"""Pontos 21–24, 46–47 — posição normalizada, safe area e precedência de cores.

A posição é medida NO PIXEL: o mesmo estilo renderizado em 540×960 e em
1080×1920 tem de cair na mesma posição PROPORCIONAL (o que a prévia mostra é
o que o render final entrega).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pytest

from app.pipeline import captions
from app.services import ffmpeg

PALAVRAS = [{"idx": 0, "start_s": 0.0, "end_s": 1.2, "word": "TESTE"}]


def _mancha(style: dict, res: tuple[int, int], tmp: Path) -> tuple[float, float]:
    """Renderiza e devolve o centro (x, y) NORMALIZADO da tinta do texto."""
    ass = captions.build_ass(PALAVRAS, style, None, res=res, clip_duration=1.5, fps=25.0)
    nome = f"p{res[0]}"
    (tmp / f"{nome}.ass").write_text(ass, encoding="utf-8")
    png = tmp / f"{nome}.png"
    subprocess.run(
        [ffmpeg.find_binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", f"color=c=black:s={res[0]}x{res[1]}:r=25:d=1.5",
         "-vf", f"ass={nome}.ass", "-ss", "0.6", "-frames:v", "1", str(png)],
        cwd=tmp, check=True, capture_output=True)
    from PIL import Image  # noqa: PLC0415

    arr = np.asarray(Image.open(png).convert("L"))
    ys, xs = np.nonzero(arr > 60)
    assert len(xs) > 50, "texto não apareceu no frame"
    return float(xs.mean() / res[0]), float(ys.mean() / res[1])


def test_margens_normalizadas_sao_proporcionais():
    a = captions._margens({"pos_x": 0.5, "pos_y": 0.68, "max_width_pct": 80}, (1080, 1920))
    b = captions._margens({"pos_x": 0.5, "pos_y": 0.68, "max_width_pct": 80}, (540, 960))
    assert a == (108, 108, 1306)
    assert b == (54, 54, 653)  # exatamente metade — mesma proporção
    # encostar na borda esquerda não empurra o texto para fora da tela
    ml, mr, _ = captions._margens({"pos_x": 0.1, "pos_y": 0.3, "max_width_pct": 80},
                                  (1080, 1920))
    assert ml == 0 and mr > 0


def test_estilo_sem_posicao_normalizada_nao_muda(tmp_path):
    """Compatibilidade: cortes/kits antigos seguem no caminho anchor_top + %."""
    assert captions._margens({"anchor_top": 1280, "max_width_pct": 88}, (1080, 1920)) \
        == (64, 64, 1280)
    assert captions._margens({"margin_l": 90, "margin_r": 30, "anchor_top": 900},
                             (1080, 1920)) == (90, 30, 900)


@pytest.mark.parametrize("pos", [(0.5, 0.25), (0.3, 0.6), (0.72, 0.8)])
def test_posicao_identica_em_previa_e_render_final(pos, tmp_path):
    """Ponto 46: prévia 540×960 e final 1080×1920 na MESMA posição proporcional."""
    # largura 50% garante que a caixa cabe na tela em todas as posições testadas
    style = {"preset": "clean", "pos_x": pos[0], "pos_y": pos[1], "max_width_pct": 50}
    x_prev, y_prev = _mancha(style, (540, 960), tmp_path)
    x_fin, y_fin = _mancha(style, (1080, 1920), tmp_path)
    assert abs(x_prev - x_fin) < 0.02, f"x divergiu: {x_prev:.3f} vs {x_fin:.3f}"
    assert abs(y_prev - y_fin) < 0.02, f"y divergiu: {y_prev:.3f} vs {y_fin:.3f}"
    # e a posição pedida é de fato respeitada (âncora no topo do texto)
    assert abs(x_fin - pos[0]) < 0.06
    assert y_fin > pos[1] - 0.02


def test_legenda_encostada_na_borda_nao_sai_da_tela(tmp_path):
    """Pedir uma posição impossível aproxima da borda em vez de cortar o texto."""
    style = {"preset": "clean", "pos_x": 0.95, "pos_y": 0.5, "max_width_pct": 70}
    x, _ = _mancha(style, (1080, 1920), tmp_path)
    assert x < 0.98, "o texto não pode vazar para fora do quadro"
    assert x > 0.5, "mas deve ficar claramente à direita, como pedido"


def test_precedencia_preset_kit_corte():
    """Ponto 24: corte › kit › preset (a palavra entra na Etapa G)."""
    preset = captions.resolve_style({"preset": "palavra_pop"}, None)
    assert preset["highlight_color"] == "#FFFFFF"

    kit = {"caption_preset": "palavra_pop", "primary_color": "#EEEEEE",
           "secondary_color": "#0000FF", "font_family": "Inter",
           "caption_style": {"outline": 9}}
    com_kit = captions.resolve_style(None, kit)
    assert com_kit["highlight_color"] == "#0000FF"  # kit vence o preset
    assert com_kit["font_family"] == "Inter"
    assert com_kit["outline"] == 9

    do_corte = captions.resolve_style(
        {"preset": "palavra_pop", "highlight_color": "#00FF00", "outline": 2}, kit)
    assert do_corte["highlight_color"] == "#00FF00"  # corte vence o kit
    assert do_corte["outline"] == 2
    assert do_corte["font_family"] == "Inter"  # o que o corte não define, o kit mantém


def test_cor_de_sombra_independe_da_caixa():
    """Ponto 23: cor de sombra própria sem alterar a caixa dos presets de box."""
    ass = captions.build_ass(PALAVRAS, {"preset": "clean", "shadow_color": "#FF0000"},
                             None, clip_duration=1.5)
    linha = next(x for x in ass.splitlines() if x.startswith("Style: Default"))
    assert "&H960000FF" in linha, linha  # BackColour = vermelho (sombra)

    ass_box = captions.build_ass(PALAVRAS, {"preset": "highlight_box",
                                            "shadow_color": "#FF0000"},
                                 None, clip_duration=1.5)
    linha_box = next(x for x in ass_box.splitlines() if x.startswith("Style: Default"))
    assert "&H0000D4FF" in linha_box, "caixa (border_style 3) mantém back_color"
