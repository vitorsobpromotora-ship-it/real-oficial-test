#!/usr/bin/env python3
"""Baixa binários estáticos de ffmpeg/ffprobe (builds GPL do projeto BtbN) para empacotar.

Uso: python scripts/fetch_ffmpeg.py --platform {win64|linux64} --dest app/resources/ffmpeg
Nota de licença: o FFmpeg GPL é executado como PROCESSO SEPARADO (mera agregação);
o texto da GPL e o link do código-fonte são distribuídos em docs/LICENSES.md.
"""

from __future__ import annotations

import argparse
import io
import shutil
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

URLS = {
    "win64": ("https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/"
              "ffmpeg-master-latest-win64-gpl.zip"),
    "linux64": ("https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/"
                "ffmpeg-master-latest-linux64-gpl.tar.xz"),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=["win64", "linux64"],
                        default="win64" if sys.platform == "win32" else "linux64")
    parser.add_argument("--dest", default="app/resources/ffmpeg")
    args = parser.parse_args()

    dest = Path(args.dest)
    exe_suffix = ".exe" if args.platform == "win64" else ""
    if (dest / f"ffmpeg{exe_suffix}").exists() and (dest / f"ffprobe{exe_suffix}").exists():
        print(f"ffmpeg já presente em {dest}")
        return 0
    dest.mkdir(parents=True, exist_ok=True)

    url = URLS[args.platform]
    print(f"Baixando {url} …")
    with urllib.request.urlopen(url, timeout=300) as resp:
        payload = resp.read()
    print(f"{len(payload) / 1e6:.1f} MB baixados; extraindo ffmpeg/ffprobe…")

    wanted = {f"ffmpeg{exe_suffix}", f"ffprobe{exe_suffix}"}
    found = set()
    if args.platform == "win64":
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            for name in zf.namelist():
                base = name.rsplit("/", 1)[-1]
                if base in wanted and "/bin/" in name:
                    with zf.open(name) as src, open(dest / base, "wb") as out:
                        shutil.copyfileobj(src, out)
                    found.add(base)
    else:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:xz") as tf:
            for member in tf.getmembers():
                base = member.name.rsplit("/", 1)[-1]
                if base in wanted and "/bin/" in member.name:
                    src = tf.extractfile(member)
                    assert src is not None
                    (dest / base).write_bytes(src.read())
                    (dest / base).chmod(0o755)
                    found.add(base)

    missing = wanted - found
    if missing:
        print(f"ERRO: binários não encontrados no pacote: {missing}", file=sys.stderr)
        return 1
    print(f"OK: {sorted(found)} em {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
