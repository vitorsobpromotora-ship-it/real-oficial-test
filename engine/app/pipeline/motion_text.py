"""Text Motion Core (v4 FASE C) — presets declarativos de texto e o compilador
manifest → ASS.

PRESET É DADO: cada preset descreve as 3 fases ENTER → HOLD → EXIT como
trilhas de keyframes por propriedade (Entregas 3, 55–57). Não existe
renderPop()/renderFatality() — o mesmo dicionário alimenta:

  1. `text_props_at()` — avaliação pura das propriedades em qualquer t
     (o preview do Editor espelha esta função em TS; a paridade é provada
     pelo bloco "text_props" de shared/motion-cases.json);
  2. `compile_text_tags()` — amostra text_props_at em passos de ~1 frame e
     emite `\\t` lineares encadeados no ASS: o render materializa a MESMA
     curva que o canvas mostra, com erro ≤ 1 frame (Entrega 60).

Convenção das fases: trilha ausente numa fase = valor NEUTRO. Presets bem
formados terminam o ENTER onde o HOLD começa e voltam ao neutro no fim
(o reset após a palavra é só cinto de segurança, como na ênfase v3).

Propriedades animáveis (v1, seguras inline no ASS — não deslocam a linha de
leitura; deslocamento por palavra é privilégio dos Callouts, eventos próprios):
  scale (%, 100=neutro) · blur (px) · rot (graus, clamp ±5) ·
  bord (DELTA px sobre o outline do estilo) · alpha (0..1, 0=opaco)
Jitter procedural: fase "hold" pode ter {"jitter": {"rot": amp, "freq": hz}}
— rotação por shake_offset(t, seed): mesma seed, mesmo tremor.
"""

from __future__ import annotations

from . import motion
from .captions import hex_to_ass

# ---------------------------------------------------------------------------
# Catálogo declarativo (FASE C: núcleo com 2 presets; o pack chega na FASE D)
# ---------------------------------------------------------------------------

