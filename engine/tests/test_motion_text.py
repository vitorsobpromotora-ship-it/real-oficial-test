"""v4 FASE C — Text Motion Core: compilador manifest → ASS.

Prova com ffmpeg/libass REAIS que: o efeito do manifest anima a palavra alvo
(pixels), não desloca a linha de leitura, tem precedência sobre a ênfase
clássica, é determinístico e o contrato text_props compartilhado com o preview
continua fiel ao catálogo.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from app.pipeline import captions, motion_text
from app.services import ffmpeg

FRASE = ["ISSO", "AQUI", "MUDOU"]
PALAVRAS = [{"idx": i, "start_s": 0.2 + i * 0.5, "end_s": 0.2 + i * 0.5 + 0.45, "word": w}
            for i, w in enumerate(FRASE)]

CASES = json.loads((Path(__file__).resolve().parents[2]
                    / "shared" / "motion-cases.json").read_text())


def _manifest(preset: str = "punch", idx: int = 1, **kw) -> dict:
    e = {"id": "fx1", "type": "text_emphasis", "preset": preset,
         "target": {"kind": "words", "idx": [idx]},
         "start": PALAVRAS[idx]["start_s"], "end": PALAVRAS[idx]["end_s"] + 0.25,
         "intensity": "forte", "enabled": True, "seed": 9, "params": {}}
    e.update(kw)
    return {"version": 1, "effects": [e]}


def _ass(motion: dict | None, edits: dict | None = None) -> str:
    return captions.build_ass(PALAVRAS, {"preset": "clean"}, None,
                              clip_duration=2.2, fps=25.0, edits=edits, motion=motion)


def _png(tmp: Path, nome: str, motion: dict | None, t: float) -> np.ndarray:
    (tmp / f"{nome}.ass").write_text(_ass(motion), encoding="utf-8")
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


def test_contrato_text_props_continua_fiel_ao_catalogo():
    """Se um preset do catálogo mudar, o contrato compartilhado PRECISA ser
    regenerado — senão o preview TS animaria uma curva antiga."""
    tp = CASES["text_props"]
    for pid, preset in tp["presets"].items():
        assert motion_text.TEXT_PRESETS[pid] == preset, \
            f"preset '{pid}' divergiu do contrato — regenere shared/motion-cases.json"
    for c in tp["cases"]:
        got = motion_text.text_props_at(c["effect"], tp["presets"][c["preset"]], c["t"])
        for prop, v in c["props"].items():
            assert got[prop] == pytest.approx(v, abs=1e-12), f"{c['preset']}@{c['t']}s {prop}"


def test_compila_overlay_proprio_e_esconde_a_palavra_no_base():
    """A palavra enfatizada vira um EVENTO overlay (layer 2) com a curva
    amostrada; no cartão base ela fica invisível durante a janela — é isso
    que garante que as vizinhas não se movem."""
    ass = _ass(_manifest())
    overlay = next(x for x in ass.splitlines() if x.startswith("Dialogue: 2"))
    assert overlay.count("\\t(") >= 4, "curva amostrada em passos encadeados"
    assert "\\fscx" in overlay and "AQUI" in overlay
    assert overlay.startswith("Dialogue: 2,0:00:00.70,0:00:01.40"), \
        "overlay dura exatamente a janela do efeito"
    assert "{\\alpha&HFF&}ISSO" in overlay, "vizinha invisível mantém o layout"

    base = next(x for x in ass.splitlines() if x.startswith("Dialogue: 0"))
    alvo = base.split("AQUI")[0].split("ISSO")[1]
    assert "\\alpha&HFF&" in alvo, "palavra escondida no base durante o efeito"
    assert "\\fscx" not in alvo, "nenhuma escala inline no cartão base"


def test_manifest_tem_precedencia_sobre_a_enfase_classica():
    edits = {"word_emphasis": [{"idx": [1], "effect": "pop"}]}
    so_v3 = _ass(None, edits=edits)
    com_motion = _ass(_manifest("pop_clean"), edits=edits)
    assert "\\fscx118" in so_v3.split("AQUI")[0], "sozinha, a ênfase clássica anima"
    base_mo = next(x for x in com_motion.splitlines() if x.startswith("Dialogue: 0"))
    assert "\\fscx118" not in base_mo.split("AQUI")[0], \
        "com Motion na mesma palavra, a ênfase clássica sai de cena"
    assert any(x.startswith("Dialogue: 2") for x in com_motion.splitlines())


def test_efeito_desabilitado_e_preset_desconhecido_nao_geram_tags():
    """Entrega 141 (desabilitar sem excluir) e 81 (preset futuro não quebra)."""
    for man in (_manifest(enabled=False), _manifest(preset="preset_do_futuro_v9")):
        ass = _ass(man)
        assert not any(x.startswith("Dialogue: 2") for x in ass.splitlines()), \
            "sem overlay — mas o render continua saindo"
        base = next(x for x in ass.splitlines() if x.startswith("Dialogue: 0"))
        assert "\\alpha&HFF&" not in base, "palavra não é escondida sem efeito ativo"


def test_render_do_manifest_e_deterministico():
    """Entrega 47: mesmo manifest (mesma seed) → mesmo ASS, byte a byte."""
    a = _ass(_manifest())
    b = _ass(_manifest())
    assert a == b


def test_pixels_palavra_cresce_no_pico_e_baseline_nao_move(tmp_path):
    """O punch aumenta a tinta da palavra no ataque e some no fim — e o TOPO
    das palavras vizinhas não mexe (linha de leitura estável, Entrega 93)."""
    t_pico = PALAVRAS[1]["start_s"] + 0.07   # dentro do ENTER
    sem = _png(tmp_path, "sem", None, t_pico)
    com = _png(tmp_path, "com", _manifest(), t_pico)
    tinta_sem = int((sem > 60).sum())
    tinta_com = int((com > 60).sum())
    assert tinta_com > tinta_sem * 1.12, (tinta_sem, tinta_com)

    # topo da PRIMEIRA palavra (faixa esquerda) — não pode se mover
    def topo(arr):
        faixa = arr[:, : arr.shape[1] // 3]
        ys = np.nonzero((faixa > 60).any(axis=1))[0]
        return int(ys[0]) if len(ys) else -1

    assert abs(topo(sem) - topo(com)) <= 2, "vizinha não pode subir/descer"

    # bem depois do fim do efeito, os frames voltam a ser praticamente iguais
    t_fim = 1.55  # efeito termina em 1.40; o cartão vai até 1.77
    sem2 = _png(tmp_path, "sem2", None, t_fim)
    com2 = _png(tmp_path, "com2", _manifest(), t_fim)
    diff = np.abs(sem2 - com2)
    assert (diff > 40).sum() < sem2.size * 0.002, "efeito não pode vazar além do fim"


def test_janela_curta_comprime_as_fases_sem_quebrar():
    e = _manifest()["effects"][0]
    e["start"], e["end"] = 1.0, 1.12  # 120ms — menor que enter+exit nominais
    p = motion_text.TEXT_PRESETS["punch"]
    vals = [motion_text.text_props_at(e, p, 1.0 + i * 0.02)["scale"] for i in range(6)]
    assert max(vals) > 110, "mesmo curto, o ataque acontece"
    assert motion_text.text_props_at(e, p, 1.13)["scale"] == 100.0
    ov = motion_text.overlay_line(e, p, {"outline": 3}, ["UM", "DOIS"], set(), {0},
                                  ev_start=0.9, ev_end=1.4, fps=25.0,
                                  ts=captions._ts)
    assert ov and ov.count("\\t(") >= 2
