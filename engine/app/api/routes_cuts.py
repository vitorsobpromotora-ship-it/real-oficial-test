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
        hashtags=c.hashtags, reason=c.reason, verdict=c.verdict or "revisar",
        analysis=c.analysis, status=c.status, rank=c.rank, origin=c.origin,
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


def _invalidate_previews(s, cut_id: str) -> None:
    """Ajuste visual torna a prévia antiga obsoleta: remove registros e arquivo."""
    from .. import config  # noqa: PLC0415
    from ..db.models import Render  # noqa: PLC0415

    rows = s.execute(select(Render).where(Render.cut_id == cut_id,
                                          Render.kind == "preview")).scalars().all()
    for r in rows:
        s.delete(r)
    (config.data_dir() / "media" / "previews" / f"{cut_id}.mp4").unlink(missing_ok=True)


VISUAL_FIELDS = {"start_s", "end_s", "framing", "title", "caption_style", "brand_kit_id", "edits"}


def _apply_patch(s, c: CutCandidate, patch: CutPatch) -> None:
    # exclude_unset (e não exclude_none): null explícito significa LIMPAR o campo
    # (ex.: brand_kit_id=null remove o kit; caption_style=null volta ao padrão).
    data = patch.model_dump(exclude_unset=True)

    def _mudou(field: str, value) -> bool:
        if field == "framing":
            return ((c.edits or {}).get("framing") or "auto") != (value or "auto")
        if field in ("start_s", "end_s"):
            return value is not None and getattr(c, field) != value
        return getattr(c, field) != value

    # só invalida prévias quando o valor visual de fato muda (aprovar reenviando
    # o mesmo estilo/kit não descarta a prévia já renderizada)
    visual_change = any(_mudou(f, v) for f, v in data.items() if f in VISUAL_FIELDS)
    if "review_started" in data:
        if data.pop("review_started") and not c.review_started_at:
            c.review_started_at = utcnow()
    if data.get("status"):
        c.status = data.pop("status")
        if c.status in ("approved", "rejected"):
            c.reviewed_at = utcnow()
    else:
        data.pop("status", None)
    if data.get("start_s") is not None or data.get("end_s") is not None:
        new_start = data.pop("start_s", None)
        new_end = data.pop("end_s", None)
        new_start = c.start_s if new_start is None else new_start
        new_end = c.end_s if new_end is None else new_end
        if new_end <= new_start:
            raise HTTPException(422, "end_s deve ser maior que start_s")
        if (new_start, new_end) != (c.start_s, c.end_s):
            c.start_s, c.end_s = new_start, new_end
            c.crop_plan = None  # trim invalida o plano de enquadramento; será recalculado
    else:
        data.pop("start_s", None)
        data.pop("end_s", None)
    for field in ("title", "caption_style", "brand_kit_id", "edits", "human_rank"):
        if field in data:
            setattr(c, field, "" if field == "title" and data[field] is None else data[field])
    if "framing" in data:
        f = data.pop("framing")
        edits = dict(c.edits or {})
        if f and f != "auto":
            edits["framing"] = f
        else:
            edits.pop("framing", None)  # auto/null → volta ao enquadramento automático
        c.edits = edits or None
    if visual_change:
        _invalidate_previews(s, c.id)
    c.updated_at = utcnow()


@router.patch("/cuts/{cut_id}", response_model=CutOut)
def patch_cut(cut_id: str, patch: CutPatch):
    with session() as s:
        c = s.get(CutCandidate, cut_id)
        if c is None:
            raise HTTPException(404, "Corte não encontrado")
        _apply_patch(s, c, patch)
        s.flush()
        return to_out(c)


@router.post("/cuts/bulk", response_model=OkOut)
def bulk_patch(body: BulkCutsIn):
    with session() as s:
        rows = s.execute(select(CutCandidate).where(CutCandidate.id.in_(body.cut_ids))).scalars().all()
        if len(rows) != len(set(body.cut_ids)):
            raise HTTPException(404, "Um ou mais cortes não foram encontrados")
        for c in rows:
            _apply_patch(s, c, body.patch)
    return OkOut(ok=True, detail=f"{len(rows)} cortes atualizados")


@router.post("/cuts/{cut_id}/preview")
def preview_cut(cut_id: str, request: Request):
    """Enfileira um render de pré-visualização (540×960 rápido) do corte.

    Se já houver uma prévia na fila/em andamento, retorna essa em vez de duplicar."""
    from ..db.models import Render  # noqa: PLC0415

    with session() as s:
        c = s.get(CutCandidate, cut_id)
        if c is None:
            raise HTTPException(404, "Corte não encontrado")
        ativo = s.execute(select(Render).where(
            Render.cut_id == cut_id, Render.kind == "preview",
            Render.status.in_(("queued", "running")))).scalars().first()
        if ativo is not None:
            return {"render_id": ativo.id, "job_id": ativo.job_id}
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
