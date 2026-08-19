"""Descoberta e execução de ffmpeg/ffprobe com progresso e cancelamento.

Ordem de busca do binário: env REAL_OFICIAL_FFMPEG_DIR → pasta `ffmpeg/` ao lado
do executável (produção empacotada) → PATH do sistema.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path


class FFmpegError(RuntimeError):
    pass


def find_binary(name: str = "ffmpeg") -> str:
    exe = f"{name}.exe" if os.name == "nt" else name
    env_dir = os.environ.get("REAL_OFICIAL_FFMPEG_DIR")
    if env_dir and (Path(env_dir) / exe).exists():
        return str(Path(env_dir) / exe)
    bundled = Path(sys.executable).resolve().parent / "ffmpeg" / exe
    if bundled.exists():
        return str(bundled)
    found = shutil.which(name)
    if found:
        return found
    raise FFmpegError(
        f"Binário '{name}' não encontrado. Instale o FFmpeg ou defina REAL_OFICIAL_FFMPEG_DIR."
    )


def probe(path: str | Path) -> dict:
    """ffprobe → {duration_s, width, height, fps, size_bytes, has_audio}."""
    out = subprocess.run(
        [find_binary("ffprobe"), "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, timeout=120,
    )
    if out.returncode != 0:
        raise FFmpegError(f"ffprobe falhou para {path}: {out.stderr.strip()[:500]}")
    data = json.loads(out.stdout or "{}")
    fmt = data.get("format", {})
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    fps = None
    if video and video.get("avg_frame_rate") not in (None, "0/0"):
        num, _, den = video["avg_frame_rate"].partition("/")
        try:
            fps = round(float(num) / float(den or 1), 3)
        except (ValueError, ZeroDivisionError):
            fps = None
    return {
        "duration_s": float(fmt.get("duration") or 0) or None,
        "width": int(video["width"]) if video else None,
        "height": int(video["height"]) if video else None,
        "fps": fps,
        "size_bytes": int(fmt.get("size") or 0) or None,
        "has_audio": audio is not None,
    }


def run(args: list[str], *, duration: float | None = None,
        progress_cb: Callable[[float], None] | None = None,
        cancel_check: Callable[[], None] | None = None,
        cwd: str | Path | None = None) -> None:
    """Executa ffmpeg com -progress em stdout; chama progress_cb(fração 0–1)."""
    cmd = [find_binary("ffmpeg"), "-hide_banner", "-nostdin", "-y",
           "-loglevel", "error", *args, "-progress", "pipe:1"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, cwd=str(cwd) if cwd else None)
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if cancel_check is not None:
                try:
                    cancel_check()
                except Exception:
                    proc.terminate()
                    proc.wait(timeout=10)
                    raise
            if progress_cb and duration and duration > 0 and line.startswith("out_time_us="):
                try:
                    us = int(line.split("=", 1)[1])
                    progress_cb(min(1.0, us / 1_000_000 / duration))
                except ValueError:
                    pass
        proc.wait(timeout=600)
    finally:
        if proc.poll() is None:
            proc.kill()
    if proc.returncode != 0:
        stderr = proc.stderr.read() if proc.stderr else ""
        raise FFmpegError(f"ffmpeg saiu com código {proc.returncode}: {stderr.strip()[-800:]}")
    if progress_cb:
        progress_cb(1.0)
