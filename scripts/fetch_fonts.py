#!/usr/bin/env python3
"""Baixa as fontes Inter e Montserrat (licença OFL) para embarcar nas legendas ASS.

Uso: python scripts/fetch_fonts.py --dest engine/assets/fonts
Best-effort: sem as fontes, o libass usa as fontes do sistema (Segoe UI/Arial) —
funciona, mas sem a identidade padrão dos presets.
"""

from __future__ import annotations

import argparse
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

FAMILIES = {
    "Inter": ["Inter-Regular.ttf", "Inter-Bold.ttf"],
    "Montserrat": ["Montserrat-Regular.ttf", "Montserrat-Bold.ttf", "Montserrat-ExtraBold.ttf"],
}


def fetch_family(family: str, wanted: list[str], dest: Path) -> list[str]:
    url = f"https://fonts.google.com/download?family={family}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        payload = resp.read()
    got: list[str] = []
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        names = zf.namelist()
        for target in wanted:
            match = next((n for n in names if n.endswith(f"/{target}") or n == target
                          or n.endswith(f"static/{target}")), None)
            if match is None:
                continue
            (dest / target).write_bytes(zf.read(match))
            got.append(target)
    return got


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dest", default="engine/assets/fonts")
    args = parser.parse_args()
    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)

    ok = True
    for family, wanted in FAMILIES.items():
        existing = [w for w in wanted if (dest / w).exists()]
        if len(existing) == len(wanted):
            print(f"{family}: já presente")
            continue
        try:
            got = fetch_family(family, wanted, dest)
            print(f"{family}: {got or 'nenhum arquivo estático encontrado'}")
            ok = ok and bool(got)
        except Exception as exc:  # noqa: BLE001
            print(f"AVISO: falha ao baixar {family}: {exc}", file=sys.stderr)
            ok = False
    if not ok:
        print("AVISO: fontes incompletas — libass usará fontes do sistema.", file=sys.stderr)
    return 0  # best-effort: nunca falha o build


if __name__ == "__main__":
    raise SystemExit(main())
