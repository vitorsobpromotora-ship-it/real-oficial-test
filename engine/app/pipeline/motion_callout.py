"""Text Callout / Typography Takeover (v4 FASE E).

"Transformar em destaque de tela": um grupo de palavras deixa de ser legenda
e vira O elemento da tela — evento(s) ASS próprios com \\pos livre, tamanho
por palavra, entrada escalonada (stagger) e um fundo de cena opcional
(escurecer/blur/preto) compilado como cadeia de vídeo na mesma janela.

Reuso estrutural (nada reimplementado):
- as ANIMAÇÕES do callout são fases ENTER/HOLD/EXIT avaliadas por
  motion_text.text_props_at — as mesmas funções já provadas pelo contrato;
- o FUNDO usa as mesmas primitivas do Video FX (eq/gblur/drawbox com
  between(t,…)), inserido junto das fx_chains do render.

Layouts sem métricas de fonte (posições sempre calculáveis):
- "stack": uma palavra por linha, cada linha é um EVENTO com \\pos próprio
  (centrado em X; Y = centro + (i − (n−1)/2)·line_height);
- "line": uma linha única, UM evento; o stagger revela palavra a palavra
  via \\t de alpha e o pop de entrada anima o GRUPO.
Enquanto o callout está na tela, os cartões de legenda que cruzam a janela
são escondidos (o takeover é o texto da vez — nada duplicado).
"""

from __future__ import annotations

from . import motion_text
from .captions import hex_to_ass