TEXT_PRESETS: dict[str, dict] = {
    # ------------------------------ Básicos ------------------------------
    "pop_clean": {
        "id": "pop_clean", "label": "Pop Clean", "categoria": "Básicos",
        "descricao": "Crescimento rápido e assentamento suave — ênfase limpa.",
        "phases": {
            "enter": {"dur_ms": 170, "tracks": {
                "scale": [{"t": 0.0, "v": 100.0},
                          {"t": 0.55, "v": 117.0, "ease": "rapido"},
                          {"t": 1.0, "v": 106.0, "ease": "suave"}],
            }},
            "hold": {"tracks": {
                "scale": [{"t": 0.0, "v": 106.0}, {"t": 1.0, "v": 106.0}],
            }},
            "exit": {"dur_ms": 140, "tracks": {
                "scale": [{"t": 0.0, "v": 106.0}, {"t": 1.0, "v": 100.0, "ease": "suave"}],
            }},
        },
    },
    "pop_elastic": {
        "id": "pop_elastic", "label": "Pop Elástico", "categoria": "Básicos",
        "descricao": "Pop com quique elástico no assentamento.",
        "phases": {
            "enter": {"dur_ms": 320, "tracks": {
                "scale": [{"t": 0.0, "v": 100.0},
                          {"t": 0.22, "v": 126.0, "ease": "rapido"},
                          {"t": 1.0, "v": 108.0, "ease": "elastico"}],
            }},
            "hold": {"tracks": {
                "scale": [{"t": 0.0, "v": 108.0}, {"t": 1.0, "v": 108.0}],
            }},
            "exit": {"dur_ms": 150, "tracks": {
                "scale": [{"t": 0.0, "v": 108.0}, {"t": 1.0, "v": 100.0, "ease": "suave"}],
            }},
        },
    },
    "color_pop": {
        "id": "color_pop", "label": "Color Pop", "categoria": "Básicos",
        "descricao": "A palavra acende numa cor de destaque com um pop leve.",
        "color": "#FFD400",
        "phases": {
            "enter": {"dur_ms": 130, "tracks": {
                "scale": [{"t": 0.0, "v": 100.0},
                          {"t": 0.6, "v": 112.0, "ease": "rapido"},
                          {"t": 1.0, "v": 106.0, "ease": "suave"}],
            }},
            "hold": {"tracks": {
                "scale": [{"t": 0.0, "v": 106.0}, {"t": 1.0, "v": 106.0}],
            }},
            "exit": {"dur_ms": 160, "tracks": {
                "scale": [{"t": 0.0, "v": 106.0}, {"t": 1.0, "v": 100.0, "ease": "suave"}],
            }},
        },
    },
    "flash_word": {
        "id": "flash_word", "label": "Flash Word", "categoria": "Básicos",
        "descricao": "Clarão branco instantâneo que assenta na cor normal.",
        "color": "#FFFFFF",
        "phases": {
            "enter": {"dur_ms": 200, "tracks": {
                "scale": [{"t": 0.0, "v": 108.0}, {"t": 1.0, "v": 105.0, "ease": "rapido"}],
                "blur": [{"t": 0.0, "v": 6.0}, {"t": 0.35, "v": 0.0, "ease": "rapido"},
                         {"t": 1.0, "v": 0.0}],
                "bord": [{"t": 0.0, "v": 4.0}, {"t": 1.0, "v": 0.5, "ease": "rapido"}],
            }},
            "hold": {"tracks": {
                "scale": [{"t": 0.0, "v": 105.0}, {"t": 1.0, "v": 105.0}],
            }},
            "exit": {"dur_ms": 130, "tracks": {
                "scale": [{"t": 0.0, "v": 105.0}, {"t": 1.0, "v": 100.0, "ease": "suave"}],
            }},
        },
    },
    # ------------------------------ Impacto ------------------------------
    "punch": {
        "id": "punch", "label": "Punch", "categoria": "Impacto",
        "descricao": "Soco seco: estoura no ataque e volta com overshoot.",
        "phases": {
            "enter": {"dur_ms": 210, "tracks": {
                "scale": [{"t": 0.0, "v": 100.0},
                          {"t": 0.28, "v": 138.0, "ease": "rapido"},
                          {"t": 1.0, "v": 108.0, "ease": "impacto"}],
                "bord": [{"t": 0.0, "v": 0.0},
                         {"t": 0.28, "v": 3.0, "ease": "rapido"},
                         {"t": 1.0, "v": 1.0, "ease": "suave"}],
                "blur": [{"t": 0.0, "v": 2.4, "ease": "linear"},
                         {"t": 0.3, "v": 0.0, "ease": "rapido"},
                         {"t": 1.0, "v": 0.0}],
            }},
            "hold": {"tracks": {
                "scale": [{"t": 0.0, "v": 108.0}, {"t": 1.0, "v": 108.0}],
                "bord": [{"t": 0.0, "v": 1.0}, {"t": 1.0, "v": 1.0}],
            }},
            "exit": {"dur_ms": 150, "tracks": {
                "scale": [{"t": 0.0, "v": 108.0}, {"t": 1.0, "v": 100.0, "ease": "suave"}],
                "bord": [{"t": 0.0, "v": 1.0}, {"t": 1.0, "v": 0.0, "ease": "suave"}],
            }},
        },
    },
    "slam": {
        "id": "slam", "label": "Slam", "categoria": "Impacto",
        "descricao": "Cai GRANDE de cima e crava no lugar, com poeira de blur.",
        "phases": {
            "enter": {"dur_ms": 190, "tracks": {
                "scale": [{"t": 0.0, "v": 168.0},
                          {"t": 0.45, "v": 96.0, "ease": "rapido"},
                          {"t": 1.0, "v": 108.0, "ease": "impacto"}],
                "blur": [{"t": 0.0, "v": 7.0},
                         {"t": 0.5, "v": 0.0, "ease": "rapido"}, {"t": 1.0, "v": 0.0}],
                "rot": [{"t": 0.0, "v": -2.5},
                        {"t": 1.0, "v": 0.0, "ease": "impacto"}],
            }},
            "hold": {"tracks": {
                "scale": [{"t": 0.0, "v": 108.0}, {"t": 1.0, "v": 108.0}],
            }},
            "exit": {"dur_ms": 140, "tracks": {
                "scale": [{"t": 0.0, "v": 108.0}, {"t": 1.0, "v": 100.0, "ease": "suave"}],
            }},
        },
    },
    "outline_burst": {
        "id": "outline_burst", "label": "Outline Burst", "categoria": "Impacto",
        "descricao": "A borda explode grossa e recolhe — impacto sem crescer muito.",
        "phases": {
            "enter": {"dur_ms": 220, "tracks": {
                "scale": [{"t": 0.0, "v": 100.0},
                          {"t": 0.4, "v": 110.0, "ease": "rapido"},
                          {"t": 1.0, "v": 106.0, "ease": "suave"}],
                "bord": [{"t": 0.0, "v": 0.0},
                         {"t": 0.35, "v": 8.0, "ease": "rapido"},
                         {"t": 1.0, "v": 1.5, "ease": "suave"}],
            }},
            "hold": {"tracks": {
                "scale": [{"t": 0.0, "v": 106.0}, {"t": 1.0, "v": 106.0}],
                "bord": [{"t": 0.0, "v": 1.5}, {"t": 1.0, "v": 1.5}],
            }},
            "exit": {"dur_ms": 150, "tracks": {
                "scale": [{"t": 0.0, "v": 106.0}, {"t": 1.0, "v": 100.0, "ease": "suave"}],
                "bord": [{"t": 0.0, "v": 1.5}, {"t": 1.0, "v": 0.0, "ease": "suave"}],
            }},
        },
    },
    "word_stretch": {
        "id": "word_stretch", "label": "Word Stretch", "categoria": "Impacto",
        "descricao": "Estica horizontal no ataque e volta ao normal — groove de batida.",
        "phases": {
            "enter": {"dur_ms": 240, "tracks": {
                "scale_x": [{"t": 0.0, "v": 100.0},
                            {"t": 0.25, "v": 148.0, "ease": "rapido"},
                            {"t": 0.75, "v": 106.0, "ease": "suave"},
                            {"t": 1.0, "v": 112.0, "ease": "elastico"}],
                "scale_y": [{"t": 0.0, "v": 100.0},
                            {"t": 0.25, "v": 92.0, "ease": "rapido"},
                            {"t": 0.75, "v": 102.0, "ease": "suave"},
                            {"t": 1.0, "v": 104.0, "ease": "elastico"}],
            }},
            "hold": {"tracks": {
                "scale_x": [{"t": 0.0, "v": 112.0}, {"t": 1.0, "v": 112.0}],
                "scale_y": [{"t": 0.0, "v": 104.0}, {"t": 1.0, "v": 104.0}],
            }},
            "exit": {"dur_ms": 150, "tracks": {
                "scale_x": [{"t": 0.0, "v": 112.0}, {"t": 1.0, "v": 100.0, "ease": "suave"}],
                "scale_y": [{"t": 0.0, "v": 104.0}, {"t": 1.0, "v": 100.0, "ease": "suave"}],
            }},
        },
    },
    # ------------------------------ Batalha ------------------------------
    "fatality": {
        "id": "fatality", "label": "Fatality", "categoria": "Batalha",
        "descricao": "O golpe final: estoura vermelho, treme contido e assenta pesado.",
        "color": "#FF2D2D",
        "phases": {
            "enter": {"dur_ms": 240, "tracks": {
                "scale": [{"t": 0.0, "v": 100.0},
                          {"t": 0.3, "v": 152.0, "ease": "rapido"},
                          {"t": 1.0, "v": 118.0, "ease": "impacto"}],
                "bord": [{"t": 0.0, "v": 0.0},
                         {"t": 0.3, "v": 5.0, "ease": "rapido"},
                         {"t": 1.0, "v": 2.0, "ease": "suave"}],
                "blur": [{"t": 0.0, "v": 5.0},
                         {"t": 0.35, "v": 0.0, "ease": "rapido"}, {"t": 1.0, "v": 0.0}],
            }},
            "hold": {"jitter": {"rot": 1.6, "freq": 10.0}, "tracks": {
                "scale": [{"t": 0.0, "v": 118.0}, {"t": 1.0, "v": 118.0}],
                "bord": [{"t": 0.0, "v": 2.0}, {"t": 1.0, "v": 2.0}],
            }},
            "exit": {"dur_ms": 180, "tracks": {
                "scale": [{"t": 0.0, "v": 118.0}, {"t": 1.0, "v": 100.0, "ease": "suave"}],
                "bord": [{"t": 0.0, "v": 2.0}, {"t": 1.0, "v": 0.0, "ease": "suave"}],
            }},
        },
    },
    "diss": {
        "id": "diss", "label": "Diss", "categoria": "Batalha",
        "descricao": "Provocação: inclina com deboche e segura o olhar.",
        "color": "#FF9F1C",
        "phases": {
            "enter": {"dur_ms": 200, "tracks": {
                "scale": [{"t": 0.0, "v": 100.0},
                          {"t": 0.45, "v": 122.0, "ease": "rapido"},
                          {"t": 1.0, "v": 112.0, "ease": "suave"}],
                "rot": [{"t": 0.0, "v": 0.0},
                        {"t": 0.5, "v": -3.4, "ease": "rapido"},
                        {"t": 1.0, "v": -2.6, "ease": "suave"}],
            }},
            "hold": {"tracks": {
                "scale": [{"t": 0.0, "v": 112.0}, {"t": 1.0, "v": 112.0}],
                "rot": [{"t": 0.0, "v": -2.6}, {"t": 1.0, "v": -2.6}],
            }},
            "exit": {"dur_ms": 160, "tracks": {
                "scale": [{"t": 0.0, "v": 112.0}, {"t": 1.0, "v": 100.0, "ease": "suave"}],
                "rot": [{"t": 0.0, "v": -2.6}, {"t": 1.0, "v": 0.0, "ease": "suave"}],
            }},
        },
    },
    "bass_hit": {
        "id": "bass_hit", "label": "Bass Hit", "categoria": "Batalha",
        "descricao": "Bomba do grave: infla na vertical e pulsa dois batimentos.",
        "phases": {
            "enter": {"dur_ms": 120, "tracks": {
                "scale_x": [{"t": 0.0, "v": 100.0},
                            {"t": 1.0, "v": 104.0, "ease": "rapido"}],
                "scale_y": [{"t": 0.0, "v": 100.0},
                            {"t": 1.0, "v": 122.0, "ease": "rapido"}],
            }},
            "hold": {"tracks": {
                "scale_x": [{"t": 0.0, "v": 104.0}, {"t": 1.0, "v": 104.0}],
                "scale_y": [{"t": 0.0, "v": 122.0},
                            {"t": 0.25, "v": 130.0, "ease": "rapido"},
                            {"t": 0.5, "v": 118.0, "ease": "suave"},
                            {"t": 0.75, "v": 127.0, "ease": "rapido"},
                            {"t": 1.0, "v": 122.0, "ease": "suave"}],
                "blur": [{"t": 0.0, "v": 0.0}, {"t": 0.25, "v": 1.6, "ease": "rapido"},
                         {"t": 0.5, "v": 0.0, "ease": "suave"},
                         {"t": 0.75, "v": 1.4, "ease": "rapido"},
                         {"t": 1.0, "v": 0.0, "ease": "suave"}],
            }},
            "exit": {"dur_ms": 140, "tracks": {
                "scale_x": [{"t": 0.0, "v": 104.0},
                            {"t": 1.0, "v": 100.0, "ease": "suave"}],
                "scale_y": [{"t": 0.0, "v": 122.0},
                            {"t": 1.0, "v": 100.0, "ease": "suave"}],
            }},
        },
    },
    "knockout": {
        "id": "knockout", "label": "Knockout", "categoria": "Batalha",
        "descricao": "Nocaute: entra gigante torto e crava sem dó.",
        "outline_color": "#000000",
        "phases": {
            "enter": {"dur_ms": 230, "tracks": {
                "scale": [{"t": 0.0, "v": 178.0},
                          {"t": 0.4, "v": 104.0, "ease": "rapido"},
                          {"t": 1.0, "v": 116.0, "ease": "impacto"}],
                "rot": [{"t": 0.0, "v": -4.2},
                        {"t": 0.6, "v": 1.4, "ease": "rapido"},
                        {"t": 1.0, "v": -1.0, "ease": "suave"}],
                "bord": [{"t": 0.0, "v": 5.0}, {"t": 1.0, "v": 2.0, "ease": "rapido"}],
                "blur": [{"t": 0.0, "v": 8.0},
                         {"t": 0.45, "v": 0.0, "ease": "rapido"}, {"t": 1.0, "v": 0.0}],
            }},
            "hold": {"tracks": {
                "scale": [{"t": 0.0, "v": 116.0}, {"t": 1.0, "v": 116.0}],
                "rot": [{"t": 0.0, "v": -1.0}, {"t": 1.0, "v": -1.0}],
                "bord": [{"t": 0.0, "v": 2.0}, {"t": 1.0, "v": 2.0}],
            }},
            "exit": {"dur_ms": 170, "tracks": {
                "scale": [{"t": 0.0, "v": 116.0}, {"t": 1.0, "v": 100.0, "ease": "suave"}],
                "rot": [{"t": 0.0, "v": -1.0}, {"t": 1.0, "v": 0.0, "ease": "suave"}],
                "bord": [{"t": 0.0, "v": 2.0}, {"t": 1.0, "v": 0.0, "ease": "suave"}],
            }},
        },
    },
    # ------------------------------ Glitch ------------------------------
    "glitch_snap": {
        "id": "glitch_snap", "label": "Glitch Snap", "categoria": "Glitch",
        "descricao": "Pisca e range como sinal ruim antes de estabilizar.",
        "outline_color": "#00E5FF",
        "phases": {
            "enter": {"dur_ms": 260, "tracks": {
                "alpha": [{"t": 0.0, "v": 0.0}, {"t": 0.12, "v": 0.7},
                          {"t": 0.2, "v": 0.0}, {"t": 0.34, "v": 0.55},
                          {"t": 0.44, "v": 0.0}, {"t": 1.0, "v": 0.0}],
                "scale": [{"t": 0.0, "v": 104.0},
                          {"t": 0.5, "v": 112.0, "ease": "rapido"},
                          {"t": 1.0, "v": 108.0, "ease": "suave"}],
                "bord": [{"t": 0.0, "v": 2.5}, {"t": 1.0, "v": 1.0, "ease": "rapido"}],
            }},
            "hold": {"jitter": {"rot": 0.9, "freq": 16.0}, "tracks": {
                "scale": [{"t": 0.0, "v": 108.0}, {"t": 1.0, "v": 108.0}],
                "bord": [{"t": 0.0, "v": 1.0}, {"t": 1.0, "v": 1.0}],
            }},
            "exit": {"dur_ms": 140, "tracks": {
                "scale": [{"t": 0.0, "v": 108.0}, {"t": 1.0, "v": 100.0, "ease": "suave"}],
                "bord": [{"t": 0.0, "v": 1.0}, {"t": 1.0, "v": 0.0, "ease": "suave"}],
            }},
        },
    },
    # ----------------------------- Elegantes -----------------------------
    "soft_impact": {
        "id": "soft_impact", "label": "Soft Impact", "categoria": "Elegantes",
        "descricao": "Presença sem grito: cresce pouco, entra de leve, sai de leve.",
        "phases": {
            "enter": {"dur_ms": 260, "tracks": {
                "scale": [{"t": 0.0, "v": 100.0},
                          {"t": 1.0, "v": 107.0, "ease": "suave"}],
                "blur": [{"t": 0.0, "v": 2.0}, {"t": 0.7, "v": 0.0, "ease": "suave"},
                         {"t": 1.0, "v": 0.0}],
            }},
            "hold": {"tracks": {
                "scale": [{"t": 0.0, "v": 107.0}, {"t": 1.0, "v": 107.0}],
            }},
            "exit": {"dur_ms": 220, "tracks": {
                "scale": [{"t": 0.0, "v": 107.0}, {"t": 1.0, "v": 100.0, "ease": "suave"}],
            }},
        },
    },
}

