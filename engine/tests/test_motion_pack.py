"""v4 FASE D — pack de presets de texto com QUALITY GATE automático.

O gate formaliza a Entrega 165: nenhum preset entra no catálogo se for
brusco demais, ilegível, sem ataque ou sem recuperação. A inspeção VISUAL
(Entrega 164) acontece à parte, com o contact sheet renderizado de verdade —
este arquivo garante o piso mecânico.
"""

from __future__ import annotations

import subprocess

import numpy as np
import pytest

from app.pipeline import captions, motion_text
from app.services import ffmpeg

PACK_ESPERADO = {
    "pop_clean", "pop_elastic", "color_pop", "flash_word",       # Básicos
    "punch", "slam", "outline_burst", "word_stretch",            # Impacto
    "fatality", "diss", "bass_hit", "knockout",                  # Batalha
    "glitch_snap",                                               # Glitch
    "soft_impact",                                               # Elegantes
}

DUR = 0.8  # efeito típico de uma palavra enfatizada


def _efeito(pid: str, intensity: str = "normal") -> dict:
    return {"id": f"e_{pid}", "type": "text_emphasis", "preset": pid,
            "target": {"kind": "words", "idx": [1]}, "start": 1.0,
            "end": 1.0 + DUR, "intensity": intensity, "enabled": True,
            "seed": 9, "params": {}}


def _amostra(pid: str, intensity: str = "normal", passo: float = 1 / 30):
    e = _efeito(pid, intensity)
    p = motion_text.TEXT_PRESETS[pid]
    ts, vals = [], []
    t = 1.0
    while t < 1.0 + DUR:
        ts.append(t)
        vals.append(motion_text.text_props_at(e, p, t))
        t += passo
    return ts, vals


def test_o_pack_completo_esta_no_catalogo_com_categorias_e_descricao():
    assert set(motion_text.TEXT_PRESETS) == PACK_ESPERADO
    for pid, p in motion_text.TEXT_PRESETS.items():
        assert p["id"] == pid
        assert p["label"] and p["categoria"] and p["descricao"], pid
        assert p["categoria"] in ("Básicos", "Impacto", "Batalha", "Glitch",
                                  "Elegantes")


@pytest.mark.parametrize("pid", sorted(PACK_ESPERADO))
def test_gate_recuperacao_todo_preset_termina_neutro(pid):
    """Sem recovery = reprovado: o fim do efeito deve devolver o texto ao
    estado neutro (nada de palavra presa em 116% quando o efeito acaba)."""
    e = _efeito(pid, "forte")
    p = motion_text.TEXT_PRESETS[pid]
    fim = motion_text.text_props_at(e, p, 1.0 + DUR - 1e-4)
    assert abs(fim["scale"] - 100) < 3.0, f"{pid}: scale final {fim['scale']}"
    assert abs(fim["scale_x"] - 100) < 3.0 and abs(fim["scale_y"] - 100) < 3.0, pid
    assert fim["blur"] < 0.6 and abs(fim["bord"]) < 0.6, pid
    assert abs(fim["rot"]) < 0.8 and fim["alpha"] < 0.08, pid
    # e além da janela, neutro ABSOLUTO
    assert motion_text.text_props_at(e, p, 1.0 + DUR + 0.01) == motion_text.NEUTRAL


