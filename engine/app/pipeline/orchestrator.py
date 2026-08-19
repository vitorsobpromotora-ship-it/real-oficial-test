"""Orquestrador do pipeline: ingest → transcribe → analyze → reframe, com checkpoints.

Cada estágio é idempotente (verifica DB/disco e pula o que já existe), então uma
retomada após restart reexecuta o job e continua de onde parou.
"""

from __future__ import annotations

import logging
import time

from ..db.base import session
from ..db.models import SourceVideo, StageTiming
from ..jobs.registry import job_handler

# Imports ESTÁTICOS: importlib com string deixava os estágios fora do binário PyInstaller.
from . import analyze, ingest, reframe, transcribe

log = logging.getLogger(__name__)

# (nome, função, progresso inicial, progresso final)
STAGES = [
    ("ingest", ingest.stage_ingest, 0.00, 0.15),
    ("transcribe", transcribe.stage_transcribe, 0.15, 0.55),
    ("analyze", analyze.stage_analyze, 0.55, 0.85),
    ("reframe", reframe.stage_reframe, 0.85, 1.00),
]


@job_handler("process_source", lane="pipeline")
def process_source(ctx) -> dict:
    source_id = ctx.payload.get("source_video_id")
    if not source_id:
        raise ValueError("payload sem source_video_id")

    executed: list[str] = []
    for name, fn, p0, p1 in STAGES:
        ctx.check_cancel()

        def report(frac: float, msg: str = "", *, _n=name, _p0=p0, _p1=p1):
            ctx.report(stage=_n, progress=_p0 + max(0.0, min(1.0, frac)) * (_p1 - _p0),
                       message=msg, force=True)

        report(0.0)
        t0 = time.monotonic()
        try:
            fn(ctx, source_id, report)
        except Exception as exc:
            with session() as s:
                src = s.get(SourceVideo, source_id)
                if src is not None and src.status != "failed":
                    src.status = "failed"
                    src.error = f"Falha no estágio {name}: {exc}"
            raise
        with session() as s:
            s.add(StageTiming(source_video_id=source_id, stage=name,
                              seconds=round(time.monotonic() - t0, 3)))
        executed.append(name)

    ctx.report(stage="finalizado", progress=1.0, message="Pipeline concluído", force=True)
    return {"source_video_id": source_id, "stages": executed}