# propriedades cujo DESVIO do neutro escala com a intensidade
NEUTRAL = {"scale": 100.0, "scale_x": 100.0, "scale_y": 100.0,
           "blur": 0.0, "rot": 0.0, "bord": 0.0, "alpha": 0.0}
ROT_MAX = 5.0  # \frz gira em torno da âncora da LINHA — ângulo grande desloca a palavra


def preset_of(effect: dict) -> dict | None:
    """Preset do efeito; None para preset desconhecido (versão futura) —
    a palavra fica sem animação em vez de quebrar o render."""
    return TEXT_PRESETS.get(str(effect.get("preset") or ""))


# ---------------------------------------------------------------------------
# Avaliação pura — espelhada em app/src/editor/motion.ts (textPropsAt)
# ---------------------------------------------------------------------------


def _fase_em(preset: dict, t_ms: float, dur_ms: float) -> tuple[dict, float, float]:
    """(fase, u local 0..1, t_ms dentro da fase) para o instante t do efeito."""
    fases = preset.get("phases", {})
    enter = fases.get("enter") or {"dur_ms": 0, "tracks": {}}
    exit_ = fases.get("exit") or {"dur_ms": 0, "tracks": {}}
    hold = fases.get("hold") or {"tracks": {}}
    e_dur = min(float(enter.get("dur_ms", 0)), dur_ms * 0.5)
    x_dur = min(float(exit_.get("dur_ms", 0)), dur_ms * 0.3)
    if t_ms < e_dur:
        return enter, (t_ms / e_dur if e_dur > 0 else 1.0), t_ms
    if t_ms >= dur_ms - x_dur:
        rest = t_ms - (dur_ms - x_dur)
        return exit_, (rest / x_dur if x_dur > 0 else 1.0), rest
    h_dur = dur_ms - e_dur - x_dur
    rest = t_ms - e_dur
    return hold, (rest / h_dur if h_dur > 0 else 0.0), rest


