"""Relatórios técnico-editoriais por fonte e por projeto (JSON e HTML)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from ..reports import builder
from .deps import require_token, require_token_query

router = APIRouter()


@router.get("/reports/sources/{source_id}", dependencies=[Depends(require_token)])
def source_report(source_id: str):
    try:
        return builder.source_report_json(source_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/reports/sources/{source_id}/html", response_class=HTMLResponse,
            dependencies=[Depends(require_token_query)])
def source_report_html(source_id: str):
    try:
        return builder.source_report_html(source_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/reports/projects/{project_id}", dependencies=[Depends(require_token)])
def project_report(project_id: str):
    try:
        return builder.project_report_json(project_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
