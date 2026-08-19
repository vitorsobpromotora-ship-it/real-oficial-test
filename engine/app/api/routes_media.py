"""Streaming de arquivos de mídia para a UI (tag <video> autentica via ?token=)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from .. import config
from ..db.base import session
from ..db.models import Render
from .deps import require_token_query

router = APIRouter(dependencies=[Depends(require_token_query)])


@router.get("/media/{render_id}/file")
def render_file(render_id: str):
    with session() as s:
        r = s.get(Render, render_id)
        if r is None or not r.output_path:
            raise HTTPException(404, "Arquivo de render não disponível")
        path = Path(r.output_path)
    if not path.exists():
        raise HTTPException(404, "Arquivo não existe mais no disco")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@router.get("/media/cuts/{cut_id}/preview")
def cut_preview(cut_id: str):
    path = config.data_dir() / "media" / "previews" / f"{cut_id}.mp4"
    if not path.exists():
        raise HTTPException(404, "Preview ainda não renderizado")
    return FileResponse(path, media_type="video/mp4", filename=path.name)