def text_props_at(effect: dict, preset: dict, t_out: float) -> dict:
    """Propriedades da palavra no instante t (tempo de SAÍDA, segundos), já com
    intensidade aplicada e clamps de segurança. Fora da janela → neutro."""
    props = dict(NEUTRAL)
    start, end = float(effect["start"]), float(effect["end"])
    if not effect.get("enabled", True) or t_out < start or t_out >= end:
        return props
    dur_ms = (end - start) * 1000.0
    t_ms = (t_out - start) * 1000.0
    fase, u, t_fase_ms = _fase_em(preset, t_ms, dur_ms)
    k = motion.intensity_k(effect.get("intensity", "normal"))
    for prop, trilha in (fase.get("tracks") or {}).items():
        if prop not in NEUTRAL:
            continue  # propriedade de versão futura: ignorada com segurança
        v = motion.eval_keyframes(trilha, u)
        neutro = NEUTRAL[prop]
        props[prop] = neutro + (v - neutro) * (k if prop != "alpha" else 1.0)
    jitter = (fase.get("jitter") or {})
    if jitter.get("rot"):
        seed = int(effect.get("seed") or 1)
        _, _, rot = motion.shake_offset(t_fase_ms / 1000.0, seed, 0.0, 0.0,
                                        float(jitter["rot"]) * k,
                                        float(jitter.get("freq", 9.0)))
        props["rot"] += rot
    props["rot"] = max(-ROT_MAX, min(ROT_MAX, props["rot"]))
    for k_ in ("scale", "scale_x", "scale_y"):
        props[k_] = max(10.0, min(220.0, props[k_]))
    props["blur"] = max(0.0, min(24.0, props["blur"]))
    props["alpha"] = max(0.0, min(1.0, props["alpha"]))
    return props


