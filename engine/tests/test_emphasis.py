"""Pontos 15–18, 29, 45, 48 — ênfase por palavra.

A ênfase é o override mais específico (vence corte, kit e preset) e NÃO pode
mexer na linha de leitura: as palavras vizinhas ficam exatamente onde estavam.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pytest

from app.pipeline import captions
from app.services import ffmpeg

FRASE = ["ISSO", "AQUI", "MUDOU"]
PALAVRAS = [{"idx": i, "start_s": 0.2 + i * 0.5, "end_s": 0.2 + i * 0.5 + 0.45, "word": w}
            for i, w in enumerate(FRASE)]


def _png(tmp: Path, nome: str, edits: dict | None, t: float,
         style: dict | None = None) -> np.ndarray:
    ass = captions.build_ass(PALAVRAS, style or {"preset": "clean"}, None,
                             clip_duration=2.2, fps=25.0, edits=edits)
    (tmp / f"{nome}.ass").write_text(ass, encoding="utf-8")
    png = tmp / f"{nome}.png"
    r = subprocess.run(
        [ffmpeg.find_binary("ffmpeg"), "-hide_banner", "-loglevel", "warning", "-y",
         "-f", "lavfi", "-i", "color=c=black:s=540x960:r=25:d=2.2",
         "-vf", f"ass={nome}.ass", "-ss", f"{t}", "-frames:v", "1", str(png)],
        cwd=tmp, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "Unknown" not in r.stderr, r.stderr
    from PIL import Image  # noqa: PLC0415

    return np.asarray(Image.open(png).convert("L"), dtype=np.int16)


def _topo(arr: np.ndarray, x0: float, x1: float) -> int:
    """Primeira linha (Y) com tinta na faixa horizontal [x0, x1] da largura."""
    faixa = arr[:, int(arr.shape[1] * x0):int(arr.shape[1] * x1)]
    ys = np.nonzero((faixa > 60).any(axis=1))[0]
    assert len(ys), "sem tinta na faixa medida"
    return int(ys[0])


def test_todos_os_efeitos_geram_tags_validas():
    style = captions.resolve_style({"preset": "bold_karaoke"}, None)
    for efeito in captions.EMPHASIS_EFFECTS:
        pre, pos = captions._emphasis_tags({"effect": efeito}, style, 500, 400)
        assert pre.startswith("{\\") and pre.endswith("}"), efeito
        assert "\\fs" not in pre.replace("\\fscx", "").replace("\\fscy", ""), \
            f"{efeito} não pode mexer no tamanho da fonte (reflui a linha)"
        assert "\\pos" not in pre and "\\move" not in pre, \
            f"{efeito} não pode reposicionar o texto"
        assert "\\fscx100\\fscy100" in pos and "\\bord" in pos, efeito
        assert captions.EMPHASIS_LABELS_PTBR[efeito]


def test_intensidade_muda_a_escala_do_efeito():
    style = captions.resolve_style({"preset": "bold_karaoke"}, None)
    escalas = []
    for nivel in ("suave", "normal", "forte"):
        pre, _ = captions._emphasis_tags({"effect": "punch", "intensity": nivel},
                                         style, 0, 400)
        escalas.append(int(pre.split("\\fscx")[1].split("\\")[0]))
    assert escalas[0] < escalas[1] < escalas[2], escalas


def test_enfase_so_atinge_a_palavra_alvo():
    edits = {"word_emphasis": [{"idx": [1], "effect": "impact"}]}
    ass = captions.build_ass(PALAVRAS, {"preset": "clean"}, None,
                             clip_duration=2.2, fps=25.0, edits=edits)
    linha = next(x for x in ass.splitlines() if x.startswith("Dialogue: 0"))
    antes, depois = linha.split("AQUI")
    assert "\\t(" in antes.split("ISSO")[1], "a ênfase precede a palavra alvo"
    assert "\\fscx100\\fscy100" in depois.split("MUDOU")[0], "reset antes da próxima palavra"
    assert "\\t(" not in depois.split("MUDOU")[0].replace("\\fscx100\\fscy100", "")


def test_enfase_por_expressao_cobre_varias_palavras():
    edits = {"word_emphasis": [{"idx": [0, 1], "effect": "pop"}]}
    ass = captions.build_ass(PALAVRAS, {"preset": "clean"}, None,
                             clip_duration=2.2, fps=25.0, edits=edits)
    linha = next(x for x in ass.splitlines() if x.startswith("Dialogue: 0"))
    assert linha.count("\\t(") >= 4, "as duas palavras recebem o efeito"


def test_cor_da_enfase_vence_corte_kit_e_preset():
    """Ponto 24: palavra > corte > kit > preset."""
    kit = {"caption_preset": "clean", "secondary_color": "#0000FF"}
    edits = {"word_emphasis": [{"idx": [1], "effect": "pop", "color": "#FF0000"}]}
    ass = captions.build_ass(PALAVRAS, {"preset": "clean", "text_color": "#00FF00"},
                             kit, clip_duration=2.2, fps=25.0, edits=edits)
    linha = next(x for x in ass.splitlines() if x.startswith("Dialogue: 0"))
    antes_alvo = linha.split("AQUI")[0]
    assert "\\c&H000000FF" in antes_alvo, "a palavra usa a cor da ênfase (vermelho)"
    estilo = next(x for x in ass.splitlines() if x.startswith("Style: Default"))
    assert "&H0000FF00" in estilo, "o resto do cartão mantém a cor do corte (verde)"


@pytest.mark.parametrize("efeito", ["pop", "punch", "impact", "fatality", "color_hit",
                                    "shake", "highlight_box", "soft_lift"])
def test_efeitos_renderizam_no_libass_sem_aviso(efeito, tmp_path):
    """Ponto 45 (parte técnica): os 8 efeitos prioritários são sólidos."""
    edits = {"word_emphasis": [{"idx": [1], "effect": efeito, "intensity": "forte"}]}
    arr = _png(tmp_path, f"e_{efeito}", edits, t=0.85)
    assert (arr > 60).sum() > 200, "cartão deveria estar visível no instante medido"


def test_enfase_nao_desloca_a_linha_de_leitura(tmp_path):
    """Pontos 29/48: a palavra pode crescer, as vizinhas NÃO se mexem."""
    base = _png(tmp_path, "base", None, t=0.85)
    topo_base = _topo(base, 0.0, 0.42)  # faixa da 1ª palavra (sem ênfase)
    for efeito in ("impact", "fatality", "punch", "highlight_box"):
        edits = {"word_emphasis": [{"idx": [2], "effect": efeito, "intensity": "forte"}]}
        arr = _png(tmp_path, f"l_{efeito}", edits, t=0.85)
        assert _topo(arr, 0.0, 0.42) == topo_base, \
            f"{efeito} deslocou a linha das palavras vizinhas"


def test_sequencia_mista_mantem_a_linha_base(tmp_path):
    """Ponto 48: 1 linha → 2 linhas → 1 linha, com Impact e Fatality no meio."""
    palavras = []
    t = 0.2
    grupos = [["UM"], ["DOIS", "TRES", "QUATRO", "CINCO", "SEIS", "SETE"], ["OITO"],
              ["NOVE"], ["DEZ"], ["ONZE"]]
    idx = 0
    for g in grupos:
        for w in g:
            palavras.append({"idx": idx, "start_s": t, "end_s": t + 0.3, "word": w})
            idx += 1
            t += 0.35
        t += 0.7  # pausa força a quebra de cartão
    edits = {"word_emphasis": [{"idx": [9], "effect": "impact", "intensity": "forte"},
                               {"idx": [11], "effect": "fatality", "intensity": "forte"}]}
    style = {"preset": "clean", "max_chars": 14, "max_lines": 2}
    ass = captions.build_ass(palavras, style, None, clip_duration=t + 1, fps=25.0, edits=edits)
    (tmp_path / "seq.ass").write_text(ass, encoding="utf-8")

    cartoes = captions.build_cards(palavras, captions.resolve_style(style, None))
    janelas = captions.card_windows(cartoes, fps=25.0)
    # nenhum par de cartões coexiste
    for (_s1, e1), (s2, _) in zip(janelas, janelas[1:], strict=False):
        assert e1 <= s2, "cartões não podem se sobrepor"

    from PIL import Image  # noqa: PLC0415

    topos = []
    for i, (s1, e1) in enumerate(janelas):
        meio = (s1 + e1) / 2
        png = tmp_path / f"seq{i}.png"
        subprocess.run(
            [ffmpeg.find_binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", f"color=c=black:s=540x960:r=25:d={t + 1:.2f}",
             "-vf", "ass=seq.ass", "-ss", f"{meio:.2f}", "-frames:v", "1", str(png)],
            cwd=tmp_path, check=True, capture_output=True)
        arr = np.asarray(Image.open(png).convert("L"), dtype=np.int16)
        ys = np.nonzero((arr > 60).any(axis=1))[0]
        if len(ys):
            topos.append(int(ys[0]))
    assert len(topos) >= 5
    # a linha-base é a MESMA em todos os cartões (1 linha, 2 linhas, com ênfase…)
    assert max(topos) - min(topos) <= 4, f"a legenda pulou verticalmente: {topos}"
