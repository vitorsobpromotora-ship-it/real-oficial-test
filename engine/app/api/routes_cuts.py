"""Cortes: listagem por projeto/fonte, revisão (aprovar/rejeitar/ajustar) e edição em massa."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select

from ..db.base import session
from ..db.models import CutCandidate, utcnow
from ..schemas.api import BulkCutsIn, CutOut, CutPatch, OkOut
from .deps import require_token

router = APIRouter(dependencies=[Depends(require_token)])


def to_out(c: CutCandidate) -> CutOut:
    return CutOut(
        id=c.id, source_video_id=c.source_video_id, project_id=c.project_id,
        start_s=c.start_s, end_s=c.end_s, duration_s=round(c.end_s - c.start_s, 3),
        score=c.score, score_breakdown=c.score_breakdown, rhpt_score=c.rhpt_score,
        semantic_score=c.semantic_score, hook_text=c.hook_text, title=c.title,
        hashtags=c.hashtags, reason=c.reason, status=c.status, rank=c.rank, origin=c.origin,
        crop_plan=c.crop_plan, censor_plan=c.censor_plan, caption_style=c.caption_style,
        brand_kit_id=c.brand_kit_id, edits=c.edits, human_rank=c.human_rank,
        review_started_at=c.review_started_at, reviewed_at=c.reviewed_at,
        created_at=c.created_at, updated_at=c.updated_at)


@router.get("/projects/{project_id}/cuts", response_model=list[CutOut])
def list_cuts(project_id: str, status: str | None = Query(default=None),
              source_video_id: str | None = Query(default=None),
              sort: str = Query(default="score")):
    with session() as s:
        q = select(CutCandidate).where(CutCandidate.project_id == project_id)
        if status:
            q = q.where(CutCandidate.status == status)
        if source_video_id:
            q = q.where(CutCandidate.source_video_id == source_video_id)
        if sort == "time":
            q = q.order_by(CutCandidate.start_s)
        else:
            q = q.order_by(CutCandidate.score.desc())
        return [to_out(c) for c in s.execute(q).scalars().all()]


@router.get("/cuts/{cut_id}", response_model=CutOut)
def get_cut(cut_id: str):
    with session() as s:
        c = s.get(CutCandidate, cut_id)
        if c is None:
            raise HTTPException(404, "Corte não encontrado")
        return to_out(c)


def _apply_patch(c: CutCandidate, patch: CutPatch) -> None:
    data = patch.model_dump(exclude_none=True)
    if "review_started" in data:
        if data.pop("review_started") and not c.review_started_at:
            c.review_started_at = utcnow()
    if "status" in data:
        c.status = data.pop("status")
        if c.status in ("approved", "rejected"):
            c.reviewed_at = utcnow()
    if "start_s" in data or "end_s" in data:
        new_start = data.pop("start_s", c.start_s)
        new_end = data.pop("end_s", c.end_s)
        if new_end <= new_start:
            raise HTTPException(422, "end_s deve ser maior que start_s")
        c.start_s, c.end_s = new_start, new_end
        c.crop_plan = None  # trim invalida o plano de enquadramento; será recalculado
    for field in ("title", "caption_style", "brand_kit_id", "edits", "human_rank"):
        if field in data:
            setattr(c, field, data[field])
    c.updated_at = utcnow()


@router.patch("/cuts/{cut_id}", response_model=CutOut)
def patch_cut(cut_id: str, patch: CutPatch):
    with session() as s:
        c = s.get(CutCandidate, cut_id)
        if c is None:
            raise HTTPException(404, "Corte não encontrado")
        _apply_patch(c, patch)
        s.flush()
        return to_out(c)


@router.post("/cuts/bulk", response_model=OkOut)
def bulk_patch(body: BulkCutsIn):
    with session() as s:
        rows = s.execute(select(CutCandidate).where(CutCandidate.id.in_(body.cut_ids))).scalars().all()
        if len(rows) != len(set(body.cut_ids)):
            raise HTTPException(404, "Um ou mais cortes não foram encontrados")
        for c in rows:
            _apply_patch(c, body.patch)
    return OkOut(ok=True, detail=f"{len(rows)} cortes atualizados")


@router.post("/cuts/{cut_id}/preview")
def preview_cut(cut_id: str, request: Request):
    """Enfileira um render de pré-visualização (540×960 rápido) do corte."""
    from ..db.models import Render  # noqa: PLC0415

    with session() as s:
        c = s.get(CutCandidate, cut_id)
        if c is None:
            raise HTTPException(404, "Corte não encontrado")
        r = Render(cut_id=cut_id, kind="preview")
        s.add(r)
        s.flush()
        render_id, project_id, source_id = r.id, c.project_id, c.source_video_id
    job_id = request.app.state.runner.submit("render_cut", {"render_id": render_id},
                                             project_id=project_id, source_video_id=source_id,
                                             cut_id=cut_id)
    with session() as s:
        r = s.get(Render, render_id)
        r.job_id = job_id
    return {"render_id": render_id, "job_id": job_id}


@router.delete("/cuts/{cut_id}", response_model=OkOut)
def delete_cut(cut_id: str):
    with session() as s:
        c = s.get(CutCandidate, cut_id)
        if c is None:
            raise HTTPException(404, "Corte não encontrado")
        s.delete(c)
    return OkOut(ok=True, detail="Corte excluído")