# ---------------------------------------------------------------------------
# Compilador ASS — a palavra enfatizada vira um EVENTO OVERLAY próprio
# ---------------------------------------------------------------------------
# Escala inline muda o extent da LINHA no libass (as vizinhas desceriam no
# pico — medido em teste de pixels). Por isso o efeito é compilado como um
# Dialogue de layer alto com o MESMO texto do cartão, onde só a palavra alvo
# é visível e animada; no cartão base ela fica invisível durante a janela.
# As vizinhas ficam paradas por construção — e o mesmo mecanismo é a base
# dos Text Callouts (eventos próprios com \pos livre).


def _tags_de(props: dict, style: dict) -> str:
    bord_base = float(style.get("outline") or 3)
    # eixos separados (Word Stretch) têm precedência sobre a escala uniforme
    sx = props["scale_x"] if props["scale_x"] != 100.0 else props["scale"]
    sy = props["scale_y"] if props["scale_y"] != 100.0 else props["scale"]
    tags = (f"\\fscx{sx:.0f}\\fscy{sy:.0f}"
            f"\\bord{bord_base + props['bord']:.2g}")
    tags += f"\\blur{props['blur']:.2g}" if props["blur"] else "\\blur0"
    tags += f"\\frz{props['rot']:.2f}" if props["rot"] else "\\frz0"
    a = int(round(props["alpha"] * 255))
    tags += f"\\alpha&H{a:02X}&"
    return tags


