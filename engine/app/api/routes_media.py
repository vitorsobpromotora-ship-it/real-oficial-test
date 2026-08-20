"""Streaming de arquivos de mídia para a UI (tags <video>/<img> autenticam via ?token=)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from .. import config
from ..db.base import session
from ..db.models import CutCandidate, Render, SourceVideo
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


@router.get("/media/brand/{filename}")
def brand_asset(filename: str):
    """Logos e assets de camada do Brand Studio (nome de arquivo, sem caminhos)."""
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(404, "Arquivo inválido")
    base = config.data_dir() / "media" / "brand"
    for cand in (base / filename, base / "assets" / filename):
        if cand.exists():
            tipos = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp",
                     ".mp4": "video/mp4", ".webm": "video/webm"}
            return FileResponse(cand, media_type=tipos.get(cand.suffix, "application/octet-stream"))
    raise HTTPException(404, "Asset não encontrado")


@router.get("/media/sources/{source_id}/file")
def source_file(source_id: str):
    """Vídeo-fonte original para o player do Editor (FileResponse atende Range/seek)."""
    with session() as s:
        v = s.get(SourceVideo, source_id)
        if v is None or not v.file_path:
            raise HTTPException(404, "Fonte não disponível")
        path = Path(v.file_path)
    if not path.exists():
        raise HTTPException(404, "Arquivo da fonte não existe mais no disco")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@router.get("/media/cuts/{cut_id}/thumb")
def cut_thumb(cut_id: str):
    """Miniatura real do corte (frame do meio, 360px) — cache em disco."""
    from ..services import ffmpeg  # noqa: PLC0415

    with session() as s:
        c = s.get(CutCandidate, cut_id)
        if c is None:
            raise HTTPException(404, "Corte não encontrado")
        src = s.get(SourceVideo, c.source_video_id)
        if src is None or not src.file_path or not Path(src.file_path).exists():
            raise HTTPException(404, "Vídeo da fonte não disponível")
        video, mid = src.file_path, (c.start_s + c.end_s) / 2
    key = hashlib.sha1(f"{video}:{mid:.2f}".encode()).hexdigest()[:12]
    out = config.data_dir() / "media" / "thumbs" / f"{cut_id}-{key}.jpg"
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg.run(["-ss", f"{mid:.3f}", "-i", video, "-frames:v", "1",
                    "-vf", "scale=360:-2", "-q:v", "5", str(out)])
    return FileResponse(out, media_type="image/jpeg")


@router.get("/media/cuts/{cut_id}/filmstrip")
def cut_filmstrip(cut_id: str, t0: float | None = Query(default=None, ge=0),
                  t1: float | None = Query(default=None, ge=0),
                  frames: int = Query(default=10, ge=4, le=24)):
    """Tira de miniaturas reais do trecho para a timeline do Editor (cache em disco).

    Janela padrão = envelope do corte; o Editor pede t0/t1 explícitos quando
    mostra contexto ao redor. A imagem é `frames` quadros de 160px lado a lado."""
    from ..services import ffmpeg  # noqa: PLC0415

    with session() as s:
        c = s.get(CutCandidate, cut_id)
        if c is None:
            raise HTTPException(404, "Corte não encontrado")
        src = s.get(SourceVideo, c.source_video_id)
        if src is None or not src.file_path or not Path(src.file_path).exists():
            raise HTTPException(404, "Vídeo da fonte não disponível")
        video, ca, cb = src.file_path, c.start_s, c.end_s
    a = ca if t0 is None else t0
    b = cb if t1 is None else t1
    if b - a < 0.2:
        raise HTTPException(422, "Janela do filmstrip muito curta")
    key = hashlib.sha1(f"{video}:{Path(video).stat().st_mtime_ns}:{a:.2f}:{b:.2f}:{frames}"
                       .encode()).hexdigest()[:16]
    out = config.data_dir() / "media" / "filmstrips" / f"{cut_id}-{key}.jpg"
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        dur = b - a
        ffmpeg.run(["-ss", f"{a:.3f}", "-t", f"{dur:.3f}", "-i", video,
                    "-vf", f"fps={frames * 1.05 / dur:.6f},scale=160:-2,tile={frames}x1",
                    "-frames:v", "1", "-q:v", "5", str(out)])
    return FileResponse(out, media_type="image/jpeg")
