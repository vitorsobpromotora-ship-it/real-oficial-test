"""Ponto 19 — família Palavra Pop: variações com diferença VISUAL perceptível.

Não basta mudar o nome: cada preset da família é renderizado de verdade pelo
libass e comparado pixel a pixel com os irmãos. O Classic é intocável.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pytest

from app.pipeline import captions
from app.services import ffmpeg

FAMILIA = [p for p, v in captions.PRESETS.items() if v.get("family") == "Palavra Pop"]
PALAVRAS = [{"idx": i, "start_s": i * 0.6, "end_s": i * 0.6 + 0.55, "word": w}
            for i, w in enumerate(["ISSO", "MUDOU", "TUDO"])]


def _frame(preset: str, tmp: Path, t: float = 0.30) -> np.ndarray:
    """Renderiza UM frame do preset sobre fundo preto e devolve a matriz."""
    ass = captions.build_ass(PALAVRAS, {"preset": preset}, None,
                            clip_duration=2.0, fps=25.0)
    (tmp / f"{preset}.ass").write_text(ass, encoding="utf-8")
    png = tmp / f"{preset}.png"
    subprocess.run(
        [ffmpeg.find_binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "color=c=black:s=540x960:r=25:d=2",
         "-vf", f"ass={preset}.ass", "-ss", f"{t}", "-frames:v", "1", str(png)],
        cwd=tmp, check=True, capture_output=True)
    from PIL import Image  # noqa: PLC0415

    return np.asarray(Image.open(png).convert("L"), dtype=np.int16)


def test_familia_palavra_pop_tem_oito_membros():
    assert len(FAMILIA) == 8, f"esperados 8 estilos na família, achei {FAMILIA}"
    assert "palavra_pop" in FAMILIA
    rotulos = {captions.PRESET_LABELS_PTBR[p] for p in FAMILIA}
    assert captions.PRESET_LABELS_PTBR["palavra_pop"] == "Palavra Pop Classic"
    assert len(rotulos) == 8


def test_classic_preserva_o_comportamento_aprovado():
    """O Classic é o estilo já aprovado: nada além do rótulo/família muda."""
    p = captions.PRESETS["palavra_pop"]
    assert (p["font_family"], p["font_size"], p["uppercase"]) == ("Montserrat", 96, True)
    assert (p["outline"], p["shadow"], p["anchor_top"]) == (5, 2, 1180)
    assert (p["max_words"], p["word_mode"], p["max_lines"]) == (1, True, 1)
    assert (p["anim_in"], p["anim_word"], p["anim_ms"]) == ("pop", "pop", 80)
    assert p["letter_spacing"] == 1


@pytest.mark.parametrize("preset", FAMILIA)
def test_cada_preset_da_familia_renderiza_sem_aviso_do_libass(preset, tmp_path):
    ass = captions.build_ass(PALAVRAS, {"preset": preset}, None,
                             clip_duration=2.0, fps=25.0)
    (tmp_path / "s.ass").write_text(ass, encoding="utf-8")
    r = subprocess.run(
        [ffmpeg.find_binary("ffmpeg"), "-hide_banner", "-loglevel", "warning", "-y",
         "-f", "lavfi", "-i", "color=c=black:s=540x960:r=25:d=2",
         "-vf", "ass=s.ass", "-frames:v", "25", "-f", "null", "-"],
        cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "Unknown" not in r.stderr and "error" not in r.stderr.lower(), r.stderr


def test_membros_da_familia_sao_visualmente_distintos(tmp_path):
    """Nenhum par pode ser quase idêntico na tela (Ponto 19)."""
    frames = {p: _frame(p, tmp_path) for p in FAMILIA}
    for p, f in frames.items():
        assert f.max() > 40, f"{p} não desenhou texto visível"
    iguais = []
    for i, a in enumerate(FAMILIA):
        for b in FAMILIA[i + 1:]:
            dif = float(np.abs(frames[a] - frames[b]).mean())
            tinta_a, tinta_b = (frames[a] > 40).sum(), (frames[b] > 40).sum()
            razao = min(tinta_a, tinta_b) / max(1, max(tinta_a, tinta_b))
            # "quase idêntico" = pouca diferença média E mesma mancha de tinta
            if dif < 1.5 and razao > 0.97:
                iguais.append((a, b, round(dif, 2), round(razao, 3)))
    assert not iguais, f"pares visualmente iguais na família: {iguais}"
