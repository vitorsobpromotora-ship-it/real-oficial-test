"""Fachada "shorts" — espelha o formato da API pública do produto:
enviar um vídeo → consultar clipes com score → baixar renders.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..db.base import session
from ..db.models import CutCandidate, Job, Project, Render, SourceVideo
from .deps import require_token

router = APIRouter(dependencies=[Depends(require_token)])


class ShortsCreate(BaseModel):
    video_url: str | None = None
    file_path: str | None = None
    project_id: str | None = None
    agent: str | None = None  # claude | gpt | local (padrão: Configurações)
    options: dict = Field(default_factory=dict)


def _job_to_status(job: Job | None) -> tuple[str, float]:
    if job is None:
        return "unknown", 0.0
    mapping = {"queued": "queued", "running": "processing", "done": "done",
               "failed": "failed", "canceled": "canceled"}
    return mapping.get(job.status, job.status), job.progress


def _clips_for_source(s, source_id: str) -> list[dict]:
    cuts = s.execute(select(CutCandidate).where(CutCandidate.source_video_id == source_id)
                     .order_by(CutCandidate.score.desc())).scalars().all()
    out = []
    for c in cuts:
        render = s.execute(select(Render).where(Render.cut_id == c.id, Render.kind == "final",
                                                Render.status == "done")
                           .order_by(Render.finished_at.desc())).scalars().first()
        out.append({
            "id": c.id, "score": c.score, "title": c.title, "hook": c.hook_text,
            "start_s": c.start_s, "end_s": c.end_s, "duration_s": round(c.end_s - c.start_s, 2),
            "status": c.status, "rank": c.rank, "hashtags": c.hashtags,
            "download_url": f"/api/v1/media/{render.id}/file" if render else None,
        })
    return out


@router.post("/shorts", status_code=201)
def create_shorts(body: ShortsCreate, request: Request):
    if not body.video_url and not body.file_path:
        raise HTTPException(422, "Informe video_url ou file_path")
    if body.file_path and not Path(body.file_path).exists():
        raise HTTPException(422, f"Arquivo não encontrado: {body.file_path}")
    with session() as s:
        project_id = body.project_id
        if project_id:
            if s.get(Project, project_id) is None:
                raise HTTPException(404, "Projeto não encontrado")
        else:
            proj = Project(name="Shorts via API", description="Criado pela fachada /shorts")
            s.add(proj)
            s.flush()
            project_id = proj.id
        src = SourceVideo(project_id=project_id,
                          origin="url" if body.video_url else "file",
                          source_url=body.video_url, file_path=body.file_path,
                          title=Path(body.file_path).stem if body.file_path else "")
        s.add(src)
        s.flush()
        source_id = src.id
    from .routes_sources import options_with_agent

    opts = options_with_agent(body.options, body.agent)
    job_id = request.app.state.runner.submit(
        "process_source", {"source_video_id": source_id, "options": opts},
        project_id=project_id, source_video_id=source_id)
    return {"short_job_id": job_id, "source_video_id": source_id, "project_id": project_id}


@router.get("/shorts")
def list_shorts(limit: int = 50):
    with session() as s:
        jobs = s.execute(select(Job).where(Job.type == "process_source")
                         .order_by(Job.created_at.desc()).limit(limit)).scalars().all()
        out = []
        for j in jobs:
            status, progress = _job_to_status(j)
            src = s.get(SourceVideo, j.source_video_id) if j.source_video_id else None
            out.append({
                "id": j.id, "status": status, "progress": progress,
                "source_video_id": j.source_video_id,
                "title": src.title if src else None,
                "created_at": j.created_at,
                "clips_count": len(_clips_for_source(s, j.source_video_id))
                if j.source_video_id else 0,
            })
        return out


@router.get("/shorts/{short_job_id}")
def get_shorts(short_job_id: str):
    with session() as s:
        j = s.get(Job, short_job_id)
        if j is None or j.type != "process_source":
            raise HTTPException(404, "Short job não encontrado")
        status, progress = _job_to_status(j)
        clips = _clips_for_source(s, j.source_video_id) if j.source_video_id else []
        return {
            "id": j.id, "status": status, "progress": progress, "stage": j.stage,
            "message": j.message, "error": j.error,
            "source_video_id": j.source_video_id, "project_id": j.project_id,
            "clips": clips,
        }