def hide_word_tags(effect: dict, ev_start: float, ev_end: float) -> tuple[str, str]:
    """Tags que ESCONDEM a palavra no cartão base durante a janela do efeito
    (o overlay assume). O reset devolve alpha para as palavras seguintes."""
    start = max(float(effect["start"]), ev_start)
    end = min(float(effect["end"]), ev_end)
    a_ms = max(0, round((start - ev_start) * 1000))
    b_ms = max(0, round((end - ev_start) * 1000))
    if a_ms <= 0 and end >= ev_end - 1e-4:
        return "{\\alpha&HFF&}", "{\\alpha&H00&}"
    pre = (f"{{\\t({a_ms},{a_ms},\\alpha&HFF&)"
           f"\\t({b_ms},{b_ms},\\alpha&H00&)}}")
    return pre, "{\\alpha&H00&}"


def _anim_sampled(effect: dict, preset: dict, style: dict,
                  start: float, end: float, fps: float) -> str:
    """Sequência de \\t lineares encadeados amostrando text_props_at — tempos
    relativos a `start` (o início do evento overlay)."""
    passo_s = max(1.0 / max(fps, 10.0), 0.025)
    n = max(2, min(24, round((end - start) / passo_s)))
    partes = []
    for i in range(n):
        a = start + (end - start) * i / n
        b = start + (end - start) * (i + 1) / n
        # valor no FIM do passo; o \t interpola linearmente até lá — aproximação
        # linear por partes da curva real, erro ≤ 1 frame
        props = text_props_at(effect, preset, min(b, end - 1e-4))
        partes.append(f"\\t({round((a - start) * 1000)},{round((b - start) * 1000)},"
                      f"{_tags_de(props, style)})")
    return "".join(partes)