CALLOUT_PRESETS: dict[str, dict] = {
    "center_impact": {
        "id": "center_impact", "label": "Impacto Central", "categoria": "Callouts",
        "descricao": "O grupo estoura no centro da tela sobre a cena escurecida.",
        "layout": "line", "bg": "darken", "font_scale": 1.45, "stagger_ms": 0,
        "phases": {
            "enter": {"dur_ms": 240, "tracks": {
                "scale": [{"t": 0.0, "v": 158.0},
                          {"t": 0.5, "v": 96.0, "ease": "rapido"},
                          {"t": 1.0, "v": 104.0, "ease": "impacto"}],
                "blur": [{"t": 0.0, "v": 7.0}, {"t": 0.5, "v": 0.0, "ease": "rapido"},
                         {"t": 1.0, "v": 0.0}],
            }},
            "hold": {"tracks": {"scale": [{"t": 0.0, "v": 104.0}, {"t": 1.0, "v": 104.0}]}},
            "exit": {"dur_ms": 160, "tracks": {
                "scale": [{"t": 0.0, "v": 104.0}, {"t": 1.0, "v": 100.0, "ease": "suave"}],
                "alpha": [{"t": 0.0, "v": 0.0}, {"t": 1.0, "v": 1.0, "ease": "suave"}],
            }},
        },
    },
    "build_up": {
        "id": "build_up", "label": "Build Up", "categoria": "Callouts",
        "descricao": "As palavras empilham uma a uma — a tensão sobe linha a linha.",
        "layout": "stack", "bg": "darken", "font_scale": 1.25, "stagger_ms": 260,
        "phases": {
            "enter": {"dur_ms": 190, "tracks": {
                "scale": [{"t": 0.0, "v": 100.0},
                          {"t": 0.5, "v": 118.0, "ease": "rapido"},
                          {"t": 1.0, "v": 104.0, "ease": "suave"}],
                "alpha": [{"t": 0.0, "v": 1.0}, {"t": 0.35, "v": 0.0, "ease": "rapido"},
                          {"t": 1.0, "v": 0.0}],
            }},
            "hold": {"tracks": {"scale": [{"t": 0.0, "v": 104.0}, {"t": 1.0, "v": 104.0}]}},
            "exit": {"dur_ms": 150, "tracks": {
                "alpha": [{"t": 0.0, "v": 0.0}, {"t": 1.0, "v": 1.0, "ease": "suave"}],
            }},
        },
    },
    "final_word": {
        "id": "final_word", "label": "Palavra Final", "categoria": "Callouts",
        "descricao": "A frase aparece e a ÚLTIMA palavra explode maior e vermelha.",
        "layout": "stack", "bg": "darken", "font_scale": 1.2, "stagger_ms": 170,
        "last_word_scale": 1.65, "last_word_color": "#FF2D2D",
        "phases": {
            "enter": {"dur_ms": 200, "tracks": {
                "scale": [{"t": 0.0, "v": 132.0},
                          {"t": 1.0, "v": 102.0, "ease": "impacto"}],
                "alpha": [{"t": 0.0, "v": 1.0}, {"t": 0.3, "v": 0.0, "ease": "rapido"},
                          {"t": 1.0, "v": 0.0}],
            }},
            "hold": {"tracks": {"scale": [{"t": 0.0, "v": 102.0}, {"t": 1.0, "v": 102.0}]}},
            "exit": {"dur_ms": 150, "tracks": {
                "alpha": [{"t": 0.0, "v": 0.0}, {"t": 1.0, "v": 1.0, "ease": "suave"}],
            }},
        },
    },
    "stack": {
        "id": "stack", "label": "Pilha", "categoria": "Callouts",
        "descricao": "Empilha o grupo no centro, limpo, sem tocar na cena.",
        "layout": "stack", "bg": "none", "font_scale": 1.2, "stagger_ms": 120,
        "phases": {
            "enter": {"dur_ms": 160, "tracks": {
                "scale": [{"t": 0.0, "v": 100.0},
                          {"t": 0.55, "v": 112.0, "ease": "rapido"},
                          {"t": 1.0, "v": 102.0, "ease": "suave"}],
                "alpha": [{"t": 0.0, "v": 1.0}, {"t": 0.4, "v": 0.0, "ease": "rapido"},
                          {"t": 1.0, "v": 0.0}],
            }},
            "hold": {"tracks": {"scale": [{"t": 0.0, "v": 102.0}, {"t": 1.0, "v": 102.0}]}},
            "exit": {"dur_ms": 140, "tracks": {
                "alpha": [{"t": 0.0, "v": 0.0}, {"t": 1.0, "v": 1.0, "ease": "suave"}],
            }},
        },
    },
    "wide_slam": {
        "id": "wide_slam", "label": "Wide Slam", "categoria": "Callouts",
        "descricao": "Uma linha larga crava na tela — manchete de impacto.",
        "layout": "line", "bg": "darken", "font_scale": 1.6, "stagger_ms": 0,
        "phases": {
            "enter": {"dur_ms": 220, "tracks": {
                "scale_x": [{"t": 0.0, "v": 165.0},
                            {"t": 0.55, "v": 98.0, "ease": "rapido"},
                            {"t": 1.0, "v": 103.0, "ease": "impacto"}],
                "scale_y": [{"t": 0.0, "v": 88.0},
                            {"t": 1.0, "v": 103.0, "ease": "impacto"}],
                "blur": [{"t": 0.0, "v": 6.0}, {"t": 0.5, "v": 0.0, "ease": "rapido"},
                         {"t": 1.0, "v": 0.0}],
            }},
            "hold": {"tracks": {
                "scale_x": [{"t": 0.0, "v": 103.0}, {"t": 1.0, "v": 103.0}],
                "scale_y": [{"t": 0.0, "v": 103.0}, {"t": 1.0, "v": 103.0}],
            }},
            "exit": {"dur_ms": 150, "tracks": {
                "alpha": [{"t": 0.0, "v": 0.0}, {"t": 1.0, "v": 1.0, "ease": "suave"}],
            }},
        },
    },
    "dark_punch": {
        "id": "dark_punch", "label": "Dark Punch", "categoria": "Callouts",
        "descricao": "Tela preta, palavra branca gigante — silêncio e soco.",
        "layout": "line", "bg": "black", "font_scale": 1.7, "stagger_ms": 0,
        "color": "#FFFFFF",
        "phases": {
            "enter": {"dur_ms": 210, "tracks": {
                "scale": [{"t": 0.0, "v": 100.0},
                          {"t": 0.3, "v": 136.0, "ease": "rapido"},
                          {"t": 1.0, "v": 106.0, "ease": "impacto"}],
            }},
            "hold": {"tracks": {"scale": [{"t": 0.0, "v": 106.0}, {"t": 1.0, "v": 106.0}]}},
            "exit": {"dur_ms": 160, "tracks": {
                "alpha": [{"t": 0.0, "v": 0.0}, {"t": 1.0, "v": 1.0, "ease": "suave"}],
            }},
        },
    },
    "battle_final": {
        "id": "battle_final", "label": "Battle Final", "categoria": "Callouts",
        "descricao": "Pilha agressiva com a última palavra em vermelho tremendo.",
        "layout": "stack", "bg": "darken", "font_scale": 1.3, "stagger_ms": 200,
        "last_word_scale": 1.5, "last_word_color": "#FF2D2D",
        "phases": {
            "enter": {"dur_ms": 180, "tracks": {
                "scale": [{"t": 0.0, "v": 128.0},
                          {"t": 1.0, "v": 103.0, "ease": "impacto"}],
                "alpha": [{"t": 0.0, "v": 1.0}, {"t": 0.3, "v": 0.0, "ease": "rapido"},
                          {"t": 1.0, "v": 0.0}],
            }},
            "hold": {"jitter": {"rot": 1.1, "freq": 9.0}, "tracks": {
                "scale": [{"t": 0.0, "v": 103.0}, {"t": 1.0, "v": 103.0}],
            }},
            "exit": {"dur_ms": 150, "tracks": {
                "alpha": [{"t": 0.0, "v": 0.0}, {"t": 1.0, "v": 1.0, "ease": "suave"}],
            }},
        },
    },
}

