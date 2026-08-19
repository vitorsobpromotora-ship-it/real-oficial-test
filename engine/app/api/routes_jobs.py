"""Listagem, consulta e cancelamento de jobs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select

from ..db.base import session
from ..db.models import Job
from ..schemas.api import JobOut, OkOut
from .deps import require_token

router = APIRouter(dependencies=[Depends(require_token)])


def to_out(j: Job, include_result: bool = False) -> JobOut:
    return JobOut(
        id=j.id, type=j.type, status=j.status, stage=j.stage, progress=j.progress,
        message=j.message, error=j.error, project_id=j.project_id,
        source_video_id=j.source_video_id, cut_id=j.cut_id, created_at=j.created_at,
        started_at=j.started_at, finished_at=j.finished_at,
        result=j.result if include_result else None,
    )


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(status: str | None = Query(default=None), type: str | None = Query(default=None),
              source_video_id: str | None = Query(default=None),
              limit: int = Query(default=100, le=500)):
    with session() as s:
        q = select(Job).order_by(Job.created_at.desc()).limit(limit)
        if status:
            q = q.where(Job.status == status)
        if type:
            q = q.where(Job.type == type)
        if source_video_id:
            q = q.where(Job.source_video_id == source_video_id)
        return [to_out(j) for j in s.execute(q).scalars().all()]


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str):
    with session() as s:
        j = s.get(Job, job_id)
        if j is None:
            raise HTTPException(404, "Job não encontrado")
        return to_out(j, include_result=True)


@router.post("/jobs/{job_id}/cancel", response_model=OkOut)
def cancel_job(job_id: str, request: Request):
    runner = request.app.state.runner
    ok = runner.request_cancel(job_id)
    if not ok:
        raise HTTPException(409, "Job já finalizado ou inexistente")
    return OkOut(ok=True, detail="Cancelamento solicitado")
