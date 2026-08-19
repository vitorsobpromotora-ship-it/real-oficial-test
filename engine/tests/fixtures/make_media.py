"""Gera mídia sintética hermética para os testes (espeak-ng + ffmpeg + foto de domínio público).

- Fala PT-BR: espeak-ng (instalado no ambiente de CI/dev)
- Rosto real: grace_hopper.jpg embarcado no wheel do matplotlib (domínio público)
- Vídeos: ffmpeg compõe fundo + "falantes" (fotos) + trilha de fala
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

GENERATED = Path(__file__).resolve().parent.parent / "assets" / "_generated"

TEXTO_PADRAO = (
    "Olá pessoal, sejam bem vindos ao nosso podcast. Hoje vamos falar sobre um assunto "
    "muito importante. Eu nunca contei isso para ninguém. O maior erro que eu cometi foi "
    "não começar antes. Isso mudou completamente a minha vida."
)


def have_espeak() -> bool:
    return shutil.which("espeak-ng") is not None


def espeak_wav(dst: Path, text: str = TEXTO_PADRAO, speed: int = 150) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["espeak-ng", "-v", "pt-br", "-s", str(speed), "-w", str(dst), text],
                   check=True, capture_output=True)
    return dst


def face_photo(dst: Path) -> Path | None:
    """Copia a foto de teste (grace_hopper.jpg do matplotlib). None se indisponível."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return dst
    try:
        import matplotlib

        src = Path(matplotlib.get_data_path()) / "sample_data" / "grace_hopper.jpg"
        if src.exists():
            shutil.copy2(src, dst)
            return dst
    except ImportError:
        pass
    return None


def make_video(dst: Path, duration: float = 30.0, width: int = 1920, height: int = 1080,
               speech: Path | None = None, faces: Path | None = None) -> Path:
    """Vídeo sintético: fundo escuro, dois 'falantes' (fotos) e fala PT-BR em loop."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    inputs: list[str] = ["-f", "lavfi", "-i", f"color=c=0x1b2230:s={width}x{height}:d={duration}:r=30"]
    filters: list[str] = []
    last_v = "0:v"
    idx = 1
    if faces is not None:
        inputs += ["-loop", "1", "-t", str(duration), "-i", str(faces)]
        fw = width // 5
        filters.append(f"[{idx}:v]scale={fw}:-2[face]")
        filters.append("[face]split=2[fa][fb]")
        filters.append(f"[{last_v}][fa]overlay={width // 8}:{height // 4}[v1]")
        filters.append(f"[v1][fb]overlay={width - width // 8 - fw}:{height // 4}[vout]")
        last_v = "vout"
        idx += 1
    if speech is not None:
        inputs += ["-stream_loop", "-1", "-t", str(duration), "-i", str(speech)]
        filters.append(f"[{idx}:a]aresample=44100,volume=1.0[aout]")
        a_map = "[aout]"
    else:
        inputs += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}"]
        a_map = f"{idx}:a"

    args = [*inputs]
    if filters:
        args += ["-filter_complex", ";".join(filters)]
    args += ["-map", f"[{last_v}]" if last_v not in ("0:v",) else last_v, "-map", a_map,
             "-t", str(duration), "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", str(dst)]
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
                   check=True, capture_output=True)
    return dst


def fixture_video(name: str = "fixture_30s.mp4", duration: float = 30.0,
                  with_faces: bool = True) -> Path:
    """Vídeo de teste cacheado em assets/_generated (regenera só se ausente)."""
    out = GENERATED / name
    if out.exists():
        return out
    speech = espeak_wav(GENERATED / "fala_ptbr.wav") if have_espeak() else None
    faces = face_photo(GENERATED / "face.jpg") if with_faces else None
    return make_video(out, duration=duration, speech=speech, faces=faces)