BACKGROUNDS = ("none", "darken", "blur", "black")


def preset_of(effect: dict) -> dict | None:
    return CALLOUT_PRESETS.get(str(effect.get("preset") or ""))


def _palavras_do_callout(effect: dict, words: list[dict]) -> list[dict]:
    """Palavras alvo na ordem do texto (idx da transcrição + inseridas)."""
    alvo_idx = set(int(i) for i in (effect.get("target") or {}).get("idx") or [])
    alvo_ins = set((effect.get("target") or {}).get("ins_ids") or [])
    out = []
    for w in words:
        if (w.get("idx") is not None and int(w["idx"]) in alvo_idx) \
                or (w.get("ins_id") and w["ins_id"] in alvo_ins):
            out.append(w)
    return out


def _grupos(effect: dict, preset: dict, palavras: list[dict]) -> list[list[dict]]:
    """Linhas do callout: stack = uma palavra por linha; line = uma linha só."""
    if preset.get("layout") == "line":
        return [palavras] if palavras else []
    return [[w] for w in palavras]


def _pseudo_effect(effect: dict, start: float) -> dict:
    """Efeito derivado para reusar text_props_at: mesma seed/intensidade,
    janela deslocada pelo stagger da linha."""
    return {**effect, "start": round(start, 4)}


