"""JobRunner: filas por lane com workers asyncio, progresso persistido + SSE,
cancelamento cooperativo e retomada após restart.

Lanes:
  - pipeline: concorrência 1 (whisper/análise dominam CPU)
  - render:   concorrência min(cpu, 2)
  - misc:     downloads de modelo, relatórios etc.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import traceback

from sqlalchemy import select

from ..db.base import session
from ..db.models import Job, utcnow
from . import registry
from .bus import EventBus

log = logging.getLogger(__name__)


class JobCancelled(Exception):
    pass


class JobContext:
    """Passado aos handlers: progresso, cancelamento, publicação de eventos."""

    def __init__(self, runner: JobRunner, job_id: str, job_type: str, payload: dict):
        self.runner = runner
        self.job_id = job_id
        self.job_type = job_type
        self.payload = payload or {}
        self._last_write = 0.0
        self._last_cancel_check = 0.0
        self._cancel_cached = False

    def report(self, stage: str | None = None, progress: float | None = None, message: str | None = None,
               force: bool = False) -> None:
        now = time.monotonic()
        throttled = (now - self._last_write) < 0.5 and not force and stage is None
        data = {"job_id": self.job_id, "type": self.job_type}
        if not throttled:
            self._last_write = now
            with session() as s:
                job = s.get(Job, self.job_id)
                if job is None:
                    return
                if stage is not None:
                    job.stage = stage
                if progress is not None:
                    job.progress = max(0.0, min(1.0, float(progress)))
                if message is not None:
                    job.message = message
                data.update(status=job.status, stage=job.stage, progress=job.progress, message=job.message)
            self.runner.bus.publish("job.updated", data)

    def check_cancel(self) -> None:
        """Levanta JobCancelled se o cancelamento foi pedido (consulta DB no máx. a cada 1s)."""
        now = time.monotonic()
        if now - self._last_cancel_check >= 1.0:
            self._last_cancel_check = now
            with session() as s:
                job = s.get(Job, self.job_id)
                self._cancel_cached = bool(job and job.cancel_requested)
        if self._cancel_cached:
            raise JobCancelled()

    def publish(self, event: str, data: dict) -> None:
        self.runner.bus.publish(event, data)


class JobRunner:
    def __init__(self, bus: EventBus):
        self.bus = bus
        cpu = os.cpu_count() or 2
        self.lanes: dict[str, int] = {"pipeline": 1, "render": min(cpu, 2), "misc": 2}
        self.queues: dict[str, asyncio.Queue] = {}
        self._workers: list[asyncio.Task] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self.queues = {lane: asyncio.Queue() for lane in self.lanes}
        self._requeue_stale()
        for lane, concurrency in self.lanes.items():
            for i in range(concurrency):
                self._workers.append(asyncio.create_task(self._worker(lane), name=f"job-{lane}-{i}"))
        log.info("JobRunner iniciado (lanes: %s)", self.lanes)

    async def stop(self) -> None:
        for w in self._workers:
            w.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    def _requeue_stale(self) -> None:
        """Jobs 'running' de uma execução anterior voltam para 'queued'; tudo 'queued' é re-enfileirado."""
        with session() as s:
            stale = s.execute(select(Job).where(Job.status == "running")).scalars().all()
            for job in stale:
                job.status = "queued"
                job.message = "Retomado após reinício"
            queued = s.execute(select(Job).where(Job.status == "queued").order_by(Job.created_at)).scalars().all()
            items = [(j.id, j.type) for j in queued]
        for job_id, job_type in items:
            self.queues[registry.lane_for(job_type)].put_nowait(job_id)

    def submit(self, job_type: str, payload: dict | None = None, *, project_id: str | None = None,
               source_video_id: str | None = None, cut_id: str | None = None) -> str:
        """Cria o registro do job e o enfileira. Thread-safe."""
        lane = registry.lane_for(job_type)
        with session() as s:
            job = Job(type=job_type, payload=payload or {}, project_id=project_id,
                      source_video_id=source_video_id, cut_id=cut_id)
            s.add(job)
            s.flush()
            job_id = job.id
        self.bus.publish("job.updated", {"job_id": job_id, "type": job_type, "status": "queued",
                                         "stage": "", "progress": 0.0, "message": ""})
        loop = self._loop
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(self.queues[lane].put_nowait, job_id)
        return job_id

    def request_cancel(self, job_id: str) -> bool:
        with session() as s:
            job = s.get(Job, job_id)
            if job is None or job.status in ("done", "failed", "canceled"):
                return False
            job.cancel_requested = True
            if job.status == "queued":
                job.status = "canceled"
                job.finished_at = utcnow()
                data = {"job_id": job_id, "type": job.type, "status": "canceled",
                        "stage": job.stage, "progress": job.progress, "message": "Cancelado"}
            else:
                data = None
        if data:
            self.bus.publish("job.updated", data)
        return True

    async def _worker(self, lane: str) -> None:
        q = self.queues[lane]
        while True:
            job_id = await q.get()
            try:
                await self._run_job(job_id)
            except asyncio.CancelledError:
                raise
            except Exception:  # nunca derruba o worker
                log.exception("Erro inesperado no worker %s (job %s)", lane, job_id)

    async def _run_job(self, job_id: str) -> None:
        with session() as s:
            job = s.get(Job, job_id)
            if job is None or job.status != "queued":
                return
            if job.cancel_requested:
                job.status = "canceled"
                job.finished_at = utcnow()
                return
            job.status = "running"
            job.started_at = utcnow()
            job_type, payload = job.type, dict(job.payload or {})
        self.bus.publish("job.updated", {"job_id": job_id, "type": job_type, "status": "running",
                                         "stage": "", "progress": 0.0, "message": ""})
        ctx = JobContext(self, job_id, job_type, payload)
        status, result, error = "done", None, None
        try:
            handler, _lane = registry.get_handler(job_type)
            if asyncio.iscoroutinefunction(handler):
                result = await handler(ctx)
            else:
                result = await asyncio.to_thread(handler, ctx)
        except JobCancelled:
            status = "canceled"
        except asyncio.CancelledError:
            with session() as s:
                job = s.get(Job, job_id)
                if job is not None and job.status == "running":
                    job.status = "queued"  # shutdown no meio: volta para a fila
            raise
        except Exception as exc:
            status = "failed"
            error = f"{exc}\n{traceback.format_exc(limit=8)}"
            log.exception("Job %s (%s) falhou", job_id, job_type)
        final = {}
        with session() as s:
            job = s.get(Job, job_id)
            if job is not None:
                job.status = status
                job.finished_at = utcnow()
                if status == "done":
                    job.progress = 1.0
                if result is not None:
                    job.result = result
                if error:
                    job.error = error
                final = {"job_id": job_id, "type": job_type, "status": status, "stage": job.stage,
                         "progress": job.progress, "message": job.message,
                         "error": (error or "").split("\n")[0] if error else None}
        if final:
            self.bus.publish("job.updated", final)
