"""v4 FASE E — Text Callout / Typography Takeover.

Prova com libass/ffmpeg reais: o callout toma a tela (texto no centro, fundo
escurecido), a legenda base SOME na janela (nada duplicado) e volta depois;
stack empilha com stagger; posição é livre; tudo determinístico.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from app.pipeline import captions, motion_callout
from app.services import ffmpeg

PAL = [{"idx": i, "start_s": 0.2 + i * 0.5, "end_s": 0.2 + i * 0.5 + 0.45, "word": w}
       for i, w in enumerate(["você", "não", "tem", "flow"])]


def _man(preset: str = "battle_final", **kw) -> dict:
    e = {"id": "co1", "type": "text_callout", "preset": preset,
         "target": {"kind": "words", "idx": [0, 1, 2, 3]},
         "start": 0.5, "end": 2.0, "intensity": "normal", "enabled": True,
         "seed": 4, "params": {}}
    e.update(kw)
    return {"version": 1, "effects": [e]}


def _ass(man: dict | None) -> str:
    return captions.build_ass(PAL, {"preset": "bold_karaoke"}, None,
                              clip_duration=2.4, fps=30.0, motion=man)


def _png(tmp: Path, nome: str, man: dict | None, t: float,
         com_bg: bool = False) -> np.ndarray:
    (tmp / f"{nome}.ass").write_text(_ass(man), encoding="utf-8")
    vf = f"ass={nome}.ass"
    if com_bg and man:
        chains = [c for e, pr in motion_callout.collect(man)
                  if (c := motion_callout.background_chain(e, pr, 540, 960))]
        if chains:
            vf = ",".join(chains) + "," + vf
    r = subprocess.run(
        [ffmpeg.find_binary("ffmpeg"), "-hide_banner", "-loglevel", "warning", "-y",
         "-f", "lavfi", "-i", "testsrc2=s=540x960:r=30:d=2.4",
         "-vf", vf, "-ss", f"{t}", "-frames:v", "1", str(tmp / f"{nome}.png")],
        cwd=tmp, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "Unknown" not in r.stderr, r.stderr
    from PIL import Image  # noqa: PLC0415

    return np.asarray(Image.open(tmp / f"{nome}.png").convert("L"), dtype=np.int16)


def test_catalogo_completo_e_declarativo():
    assert set(motion_callout.CALLOUT_PRESETS) == {
        "center_impact", "build_up", "final_word", "stack", "wide_slam",
        "dark_punch", "battle_final"}
    for pid, p in motion_callout.CALLOUT_PRESETS.items():
        assert p["id"] == pid and p["label"] and p["descricao"]
        assert p["layout"] in ("stack", "line")
        assert p["bg"] in motion_callout.BACKGROUNDS
        assert p["phases"].get("enter"), pid


def test_stack_empilha_com_stagger_e_ultima_linha_maior():
    ass = _ass(_man("battle_final"))
    eventos = [x for x in ass.splitlines() if x.startswith("Dialogue: 3")]
    assert len(eventos) == 4, "uma linha por palavra (stack)"
    starts = [x.split(",")[1] for x in eventos]
    assert starts == sorted(starts) and len(set(starts)) == 4, "entradas escalonadas"
    ys = [float(x.split("\\pos(")[1].split(")")[0].split(",")[1]) for x in eventos]
    assert ys == sorted(ys), "linhas empilhadas de cima para baixo"
    fs = [int(x.split("\\fs")[1].split("\\")[0]) for x in eventos]
    assert fs[-1] > fs[0], "última palavra maior (Battle Final)"
    assert "&H002D2DFF" in eventos[-1], "última palavra vermelha"


def test_takeover_esconde_a_legenda_base_na_janela():
    ass = _ass(_man())
    base = next(x for x in ass.splitlines() if x.startswith("Dialogue: 0"))
    assert "\\t(300,300,\\alpha&HFF&)" in base, "some quando o callout entra"
    assert "\\t(1800,1800,\\alpha&H00&)" in base, "volta quando o callout sai"
    sem = _ass(None)
    base_sem = next(x for x in sem.splitlines() if x.startswith("Dialogue: 0"))
    assert "\\alpha&HFF&" not in base_sem


def test_posicao_livre_e_persistida_em_params():
    ass = _ass(_man("center_impact", params={"pos_x": 0.5, "pos_y": 0.25}))
    ev = next(x for x in ass.splitlines() if x.startswith("Dialogue: 3"))
    assert "\\pos(540,480)" in ev, "pos_y 0.25 de 1920 → 480"


def test_background_chains_por_tipo():
    darken = motion_callout.background_chain(
        _man("center_impact")["effects"][0],
        motion_callout.CALLOUT_PRESETS["center_impact"], 540, 960)
    assert "eq=brightness=-0.32" in darken and "between(t,0.500,2.000)" in darken
    preto = motion_callout.background_chain(
        _man("dark_punch")["effects"][0],
        motion_callout.CALLOUT_PRESETS["dark_punch"], 540, 960)
    assert "drawbox" in preto and "black@0.94" in preto
    nenhum = motion_callout.background_chain(
        _man("stack")["effects"][0], motion_callout.CALLOUT_PRESETS["stack"], 540, 960)
    assert nenhum is None
    # override do usuário: params.bg troca o fundo do preset
    blur = motion_callout.background_chain(
        _man("stack", params={"bg": "blur"})["effects"][0],
        motion_callout.CALLOUT_PRESETS["stack"], 540, 960)
    assert "gblur" in blur


def test_determinismo_e_desabilitado():
    assert _ass(_man()) == _ass(_man())
    ass_off = _ass(_man(enabled=False))
    assert not any(x.startswith("Dialogue: 3") for x in ass_off.splitlines())
    assert "\\alpha&HFF&" not in next(
        x for x in ass_off.splitlines() if x.startswith("Dialogue: 0"))


def test_pixels_takeover_real(tmp_path):
    """Render de verdade: durante o callout o centro tem texto grande e a
    região da legenda fica SEM tinta de legenda; fora da janela, tela normal."""
    man = _man("center_impact")
    # centro da tela: callout presente no meio da janela
    com = _png(tmp_path, "com", man, t=1.2, com_bg=True)
    sem = _png(tmp_path, "sem", None, t=1.2)
    centro_com = com[860 // 2 - 90: 860 // 2 + 90, :]
    centro_sem = sem[860 // 2 - 90: 860 // 2 + 90, :]
    # o callout desenha MUITO texto claro com borda escura no centro
    diff_centro = float(np.mean(np.abs(centro_com.astype(np.float64)
                                       - centro_sem.astype(np.float64))))
    assert diff_centro > 8.0, "callout deveria dominar o centro"

    # região da LEGENDA (âncora ~1180/1920 → ~590/960): a base sumiu
    faixa_com = com[560:700, :]
    faixa_sem = sem[560:700, :]
    tinta_com = int((faixa_com > 200).sum())  # texto branco brilhante
    tinta_sem = int((faixa_sem > 200).sum())
    assert tinta_sem > 400, "sem callout, a legenda está lá"
    assert tinta_com < tinta_sem * 0.35, "com callout, a legenda base saiu de cena"

    # fundo escurecido: média global menor durante o takeover
    assert com.mean() < sem.mean() - 8

    # DEPOIS do callout (2.0s): tela volta ao normal
    dep_com = _png(tmp_path, "dep_com", man, t=2.2, com_bg=True)
    dep_sem = _png(tmp_path, "dep_sem", None, t=2.2)
    assert float(np.mean(np.abs(dep_com.astype(np.float64)
                                - dep_sem.astype(np.float64)))) < 2.0