def compile_callout(effect: dict, preset: dict, style: dict, words: list[dict],
                    res: tuple[int, int], fps: float, ts) -> list[str]:
    """Eventos ASS do callout (layer 3). `words`: palavras do clipe (com texto
    final resolvido); `ts` = captions._ts."""
    if not effect.get("enabled", True):
        return []
    palavras = _palavras_do_callout(effect, words)
    if not palavras:
        return []
    params = effect.get("params") or {}
    t0, t1 = float(effect["start"]), float(effect["end"])
    if t1 - t0 < 0.1:
        return []
    w_res, h_res = res
    pos_x = float(params.get("pos_x", 0.5)) * w_res
    pos_y = float(params.get("pos_y", 0.5)) * h_res
    font_scale = float(params.get("font_scale", preset.get("font_scale", 1.3)))
    fs = int(round(float(style.get("font_size") or 72) * font_scale))
    line_h = int(round(fs * 1.22))
    stagger = float(params.get("stagger_ms", preset.get("stagger_ms", 0))) / 1000.0
    cor_base = hex_to_ass(str(params.get("color") or preset.get("color")
                              or style.get("highlight_color" if style.get("karaoke")
                                           else "text_color", "#FFFFFF")))
    cor_out = hex_to_ass(style.get("outline_color", "#000000"))
    bord = max(2, int(style.get("outline") or 3))
    upper = bool(style.get("uppercase"))
    grupos = _grupos(effect, preset, palavras)
    n = len(grupos)
    # a última LINHA pode ser maior/colorida (Palavra Final, Battle Final) —
    # aplicado no \fs do EVENTO (as \t de fscx do grupo multiplicam por cima,
    # então um \fscx estático inline seria anulado pela animação)
    lw_scale = float(preset.get("last_word_scale") or 1.0)
    lw_color = preset.get("last_word_color")
    # com escala na última linha, os centros das linhas se ajustam para a
    # pilha continuar visualmente centrada
    alturas = [line_h * (lw_scale if i == n - 1 and n > 1 else 1.0) for i in range(n)]
    total_h = sum(alturas)
    eventos: list[str] = []
    y_cursor = pos_y - total_h / 2.0 if n > 1 else pos_y
    for i, grupo in enumerate(grupos):
        g_start = min(t0 + i * stagger, t1 - 0.08)
        pseudo = _pseudo_effect(effect, g_start)
        anim = motion_text._anim_sampled(pseudo, preset, style, g_start, t1, fps)
        ultima_linha = (i == n - 1 and n > 1)
        fs_linha = int(round(fs * (lw_scale if ultima_linha else 1.0)))
        # auto-ajuste: a linha NUNCA transborda a tela — sem métricas de fonte,
        # estimativa conservadora de ~0.58·fs por caractere (bold)
        n_chars = max(1, len(" ".join(str(w["word"]).strip() for w in grupo)))
        fs_max = int((w_res * 0.88) / (0.62 * n_chars))
        fs_linha = max(28, min(fs_linha, fs_max))
        y = (y_cursor + alturas[i] / 2.0) if n > 1 else pos_y
        y_cursor += alturas[i] if n > 1 else 0.0
        cor_linha = hex_to_ass(lw_color) if (ultima_linha and lw_color) else cor_base
        pedacos: list[str] = []
        for j, w in enumerate(grupo):
            texto = str(w["word"]).strip()
            if upper:
                texto = texto.upper()
            extra = ""
            # stagger DENTRO da linha (layout line): revela palavra a palavra
            if preset.get("layout") == "line" and stagger > 0 and j > 0:
                rev = round(j * stagger * 1000)
                extra += f"\\alpha&HFF&\\t({rev},{rev},\\alpha&H00&)"
            sep = " " if j > 0 else ""
            pedacos.append(f"{sep}{{{extra}}}{texto}" if extra else f"{sep}{texto}")
        corpo = "".join(pedacos)
        tag_fonte = (f"\\an5\\pos({pos_x:.0f},{y:.0f})\\fs{fs_linha}"
                     f"\\bord{bord}\\c{cor_linha}\\3c{cor_out}\\frz0")
        eventos.append(
            f"Dialogue: 3,{ts(g_start)},{ts(t1)},Default,,0,0,0,,"
            f"{{{tag_fonte}{anim}}}{corpo}")
    return eventos


def background_chain(effect: dict, preset: dict, w: int, h: int) -> str | None:
    """Cadeia de vídeo do FUNDO do callout (mesmas primitivas do Video FX)."""
    if not effect.get("enabled", True):
        return None
    params = effect.get("params") or {}
    bg = str(params.get("bg") or preset.get("bg") or "none")
    if bg not in BACKGROUNDS or bg == "none":
        return None
    t0, t1 = float(effect["start"]), float(effect["end"])
    ent = f"between(t,{t0:.3f},{t1:.3f})"
    if bg == "darken":
        return f"eq=brightness=-0.32:saturation=0.75:enable='{ent}'"
    if bg == "blur":
        sigma = max(0.5, 12.0 * w / 1080.0)
        return f"gblur=sigma={sigma:.2f}:enable='{ent}',eq=brightness=-0.12:enable='{ent}'"
    if bg == "black":
        return f"drawbox=x=0:y=0:w={w}:h={h}:color=black@0.94:t=fill:enable='{ent}'"
    return None


def collect(manifest: dict | None) -> list[tuple[dict, dict]]:
    """(efeito, preset) de todos os callouts habilitados, na ordem do manifest."""
    out = []
    for e in (manifest or {}).get("effects", []):
        if e.get("type") != "text_callout" or not e.get("enabled", True):
            continue
        preset = preset_of(e)
        if preset:
            out.append((e, preset))
    return out


def hide_windows(manifest: dict | None, card_start: float, card_end: float) -> list[tuple[float, float]]:
    """Interseções [a,b] em que os cartões de legenda devem sumir porque um
    callout tomou a tela (takeover — nada de texto duplicado)."""
    janelas = []
    for e, _p in collect(manifest):
        a = max(float(e["start"]), card_start)
        b = min(float(e["end"]), card_end)
        if b - a > 0.05:
            janelas.append((a, b))
    return sorted(janelas)
