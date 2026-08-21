"""Pontos 7 e 49 — contrato WYSIWYG: prévia e render final não podem divergir.

`shared/wysiwyg-cases.json` é lido pelos DOIS lados (aqui e em
app/tests/wysiwyg.test.ts). Se o motor mudar a geometria da legenda sem
atualizar o contrato, este teste quebra; se o canvas divergir, o do app quebra.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

from app.pipeline import captions
from app.services import ffmpeg

CONTRATO = Path(__file__).resolve().parents[2] / "shared" / "wysiwyg-cases.json"


def test_contrato_existe_e_cobre_os_casos_importantes():
    doc = json.loads(CONTRATO.read_text(encoding="utf-8"))
    nomes = {c["nome"] for c in doc["casos"]}
    assert len(doc["casos"]) >= 6
    assert any("normalizado" in n for n in nomes)
    assert any("Estudio" in n or "Estúdio" in n for n in nomes)


def test_motor_bate_com_o_contrato():
    doc = json.loads(CONTRATO.read_text(encoding="utf-8"))
    for caso in doc["casos"]:
        style = captions.resolve_style(caso["style"], None)
        for chave, esperado in caso["res"].items():
            w, h = (int(x) for x in chave.split("x"))
            ml, mr, anchor = captions._margens(style, (w, h))
            assert {"ml": ml, "mr": mr, "anchor_top": anchor} == esperado, \
                f"{caso['nome']} @ {chave}: contrato desatualizado — regenere shared/"


def test_previa_e_final_so_diferem_na_resolucao(tmp_path):
    """A MESMA descrição em 540×960 e 1080×1920: o quadro reduzido é
    praticamente o quadro grande redimensionado (só resolução muda)."""
    from PIL import Image  # noqa: PLC0415

    palavras = [{"idx": i, "start_s": 0.2 + i * 0.5, "end_s": 0.6 + i * 0.5, "word": w}
                for i, w in enumerate(["ISSO", "MUDOU", "TUDO"])]
    style = {"preset": "bold_karaoke", "pos_x": 0.5, "pos_y": 0.6,
             "max_width_pct": 80, "text_color": "#FFFFFF"}
    edits = {"word_emphasis": [{"idx": [1], "effect": "impact", "intensity": "forte"}]}
    # o pipeline gera UM ASS (PlayRes 1080×1920) e deixa o libass escalar para
    # o tamanho do vídeo — é isso que faz prévia e final coincidirem
    ass = captions.build_ass(palavras, style, None, clip_duration=2.0, fps=25.0,
                             edits=edits)
    quadros = {}
    for res in [(540, 960), (1080, 1920)]:
        nome = f"r{res[0]}"
        (tmp_path / f"{nome}.ass").write_text(ass, encoding="utf-8")
        png = tmp_path / f"{nome}.png"
        subprocess.run(
            [ffmpeg.find_binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", f"color=c=black:s={res[0]}x{res[1]}:r=25:d=2",
             "-vf", f"ass={nome}.ass", "-ss", "0.75", "-frames:v", "1", str(png)],
            cwd=tmp_path, check=True, capture_output=True)
        img = Image.open(png).convert("L").resize((270, 480), Image.BILINEAR)
        quadros[res] = np.asarray(img, dtype=np.float32)

    a, b = quadros[(540, 960)], quadros[(1080, 1920)]
    # mesma mancha de texto (tolerância para antialiasing/escala)
    tinta_a, tinta_b = (a > 60).sum(), (b > 60).sum()
    assert abs(tinta_a - tinta_b) / max(1, tinta_b) < 0.12, (tinta_a, tinta_b)
    # mesmo centro de massa
    ys_a, xs_a = np.nonzero(a > 60)
    ys_b, xs_b = np.nonzero(b > 60)
    assert abs(xs_a.mean() - xs_b.mean()) < 6
    assert abs(ys_a.mean() - ys_b.mean()) < 6
