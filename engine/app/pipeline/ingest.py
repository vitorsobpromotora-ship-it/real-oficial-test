"""Estágio de ingestão: download por URL (yt-dlp) ou arquivo local, probe e extração de áudio."""

from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from pathlib import Path

from .. import config
from ..db.base import session
from ..db.models import SourceVideo
from ..services import ffmpeg

log = logging.getLogger(__name__)


def download_url(url: str, dest_dir: Path, progress_cb: Callable[[float], None] | None = None,
                 cancel_check: Callable[[], None] | None = None) -> tuple[Path, str]:
    """Baixa via yt-dlp (YouTube/Drive/mp4 direto). Retorna (arquivo, título)."""
    import yt_dlp  # import tardio: módulo pesado

    def hook(d: dict) -> None:
        if cancel_check is not None:
            cancel_check()
        if progress_cb and d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes")
            if total and done:
                progress_cb(min(1.0, done / total))

    opts = {
        "outtmpl": str(dest_dir / "%(id)s.%(ext)s"),
        "format": "bv*[height<=1080]+ba/b",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if "entries" in info:  # playlist inesperada: usa o primeiro item
            info = info["entries"][0]
        path = Path(ydl.prepare_filename(info))
        if not path.exists():  # merge pode trocar a extensão
            candidates = list(dest_dir.glob(f"{info['id']}.*"))
            if not candidates:
                raise FileNotFoundError(f"Download não produziu arquivo para {url}")
            path = candidates[0]
        return path, info.get("title") or path.stem


def extract_audio_wav16k(src: Path, dst: Path,
                         progress_cb: Callable[[float], None] | None = None,
                         cancel_check: Callable[[], None] | None = None,
                         duration: float | None = None) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg.run(["-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dst)],
               duration=duration, progress_cb=progress_cb, cancel_check=cancel_check)
    return dst


def stage_ingest(ctx, source_id: str, report: Callable[[float, str], None]) -> None:
    with session() as s:
        src = s.get(SourceVideo, source_id)
        if src is None:
            raise ValueError(f"Fonte {source_id} não existe")
        origin, url, file_path, audio_path = src.origin, src.source_url, src.file_path, src.audio_path

    sources_dir = config.data_dir() / "media" / "sources"
    audio_dir = config.data_dir() / "media" / "audio"

    # Checkpoint: já pronto com arquivos presentes → pula.
    if file_path and Path(file_path).exists() and audio_path and Path(audio_path).exists():
        report(1.0, "Ingestão já concluída")
        return

    try:
        title = None
        if origin == "url":
            report(0.0, "Baixando vídeo…")
            local, title = download_url(url, sources_dir,
                                        progress_cb=lambda f: report(f * 0.6, "Baixando vídeo…"),
                                        cancel_check=ctx.check_cancel)
        else:
            local = Path(file_path)
            if not local.exists():
                raise FileNotFoundError(f"Arquivo não encontrado: {local}")
            # Copia para a área da aplicação para o original poder ser removido pelo usuário.
            managed = sources_dir / f"{source_id}{local.suffix.lower() or '.mp4'}"
            if not managed.exists():
                report(0.1, "Copiando arquivo…")
                shutil.copy2(local, managed)
            local = managed

        report(0.65, "Lendo metadados…")
        meta = ffmpeg.probe(local)
        if not meta["has_audio"]:
            raise ValueError("O vídeo não possui trilha de áudio — impossível transcrever.")

        wav = audio_dir / f"{source_id}.wav"
        if not wav.exists():
            report(0.7, "Extraindo áudio…")
            extract_audio_wav16k(local, wav, duration=meta["duration_s"],
                                 progress_cb=lambda f: report(0.7 + f * 0.3, "Extraindo áudio…"),
                                 cancel_check=ctx.check_cancel)

        with session() as s:
            src = s.get(SourceVideo, source_id)
            src.file_path = str(local)
            src.audio_path = str(wav)
            src.duration_s = meta["duration_s"]
            src.width = meta["width"]
            src.height = meta["height"]
            src.fps = meta["fps"]
            src.size_bytes = meta["size_bytes"]
            if title:
                src.title = title
            src.status = "ready"
            src.error = None
        report(1.0, "Ingestão concluída")
    except Exception as exc:
        with session() as s:
            src = s.get(SourceVideo, source_id)
            if src is not None:
                src.status = "failed"
                src.error = str(exc)
        raise