def overlay_line(effect: dict, preset: dict, style: dict, texts: list[str],
                 breaks: set[int], alvo: set[int], ev_start: float, ev_end: float,
                 fps: float, ts) -> str | None:
    """Evento overlay do efeito: mesmo texto/layout do cartão, palavras não-alvo
    invisíveis (mantêm o layout), alvo animada pelo preset. `ts` = formatador
    de timestamp (captions._ts)."""
    start = max(float(effect["start"]), ev_start)
    end = min(float(effect["end"]), ev_end)
    if end - start < 0.03 or not effect.get("enabled", True):
        return None
    cor_hex = (effect.get("params") or {}).get("color") or preset.get("color")
    cor = hex_to_ass(cor_hex) if cor_hex else None
    borda_hex = (effect.get("params") or {}).get("outline_color") \
        or preset.get("outline_color")
    borda = hex_to_ass(borda_hex) if borda_hex else None
    anim = _anim_sampled(effect, preset, style, start, end, fps)
    partes: list[str] = []
    for i, text in enumerate(texts):
        sep = "\\N" if i in breaks else (" " if i > 0 else "")
        if i in alvo:
            liga = ("{\\alpha&H00&" + (f"\\c{cor}" if cor else "")
                    + (f"\\3c{borda}" if borda else "") + anim + "}")
            partes.append(f"{sep}{liga}{text}{{\\alpha&HFF&}}")
        else:
            partes.append(f"{sep}{text}")
    corpo = "".join(partes)
    return (f"Dialogue: 2,{ts(start)},{ts(end)},Default,,0,0,0,,"
            f"{{\\alpha&HFF&}}{corpo}")


# ---------------------------------------------------------------------------
# Índice palavra → efeito (como o _emphasis_index da camada v3)
# ---------------------------------------------------------------------------


def emphasis_index(manifest: dict | None) -> dict:
    """Mapa 'idx:N' / 'ins:ID' → EffectInstance para efeitos text_emphasis.
    Havendo mais de um efeito na mesma palavra, vence o que começa por último
    (o mais específico no tempo)."""
    indice: dict[str, dict] = {}
    for e in (manifest or {}).get("effects", []):
        if e.get("type") != "text_emphasis" or not e.get("enabled", True):
            continue
        alvo = e.get("target") or {}
        if alvo.get("kind") != "words":
            continue
        for i in alvo.get("idx") or []:
            indice[f"idx:{int(i)}"] = e
        for ins in alvo.get("ins_ids") or []:
            indice[f"ins:{ins}"] = e
    return indice


def effect_for(word: dict, indice: dict) -> dict | None:
    if word.get("ins_id"):
        achado = indice.get(f"ins:{word['ins_id']}")
        if achado:
            return achado
    if word.get("idx") is not None:
        return indice.get(f"idx:{int(word['idx'])}")
    return None
