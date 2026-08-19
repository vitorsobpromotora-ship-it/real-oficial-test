"""CRUD de projetos."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select

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
