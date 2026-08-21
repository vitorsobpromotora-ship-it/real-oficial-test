"""CRUD de projetos."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import func, select

from .. import config
from ..db.base import session
from ..db.models import CutCandidate, Project, SourceVideo, utcnow
from ..schemas.api import OkOut, ProjectCreate, ProjectOut, ProjectUpdate
from .deps import require_token

router = APIRouter(dependencies=[Depends(require_token)])


def _to_out(p: Project, sources: int = 0, cuts: int = 0) -> ProjectOut:
    return ProjectOut(id=p.id, name=p.name, description=p.description,
                      created_at=p.created_at, updated_at=p.updated_at,
                      sources_count=sources, cuts_count=cuts)


@router.get("/projects", response_model=list[ProjectOut])
def list_projects():
    with session() as s:
        projects = s.execute(select(Project).order_by(Project.created_at.desc())).scalars().all()
        src_counts = dict(s.execute(
            select(SourceVideo.project_id, func.count()).group_by(SourceVideo.project_id)).all())
        cut_counts = dict(s.execute(
            select(CutCandidate.project_id, func.count()).group_by(CutCandidate.project_id)).all())
        return [_to_out(p, src_counts.get(p.id, 0), cut_counts.get(p.id, 0)) for p in projects]


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate):
    with session() as s:
        p = Project(name=body.name, description=body.description)
        s.add(p)
        s.flush()
        return _to_out(p)


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: str):
    with session() as s:
        p = s.get(Project, project_id)
        if p is None:
            raise HTTPException(404, "Projeto não encontrado")
        sources = s.execute(select(func.count()).where(SourceVideo.project_id == project_id)).scalar() or 0
        cuts = s.execute(select(func.count()).where(CutCandidate.project_id == project_id)).scalar() or 0
        return _to_out(p, sources, cuts)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, body: ProjectUpdate):
    with session() as s:
        p = s.get(Project, project_id)
        if p is None:
            raise HTTPException(404, "Projeto não encontrado")
        if body.name is not None:
            p.name = body.name
        if body.description is not None:
            p.description = body.description
        p.updated_at = utcnow()
        s.flush()
        return _to_out(p)


@router.delete("/projects/{project_id}", response_model=OkOut)
def delete_project(project_id: str):
    with session() as s:
        p = s.get(Project, project_id)
        if p is None:
            raise HTTPException(404, "Projeto não encontrado")
        s.delete(p)
    return OkOut(ok=True, detail="Projeto excluído")


# ---------------------------------------------------------------------------
# Biblioteca de mídia do projeto (B-roll) — v4 FASE H
# ---------------------------------------------------------------------------

BROLL_TYPES = {
    "video/mp4": ".mp4", "video/quicktime": ".mov", "video/webm": ".webm",
    "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp",
}


def _media_out(m) -> dict:
    return {"id": m.id, "project_id": m.project_id, "filename": m.filename,
            "kind": m.kind, "duration_s": m.duration_s, "width": m.width,
            "height": m.height, "created_at": m.created_at}


@router.get("/projects/{project_id}/media")
def list_media(project_id: str):
    from ..db.models import ProjectMedia  # noqa: PLC0415

    with session() as s:
        rows = s.execute(select(ProjectMedia)
                         .where(ProjectMedia.project_id == project_id)
                         .order_by(ProjectMedia.created_at.desc())).scalars().all()
        return {"media": [_media_out(m) for m in rows]}


@router.post("/projects/{project_id}/media", status_code=201)
async def upload_media(project_id: str, file: UploadFile):
    """Importa uma mídia para a biblioteca do projeto — o arquivo é COPIADO
    para o data_dir (apagar a origem não quebra os cortes; Entrega 82)."""
    from ..db.models import ProjectMedia  # noqa: PLC0415
    from ..services import ffmpeg as ff  # noqa: PLC0415

    if file.content_type not in BROLL_TYPES:
        raise HTTPException(422, "Use MP4, MOV, WebM, PNG, JPEG ou WebP")
    content = await file.read()
    if len(content) > 300 * 1024 * 1024:
        raise HTTPException(422, "Arquivo muito grande (máx. 300 MB)")
    with session() as s:
        if s.get(Project, project_id) is None:
            raise HTTPException(404, "Projeto não encontrado")
        ext = BROLL_TYPES[file.content_type]
        m = ProjectMedia(project_id=project_id,
                         filename=file.filename or f"midia{ext}",
                         path="", kind="image" if ext in (".png", ".jpg", ".webp")
                         else "video")
        dest_dir = config.data_dir() / "media" / "broll"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{m.id}{ext}"
        dest.write_bytes(content)
        m.path = str(dest)
        if m.kind == "video":
            try:
                info = ff.probe(str(dest))
                m.duration_s = info.get("duration_s")
                m.width, m.height = info.get("width"), info.get("height")
            except Exception:  # noqa: BLE001 — mídia fica utilizável mesmo sem probe
                pass
        s.add(m)
        s.flush()
        return _media_out(m)


@router.delete("/projects/{project_id}/media/{media_id}")
def delete_media(project_id: str, media_id: str):
    from pathlib import Path  # noqa: PLC0415

    from ..db.models import ProjectMedia  # noqa: PLC0415

    with session() as s:
        m = s.get(ProjectMedia, media_id)
        if m is None or m.project_id != project_id:
            raise HTTPException(404, "Mídia não encontrada")
        try:
            Path(m.path).unlink(missing_ok=True)
        except OSError:
            pass
        s.delete(m)
    return {"ok": True}