@pytest.mark.parametrize("pid", sorted(PACK_ESPERADO))
def test_gate_legibilidade_no_sustain(pid):
    """Durante o HOLD a palavra precisa ser legível: sem sumir (alpha), sem
    borrão permanente, sem rotação além do clamp."""
    _, vals = _amostra(pid, "forte")
    meio = vals[len(vals) // 3: 2 * len(vals) // 3]  # região do hold
    for v in meio:
        assert v["alpha"] <= 0.85, f"{pid}: some no meio (alpha {v['alpha']})"
        assert v["blur"] <= 8.0, f"{pid}: ilegível no hold (blur {v['blur']})"
        assert abs(v["rot"]) <= 5.0, pid


@pytest.mark.parametrize("pid", sorted(PACK_ESPERADO - {"soft_impact", "color_pop"}))
def test_gate_ataque_presente(pid):
    """Preset de ênfase sem ataque perceptível é reprovado: em algum instante
    dos primeiros 40% o desvio visual precisa aparecer."""
    _, vals = _amostra(pid, "normal")
    ataque = vals[: max(2, int(len(vals) * 0.4))]
    pico = max(max(abs(v["scale"] - 100), abs(v["scale_x"] - 100),
                   abs(v["scale_y"] - 100),
                   v["blur"] * 4, abs(v["bord"]) * 6, v["alpha"] * 40,
                   abs(v["rot"]) * 8) for v in ataque)
    assert pico >= 8.0, f"{pid}: ataque imperceptível (pico {pico:.1f})"


@pytest.mark.parametrize("pid", sorted(PACK_ESPERADO))
def test_gate_sem_teleporte_apos_o_ataque(pid):
    """Depois do frame de impacto inicial, a curva precisa ser contínua:
    saltos de >30% de escala entre frames vizinhos = brusco (exceto o
    próprio frame de entrada, que PODE ser um degrau intencional)."""
    _, vals = _amostra(pid, "normal")
    for a, b in zip(vals[1:], vals[2:], strict=False):
        for k in ("scale", "scale_x", "scale_y"):
            assert abs(b[k] - a[k]) <= 30.0, f"{pid}: salto {a[k]}→{b[k]} em {k}"


def test_gate_intensidade_escala_o_pico_sem_estourar_clamps():
    for pid in sorted(PACK_ESPERADO):
        picos = []
        for nivel in ("suave", "normal", "forte"):
            _, vals = _amostra(pid, nivel)
            picos.append(max(max(v["scale"], v["scale_x"], v["scale_y"])
                             for v in vals))
        assert picos[0] <= picos[1] <= picos[2], f"{pid}: {picos}"
        assert picos[2] <= 220.0, f"{pid}: estourou o clamp"


def test_presets_sao_visualmente_distintos_no_pico(tmp_path):
    """Entrega 6 na prática: cada preset produz um frame DIFERENTE no pico —
    renderizado com ffmpeg/libass de verdade, não só curvas diferentes."""
    palavras = [{"idx": 0, "start_s": 0.2, "end_s": 0.6, "word": "ISSO"},
                {"idx": 1, "start_s": 0.6, "end_s": 1.4, "word": "BATALHA"},
                {"idx": 2, "start_s": 1.4, "end_s": 1.8, "word": "AGORA"}]
    frames: dict[str, np.ndarray] = {}
    for pid in sorted(PACK_ESPERADO):
        man = {"version": 1, "effects": [{**_efeito(pid, "forte"),
                                          "start": 0.6, "end": 1.4}]}
        ass = captions.build_ass(palavras, {"preset": "clean"}, None,
                                 clip_duration=2.0, fps=30.0, motion=man)
        (tmp_path / f"{pid}.ass").write_text(ass, encoding="utf-8")
        png = tmp_path / f"{pid}.png"
        r = subprocess.run(
            [ffmpeg.find_binary("ffmpeg"), "-hide_banner", "-loglevel", "warning",
             "-y", "-f", "lavfi", "-i", "color=c=black:s=540x960:r=30:d=2",
             "-vf", f"ass={pid}.ass", "-ss", "0.70", "-frames:v", "1", str(png)],
            cwd=tmp_path, capture_output=True, text=True)
        assert r.returncode == 0, f"{pid}: {r.stderr}"
        from PIL import Image  # noqa: PLC0415

        frames[pid] = np.asarray(Image.open(png).convert("L"), dtype=np.int16)

    ids = sorted(frames)
    iguais = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            diff = int((np.abs(frames[a] - frames[b]) > 40).sum())
            if diff < 300:  # menos de 300 px diferentes = par indistinguível
                iguais.append((a, b, diff))
    assert not iguais, f"pares visualmente iguais no pico: {iguais}"
