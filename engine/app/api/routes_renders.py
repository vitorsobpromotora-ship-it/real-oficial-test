"""Renderização: individual, em lote e consulta/cancelamento."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select

from ..db.base import session
from ..db.models import BrandKit, CutCandidate, Render, RenderBatch
from ..schemas.api import OkOut, RenderBatchCreate, RenderBatchOut, RenderCreate, RenderOut
from .deps import require_token

router = APIRouter(dependencies=[Depends(require_token)])


def to_out(r: Render) -> RenderOut:
    return RenderOut(id=r.id, cut_id=r.cut_id, batch_id=r.batch_id, brand_kit_id=r.brand_kit_id,
                     kind=r.kind, status=r.status, progress=r.progress, output_path=r.output_path,
                     job_id=r.job_id, error=r.error, created_at=r.created_at,
                     started_at=r.started_at, finished_at=r.finished_at)


def _create_render(request: Request, cut_id: str, kind: str, brand_kit_id: str | None,
                   overrides: dict, batch_id: str | None = None) -> Render:
    with session() as s:
        cut = s.get(CutCandidate, cut_id)
        if cut is None:
            raise HTTPException(404, f"Corte {cut_id} não encontrado")
        if brand_kit_id and s.get(BrandKit, brand_kit_id) is None:
            raise HTTPException(404, "Brand kit não encontrado")
        r = Render(cut_id=cut_id, kind=kind, brand_kit_id=brand_kit_id,
                   preset_snapshot=overrides or {}, batch_id=batch_id)
        s.add(r)
        s.flush()
        render_id, project_id, source_id = r.id, cut.project_id, cut.source_video_id
    job_id = request.app.state.runner.submit(
        "render_cut", {"render_id": render_id}, project_id=project_id,
        source_video_id=source_id, cut_id=cut_id)
    with session() as s:
        r = s.get(Render, render_id)
        r.job_id = job_id
        s.flush()
        return r


@router.post("/renders", response_model=RenderOut, status_code=201)
def create_render(body: RenderCreate, request: Request):
    r = _create_render(request, body.cut_id, body.kind, body.brand_kit_id, body.overrides)
    return to_out(r)


@router.post("/renders/batch", response_model=RenderBatchOut, status_code=201)
def create_batch(body: RenderBatchCreate, request: Request):
    with session() as s:
        batch = RenderBatch(name=body.name or f"Lote de {len(body.cut_ids)} cortes",
                            total=len(body.cut_ids), status="running")
        s.add(batch)
        s.flush()
        batch_id = batch.id
    renders = [_create_render(request, cut_id, "final", body.brand_kit_id, body.overrides,
                              batch_id=batch_id) for cut_id in body.cut_ids]
    with session() as s:
        b = s.get(RenderBatch, batch_id)
        return RenderBatchOut(id=b.id, name=b.name, total=b.total, done=b.done, status=b.status,
                              created_at=b.created_at, renders=[to_out(r) for r in renders])


@router.get("/renders", response_model=list[RenderOut])
def list_renders(status: str | None = Query(default=None),
                 batch_id: str | None = Query(default=None),
                 cut_id: str | None = Query(default=None),
                 limit: int = Query(default=100, le=500)):
    with session() as s:
        q = select(Render).order_by(Render.created_at.desc()).limit(limit)
        if status:
            q = q.where(Render.status == status)
        if batch_id:
            q = q.where(Render.batch_id == batch_id)
        if cut_id:
            q = q.where(Render.cut_id == cut_id)
        return [to_out(r) for r in s.execute(q).scalars().all()]


@router.get("/renders/batches/{batch_id}", response_model=RenderBatchOut)
def get_batch(batch_id: str):
    with session() as s:
        b = s.get(RenderBatch, batch_id)
        if b is None:
            raise HTTPException(404, "Lote não encontrado")
        renders = s.execute(select(Render).where(Render.batch_id == batch_id)
                            .order_by(Render.created_at)).scalars().all()
        return RenderBatchOut(id=b.id, name=b.name, total=b.total, done=b.done, status=b.status,
                              created_at=b.created_at, renders=[to_out(r) for r in renders])


@router.get("/renders/{render_id}", response_model=RenderOut)
def get_render(render_id: str):
    with session() as s:
        r = s.get(Render, render_id)
        if r is None:
            raise HTTPException(404, "Render não encontrado")
        return to_out(r)


@router.post("/renders/{render_id}/cancel", response_model=OkOut)
def cancel_render(render_id: str, request: Request):
    with session() as s:
        r = s.get(Render, render_id)
        if r is None:
            raise HTTPException(404, "Render não encontrado")
        job_id = r.job_id
    if not job_id or not request.app.state.runner.request_cancel(job_id):
        raise HTTPException(409, "Render já finalizado")
    return OkOut(ok=True, detail="Cancelamento solicitado")
