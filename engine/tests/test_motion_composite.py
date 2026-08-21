"""v4 FASE G — composições: a Fatality comanda texto + vídeo + cena.

O arco SETUP→BUILD→HIT→RECOVERY (Entrega 109) é verificado avaliando a
timeline expandida com as MESMAS funções do render: antes do golpe só o zoom
arma; no hit o texto estoura com a pancada de câmera; no pico o RGB rasga;
depois do fim, neutro absoluto.
"""

from __future__ import annotations

import pytest

from app.pipeline import captions, motion, motion_composite, motion_text, motion_video

ALVO = {"kind": "words", "idx": [2]}


def _expande(intensity="normal", t_hit=2.0, seed=77):
    return motion_composite.expand_composite(
        "fatality_composta", t_hit=t_hit, dur_word=0.45, target=ALVO,
        intensity=intensity, seed_base=seed)


def test_expande_em_efeitos_reais_vinculados_por_grupo():
    efeitos = _expande()
    assert len(efeitos) == 5  # normal: sem o flash (só Forte)
    grupos = {e["group"] for e in efeitos}
    assert len(grupos) == 1, "todas as partes carregam o mesmo grupo"
    assert all(e["group_label"] == "Fatality" for e in efeitos)
    # o manifest normaliza sem reclamar (chaves extras preservadas)
    man = motion.validate_manifest({"effects": efeitos})
    assert len(man["effects"]) == 5
    assert all(e.get("group") for e in man["effects"])


def test_arco_setup_build_hit_recovery():
    """A linha do tempo da Entrega 109, medida com as funções do render."""
    efeitos = {e["preset"]: e for e in _expande(t_hit=2.0)}
    zoom = efeitos["punch_zoom"]
    texto = efeitos["fatality"]
    shake = efeitos["impact_shake"]
    rgb = efeitos["rgb_split"]
    assert zoom["start"] == pytest.approx(1.7), "zoom arma 300ms ANTES do hit"
    assert efeitos["darken"]["start"] == pytest.approx(1.85)
    assert texto["start"] == pytest.approx(2.0), "texto no instante do golpe"
    assert shake["start"] == pytest.approx(2.04)
    assert rgb["start"] == pytest.approx(2.1)

    def vfx(e, t):
        return motion_video.video_props_at(e, motion_video.VIDEO_PRESETS[e["preset"]], t)

    # SETUP (t=1.8): zoom já subindo, cena ainda sem shake, sem texto
    assert vfx(zoom, 1.8)["zoom"] > 1.02
    assert vfx(shake, 1.8) == motion_video.VIDEO_NEUTRAL
    tprops = motion_text.text_props_at(texto, motion_text.TEXT_PRESETS["fatality"], 1.8)
    assert tprops == motion_text.NEUTRAL

    # HIT (+60ms): texto estourando E câmera na pancada
    tprops = motion_text.text_props_at(texto, motion_text.TEXT_PRESETS["fatality"], 2.06)
    assert tprops["scale"] > 125
    assert abs(vfx(shake, 2.06)["dx"]) + abs(vfx(shake, 2.06)["dy"]) > 2.0

    # PICO RGB (+150ms)
    assert vfx(rgb, 2.15)["rgb"] > 0

    # RECOVERY: bem depois do fim, TUDO neutro
    t_fim = max(e["end"] for e in efeitos.values()) + 0.05
    for e in efeitos.values():
        if e["type"] == "video_fx":
            assert vfx(e, t_fim) == motion_video.VIDEO_NEUTRAL
        else:
            assert motion_text.text_props_at(
                e, motion_text.TEXT_PRESETS["fatality"], t_fim) == motion_text.NEUTRAL


def test_intensidade_muda_a_composicao_nao_so_a_amplitude():
    """Suave = menos partes (sem RGB); Forte = tudo + flash (Entrega 5)."""
    suave = {e["preset"] for e in _expande("suave")}
    normal = {e["preset"] for e in _expande("normal")}
    forte = {e["preset"] for e in _expande("forte")}
    assert "rgb_split" not in suave and "rgb_split" in normal
    assert "flash" not in normal and "flash" in forte
    assert suave < normal < forte


def test_determinismo_e_variacao_por_seed():
    a = _expande(seed=77)
    b = _expande(seed=77)
    for x, y in zip(a, b, strict=True):
        assert x["seed"] == y["seed"] and x["start"] == y["start"]
    c = _expande(seed=78)
    assert [x["seed"] for x in a] != [x["seed"] for x in c]
    # ids/grupos são únicos por criação (uuid), mas o MOVIMENTO é a seed
    assert a[0]["group"] != b[0]["group"]


def test_golpe_no_inicio_do_corte_clampa_em_zero():
    efeitos = _expande(t_hit=0.1)
    assert min(e["start"] for e in efeitos) == 0.0
    assert all(e["end"] > e["start"] for e in efeitos)


def test_composicao_compila_de_ponta_a_ponta():
    """As partes expandidas passam juntas pelo compilador de texto (ASS) e
    pelo de vídeo (filtergraph) — nada conflita."""
    palavras = [{"idx": i, "start_s": 0.5 + i * 0.6, "end_s": 0.5 + i * 0.6 + 0.45,
                 "word": w} for i, w in enumerate(["essa", "rima", "MATOU"])]
    efeitos = motion_composite.expand_composite(
        "fatality_composta", t_hit=1.7, dur_word=0.45,
        target={"kind": "words", "idx": [2]}, intensity="forte", seed_base=9)
    man = motion.validate_manifest({"effects": efeitos})
    ass = captions.build_ass(palavras, {"preset": "bold_karaoke"}, None,
                             clip_duration=2.6, fps=30.0, motion=man)
    assert any(x.startswith("Dialogue: 2") for x in ass.splitlines()), \
        "overlay do texto Fatality presente"
    chains = motion_video.compile_video_fx(man, 1080, 1920)
    assert len(chains) == 5, "zoom + darken + shake + rgb + flash no grafo"
    assert chains == motion_video.compile_video_fx(man, 1080, 1920)
