"""Legendas ASS estilizadas — motor v2.

Garantias estruturais (regressões em tests/test_captions_censor.py):

TEMPORAL — cartões NUNCA coexistem: para cartões consecutivos,
  fim_N <= início_N+1 − 1 frame (o FPS do render entra no cálculo).
  Sem coexistência não há colisão do libass, logo não há "empilhamento"
  de legendas em faixas verticais diferentes.

ESPACIAL — cada preset tem UMA âncora vertical fixa (alinhamento ASS 8,
  topo-centro): a 1ª linha de todo cartão nasce sempre na mesma altura e
  a 2ª linha cresce para baixo. Nenhum cartão muda de faixa.

Tempos das Dialogue lines são RELATIVOS ao início do corte. Karaokê:
PrimaryColour = cor "cantada", SecondaryColour = cor base ({\\k} nativo).
"""

from __future__ import annotations

# Palavras após as quais não se quebra linha (artigos, preposições, clíticos comuns).
NO_BREAK_AFTER = {
    "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas", "um", "uma", "o", "a",
    "os", "as", "que", "e", "ou", "para", "pra", "por", "com", "sem", "se", "ao", "à",
    "aos", "às", "meu", "minha", "seu", "sua", "não", "mais", "muito", "já", "vou", "vai",
}

# ---------------------------------------------------------------------------
# Presets — estilos genuinamente distintos.
# Campos de configuração explícita (todos sobrescrevíveis pelo Kit/corte):
#   anchor_top      âncora vertical fixa (px em 1080×1920) da 1ª linha
#   align           "center" | "left" | "right"
#   max_width_pct   largura máxima do texto (define margens laterais)
#   max_lines       linhas por cartão (excedente vira novo cartão)
#   max_chars       caracteres por linha
#   max_words       máx. de palavras por cartão (0 = sem limite)
#   word_mode       True → um cartão por palavra (estilos "palavra a palavra")
#   font_size / line_gap (ASS não tem entrelinha; aproximamos via \fsp? não —
#   documentado: entrelinha segue a fonte) / letter_spacing
#   border_style    1 = contorno/sombra · 3 = caixa de fundo (BackColour)
#   anim_in         "none" | "fade" | "pop" | "slide_up"
#   anim_word       "none" | "color" (karaokê) | "pop" (escala por palavra)
#   anim_ms         intensidade/duração base das animações (ms)
# ---------------------------------------------------------------------------
PRESETS: dict[str, dict] = {
    "bold_karaoke": {  # Karaokê Bold — o clássico de cortes
        "family": "Clássicos",
        "font_family": "Montserrat", "font_size": 74, "bold": True, "uppercase": True,
        "text_color": "#FFFFFF", "highlight_color": "#FFD400", "outline_color": "#000000",
        "back_color": "#000000", "outline": 4, "shadow": 1, "border_style": 1,
        "anchor_top": 1280, "align": "center", "max_width_pct": 88,
        "max_chars": 18, "max_lines": 2, "max_words": 0, "word_mode": False,
        "letter_spacing": 0, "karaoke": True,
        "anim_in": "fade", "anim_word": "color", "anim_ms": 60,
    },
    "clean": {  # Clean — branco discreto, sem karaokê
        "family": "Clássicos",
        "font_family": "Inter", "font_size": 62, "bold": True, "uppercase": False,
        "text_color": "#FFFFFF", "highlight_color": "#FFFFFF", "outline_color": "#000000",
        "back_color": "#000000", "outline": 3, "shadow": 0, "border_style": 1,
        "anchor_top": 1300, "align": "center", "max_width_pct": 84,
        "max_chars": 22, "max_lines": 2, "max_words": 0, "word_mode": False,
        "letter_spacing": 0, "karaoke": False,
        "anim_in": "fade", "anim_word": "none", "anim_ms": 90,
    },
    "podcast": {  # Podcast — sereno, destaque verde
        "family": "Clássicos",
        "font_family": "Inter", "font_size": 56, "bold": False, "uppercase": False,
        "text_color": "#F5F5F5", "highlight_color": "#7CFC00", "outline_color": "#101010",
        "back_color": "#000000", "outline": 2, "shadow": 0, "border_style": 1,
        "anchor_top": 1360, "align": "center", "max_width_pct": 86,
        "max_chars": 26, "max_lines": 2, "max_words": 0, "word_mode": False,
        "letter_spacing": 0, "karaoke": True,
        "anim_in": "none", "anim_word": "color", "anim_ms": 0,
    },
    "minimal": {  # Minimal — 1 linha, nada de efeito
        "family": "Clássicos",
        "font_family": "Inter", "font_size": 50, "bold": False, "uppercase": False,
        "text_color": "#FFFFFF", "highlight_color": "#FFFFFF", "outline_color": "#000000",
        "back_color": "#000000", "outline": 1, "shadow": 0, "border_style": 1,
        "anchor_top": 1400, "align": "center", "max_width_pct": 80,
        "max_chars": 28, "max_lines": 1, "max_words": 0, "word_mode": False,
        "letter_spacing": 0, "karaoke": False,
        "anim_in": "none", "anim_word": "none", "anim_ms": 0,
    },
    "palavra_pop": {  # Palavra Pop Classic — INTOCADO: comportamento já aprovado
        "family": "Palavra Pop",
        "font_family": "Montserrat", "font_size": 96, "bold": True, "uppercase": True,
        "text_color": "#FFFFFF", "highlight_color": "#FFFFFF", "outline_color": "#000000",
        "back_color": "#000000", "outline": 5, "shadow": 2, "border_style": 1,
        "anchor_top": 1180, "align": "center", "max_width_pct": 92,
        "max_chars": 16, "max_lines": 1, "max_words": 1, "word_mode": True,
        "letter_spacing": 1, "karaoke": False,
        "anim_in": "pop", "anim_word": "pop", "anim_ms": 80,
    },

    # --- Família Palavra Pop (Ponto 19): mesma linguagem (uma palavra por vez),
    # variações com diferença VISUAL perceptível — nunca oito nomes iguais.
    "pp_clean": {  # sofisticado: menor, sem caixa alta, contorno fino, pouca expansão
        "family": "Palavra Pop",
        "font_family": "Inter", "font_size": 76, "bold": True, "uppercase": False,
        "text_color": "#FFFFFF", "highlight_color": "#FFFFFF", "outline_color": "#0A0A0A",
        "back_color": "#000000", "outline": 2, "shadow": 0, "border_style": 1,
        "anchor_top": 1240, "align": "center", "max_width_pct": 88,
        "max_chars": 18, "max_lines": 1, "max_words": 1, "word_mode": True,
        "letter_spacing": 0, "karaoke": False,
        "anim_in": "fade", "anim_word": "soft", "anim_ms": 150,
    },
    "pp_bold": {  # pesado: fonte enorme, contorno grosso, entrada marcada
        "family": "Palavra Pop",
        "font_family": "Montserrat", "font_size": 112, "bold": True, "uppercase": True,
        "text_color": "#FFFFFF", "highlight_color": "#FFD400", "outline_color": "#000000",
        "back_color": "#000000", "outline": 7, "shadow": 3, "border_style": 1,
        "anchor_top": 1140, "align": "center", "max_width_pct": 94,
        "max_chars": 13, "max_lines": 1, "max_words": 1, "word_mode": True,
        "letter_spacing": 2, "karaoke": False,
        "anim_in": "pop", "anim_word": "pop", "anim_ms": 70,
    },
    "pp_impact": {  # batalhas/esportes: entra GRANDE e assenta, amarelo de impacto
        "family": "Palavra Pop",
        "font_family": "Montserrat", "font_size": 100, "bold": True, "uppercase": True,
        "text_color": "#FFE24A", "highlight_color": "#FFE24A", "outline_color": "#101010",
        "back_color": "#000000", "outline": 6, "shadow": 2, "border_style": 1,
        "anchor_top": 1160, "align": "center", "max_width_pct": 94,
        "max_chars": 14, "max_lines": 1, "max_words": 1, "word_mode": True,
        "letter_spacing": 1, "karaoke": False,
        "anim_in": "punch", "anim_word": "punch", "anim_ms": 110,
    },
    "pp_box": {  # educacional: a palavra vem dentro de uma caixa sólida
        "family": "Palavra Pop",
        "font_family": "Montserrat", "font_size": 84, "bold": True, "uppercase": True,
        "text_color": "#101010", "highlight_color": "#101010", "outline_color": "#FFFFFF",
        "back_color": "#FFFFFF", "outline": 6, "shadow": 0, "border_style": 3,
        "anchor_top": 1260, "align": "center", "max_width_pct": 86,
        "max_chars": 15, "max_lines": 1, "max_words": 1, "word_mode": True,
        "letter_spacing": 0, "karaoke": False,
        "anim_in": "pop", "anim_word": "none", "anim_ms": 90,
    },
    "pp_neon": {  # música/gaming: ciano vibrante com brilho e contorno escuro
        "family": "Palavra Pop",
        "font_family": "Montserrat", "font_size": 92, "bold": True, "uppercase": True,
        "text_color": "#5FF6FF", "highlight_color": "#FF3DDC", "outline_color": "#0B0322",
        "back_color": "#000000", "outline": 5, "shadow": 0, "border_style": 1,
        "anchor_top": 1200, "align": "center", "max_width_pct": 92,
        "max_chars": 15, "max_lines": 1, "max_words": 1, "word_mode": True,
        "letter_spacing": 2, "karaoke": False,
        "anim_in": "glow", "anim_word": "glow", "anim_ms": 130,
    },
    "pp_soft": {  # storytelling: sobe suave, sem sobressalto
        "family": "Palavra Pop",
        "font_family": "Inter", "font_size": 82, "bold": True, "uppercase": False,
        "text_color": "#F7F7F7", "highlight_color": "#F7F7F7", "outline_color": "#141414",
        "back_color": "#000000", "outline": 3, "shadow": 1, "border_style": 1,
        "anchor_top": 1300, "align": "center", "max_width_pct": 86,
        "max_chars": 18, "max_lines": 1, "max_words": 1, "word_mode": True,
        "letter_spacing": 0, "karaoke": False,
        "anim_in": "fade", "anim_word": "soft", "anim_ms": 200,
    },
    "pp_minimal": {  # destaca a palavra falada quase sem movimento
        "family": "Palavra Pop",
        "font_family": "Inter", "font_size": 70, "bold": False, "uppercase": True,
        "text_color": "#FFFFFF", "highlight_color": "#FFFFFF", "outline_color": "#000000",
        "back_color": "#000000", "outline": 2, "shadow": 0, "border_style": 1,
        "anchor_top": 1340, "align": "center", "max_width_pct": 80,
        "max_chars": 18, "max_lines": 1, "max_words": 1, "word_mode": True,
        "letter_spacing": 3, "karaoke": False,
        "anim_in": "none", "anim_word": "none", "anim_ms": 0,
    },
    "highlight_box": {  # Highlight Box — caixa de fundo atrás do texto
        "family": "Clássicos",
        "font_family": "Montserrat", "font_size": 64, "bold": True, "uppercase": True,
        "text_color": "#111111", "highlight_color": "#111111", "outline_color": "#FFD400",
        "back_color": "#FFD400", "outline": 3, "shadow": 0, "border_style": 3,
        "anchor_top": 1300, "align": "center", "max_width_pct": 84,
        "max_chars": 18, "max_lines": 2, "max_words": 4, "word_mode": False,
        "letter_spacing": 0, "karaoke": False,
        "anim_in": "fade", "anim_word": "none", "anim_ms": 50,
    },
    "bounce": {  # Bounce — palavra a palavra com overshoot elástico
        "family": "Clássicos",
        "font_family": "Montserrat", "font_size": 88, "bold": True, "uppercase": True,
        "text_color": "#FFFFFF", "highlight_color": "#FFD400", "outline_color": "#000000",
        "back_color": "#000000", "outline": 4, "shadow": 1, "border_style": 1,
        "anchor_top": 1220, "align": "center", "max_width_pct": 92,
        "max_chars": 14, "max_lines": 1, "max_words": 2, "word_mode": True,
        "letter_spacing": 0, "karaoke": False,
        "anim_in": "none", "anim_word": "bounce", "anim_ms": 70,
    },
    "subtitle_bar": {  # Subtitle Bar — barra escura no rodapé, estilo entrevista
        "family": "Clássicos",
        "font_family": "Inter", "font_size": 46, "bold": False, "uppercase": False,
        "text_color": "#FFFFFF", "highlight_color": "#FFFFFF", "outline_color": "#000000",
        "back_color": "#101010", "outline": 4, "shadow": 0, "border_style": 3,
        "anchor_top": 1680, "align": "center", "max_width_pct": 90,
        "max_chars": 34, "max_lines": 2, "max_words": 0, "word_mode": False,
        "letter_spacing": 0, "karaoke": False,
        "anim_in": "none", "anim_word": "none", "anim_ms": 0,
    },
}

PRESET_LABELS_PTBR = {
    "bold_karaoke": "Karaokê Bold", "clean": "Clean", "podcast": "Podcast",
    "minimal": "Minimal", "palavra_pop": "Palavra Pop Classic",
    "pp_clean": "Palavra Pop Clean", "pp_bold": "Palavra Pop Bold",
    "pp_impact": "Palavra Pop Impact", "pp_box": "Palavra Pop Box",
    "pp_neon": "Palavra Pop Neon", "pp_soft": "Palavra Pop Soft",
    "pp_minimal": "Palavra Pop Minimal",
    "highlight_box": "Highlight Box", "bounce": "Bounce", "subtitle_bar": "Subtitle Bar",
}

# frase de amostra dos cards de preview do seletor visual (Ponto 20)
PRESET_SAMPLE = "ESSA É UMA LEGENDA"

MAX_CARD_SECONDS = 3.5
CARD_GAP_BREAK = 0.6
CARD_TAIL_S = 0.12     # respiro após a última palavra…
DEFAULT_FPS = 30.0     # …limitado pelo início do próximo cartão − 1 frame


def resolve_style(caption_style: dict | None, brand_kit: dict | None = None) -> dict:
    """preset base ← overrides do brand kit ← overrides do corte."""
    preset_name = "bold_karaoke"
    if caption_style and caption_style.get("preset"):
        preset_name = caption_style["preset"]
    elif brand_kit and brand_kit.get("caption_preset"):
        preset_name = brand_kit["caption_preset"]
    style = dict(PRESETS.get(preset_name, PRESETS["bold_karaoke"]))
    if brand_kit:
        if brand_kit.get("font_family"):
            style["font_family"] = brand_kit["font_family"]
        if brand_kit.get("primary_color"):
            style["text_color"] = brand_kit["primary_color"]
        if brand_kit.get("secondary_color"):
            style["highlight_color"] = brand_kit["secondary_color"]
        for k, v in (brand_kit.get("caption_style") or {}).items():
            style[k] = v
    for k, v in (caption_style or {}).items():
        if k != "preset":
            style[k] = v
    return style


def hex_to_ass(color: str, alpha: str = "00") -> str:
    c = color.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    r, g, b = c[0:2], c[2:4], c[4:6]
    return f"&H{alpha}{b.upper()}{g.upper()}{r.upper()}"


def _ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def split_lines(word_texts: list[str], max_chars: int, max_lines: int) -> list[int]:
    """Índices onde inserir quebra (\\N), respeitando NO_BREAK_AFTER e o limite de linhas."""
    breaks: list[int] = []
    line_len = 0
    for i, word in enumerate(word_texts):
        add = len(word) + (1 if line_len else 0)
        if line_len and line_len + add > max_chars and len(breaks) < max_lines - 1:
            prev = word_texts[i - 1].lower().strip(".,!?…")
            if prev in NO_BREAK_AFTER and len(breaks) < max_lines - 1 and i >= 2:
                breaks.append(i - 1)  # move a quebra para antes da palavra funcional
            else:
                breaks.append(i)
            line_len = len(word)
        else:
            line_len += add
    return breaks


def build_cards(words: list[dict], style: dict) -> list[list[dict]]:
    """Agrupa palavras em cartões: pausa, duração, tamanho, nº de linhas e nº de palavras.

    Excedente NUNCA comprime a fonte: vira o próximo cartão sequencial."""
    if style.get("word_mode"):
        per = max(1, int(style.get("max_words") or 1))
        return [words[i:i + per] for i in range(0, len(words), per)]
    max_len = int(style["max_chars"]) * int(style["max_lines"])
    max_words = int(style.get("max_words") or 0)
    cards: list[list[dict]] = []
    current: list[dict] = []
    text_len = 0
    for w in words:
        gap = w["start_s"] - current[-1]["end_s"] if current else 0.0
        dur = w["end_s"] - current[0]["start_s"] if current else 0.0
        cheio = (text_len + len(w["word"]) + 1 > max_len
                 or (max_words and len(current) >= max_words))
        if current and (gap > CARD_GAP_BREAK or dur > MAX_CARD_SECONDS or cheio):
            cards.append(current)
            current = []
            text_len = 0
        current.append(w)
        text_len += len(w["word"]) + 1
    if current:
        cards.append(current)
    return cards


def card_windows(cards: list[list[dict]], fps: float = DEFAULT_FPS,
                 tail_s: float = CARD_TAIL_S) -> list[tuple[float, float]]:
    """Janela de exibição de cada cartão com a REGRA TEMPORAL:
    fim_N = min(última_palavra_N + cauda, início_N+1 − 1 frame).

    Invariante (coberto por teste): fim_N < início_N+1 SEMPRE — dois cartões
    jamais ficam ativos no mesmo instante, em qualquer FPS."""
    frame = 1.0 / max(1.0, fps)
    janelas: list[tuple[float, float]] = []
    for i, card in enumerate(cards):
        start = card[0]["start_s"]
        end = card[-1]["end_s"] + tail_s
        if i + 1 < len(cards):
            proximo = cards[i + 1][0]["start_s"]
            end = min(end, proximo - frame)
            if end <= start:              # cartões colados: cede meio frame
                end = min(start + frame / 4, proximo - frame / 2)
            if end <= start:              # inícios idênticos (dado degenerado):
                end = start               # evento de duração zero — invisível, sem colisão
        else:
            end = max(end, start + frame)
        janelas.append((round(start, 4), round(end, 4)))
    return janelas


def _align_an(align: str) -> int:
    """Alinhamento ASS na LINHA DO TOPO (7/8/9): a âncora vertical é sempre fixa
    e o texto cresce para baixo — nunca para cima."""
    return {"left": 7, "center": 8, "right": 9}.get(align, 8)


def _margens(style: dict, res: tuple[int, int]) -> tuple[int, int, int]:
    """Margens laterais e âncora vertical, em pixels da resolução de saída.

    Precedência de posição (Ponto 21): coordenadas NORMALIZADAS pos_x/pos_y
    (0–1, arrastadas no canvas) › margens explícitas do Estúdio › atalho
    anchor_top + largura percentual. Normalizado é o formato persistido: o
    layout continua coerente entre a prévia 540×960 e o render 1080×1920."""
    pct = float(style.get("max_width_pct") or 88)
    anchor_top = int(style.get("anchor_top")
                     or max(200, res[1] - int(style.get("margin_v", 420)) - 220))
    if style.get("pos_y") is not None:
        anchor_top = int(round(float(style["pos_y"]) * res[1]))
    anchor_top = max(0, min(anchor_top, res[1] - 80))
    if style.get("pos_x") is not None:
        meia = res[0] * (pct / 100.0) / 2.0
        centro = float(style["pos_x"]) * res[0]
        ml = int(round(centro - meia))
        mr = int(round(res[0] - (centro + meia)))
        if ml < 0:   # a caixa nunca sai da tela
            mr, ml = max(0, mr + ml), 0
        if mr < 0:
            ml, mr = max(0, ml + mr), 0
        return ml, mr, anchor_top
    # margens explícitas (área de legenda do Brand Studio) vencem a largura %
    if style.get("margin_l") is not None or style.get("margin_r") is not None:
        ml = max(0, int(style.get("margin_l") or 24))
        mr = max(0, int(style.get("margin_r") or 24))
        return ml, mr, anchor_top
    lateral = max(24, int(res[0] * (100 - pct) / 200))
    return lateral, lateral, anchor_top


def _anim_in_tags(style: dict) -> str:
    ms = int(style.get("anim_ms") or 0)
    anim = style.get("anim_in") or "none"
    if anim == "fade" and ms:
        return f"{{\\fad({ms},{max(30, ms // 2)})}}"
    if anim == "pop" and ms:
        return (f"{{\\fscx82\\fscy82\\t(0,{ms},\\fscx100\\fscy100)"
                f"\\fad({max(30, ms // 2)},{max(30, ms // 2)})}}")
    if anim == "punch" and ms:  # entra GRANDE e assenta (família Palavra Pop Impact)
        return (f"{{\\fscx132\\fscy132\\t(0,{ms},\\fscx100\\fscy100)"
                f"\\fad({max(20, ms // 3)},{max(30, ms // 2)})}}")
    if anim == "glow" and ms:  # brilho que assenta (Palavra Pop Neon)
        return f"{{\\blur6\\t(0,{ms},\\blur1.2)\\fad({max(30, ms // 2)},{max(30, ms // 2)})}}"
    if anim == "slide_up" and ms:
        return f"{{\\fad({ms},{max(30, ms // 2)})}}"  # deslize real exigiria \move por cartão
    return ""


def _anim_word_tags(style: dict) -> str:
    ms = int(style.get("anim_ms") or 0)
    anim = style.get("anim_word") or "none"
    if anim == "pop" and ms:
        return f"{{\\fscx80\\fscy80\\t(0,{ms},\\fscx100\\fscy100)}}"
    if anim == "bounce" and ms:
        return (f"{{\\fscx70\\fscy70\\t(0,{ms},\\fscx114\\fscy114)"
                f"\\t({ms},{ms * 2},\\fscx100\\fscy100)}}")
    if anim == "punch" and ms:
        return f"{{\\fscx130\\fscy130\\t(0,{ms},\\fscx100\\fscy100)}}"
    if anim == "soft" and ms:  # movimento contido, sem sobressalto
        return f"{{\\fscx94\\fscy94\\t(0,{ms},\\fscx100\\fscy100)}}"
    if anim == "glow" and ms:
        return f"{{\\blur5\\t(0,{ms},\\blur1)}}"
    return ""



# ---------------------------------------------------------------------------
# Ênfase por palavra (Pontos 15–18) — a palavra ganha tratamento próprio SEM
# deslocar a linha de leitura: só escala/cor/contorno/desfoque/rotação, nunca
# tamanho de fonte (\fs) ou posição (\pos), que refluiriam o cartão.
#
# Modelo persistido em cut.edits["word_emphasis"]:
#   [{"idx": [4, 5], "effect": "fatality", "intensity": "forte",
#     "color": "#FF0000", "outline_color": "#000000"}]
#   (para palavras inseridas manualmente: {"ins_ids": ["w1"], ...})
# Um mesmo item pode cobrir várias palavras — uma expressão inteira recebe o
# efeito como bloco. O campo fica pronto para a IA preencher no futuro
# (punchline, número importante, nome…) sem mudar nada aqui.
# ---------------------------------------------------------------------------
EMPHASIS_EFFECTS = (
    "pop", "punch", "impact", "fatality", "color_hit", "shake",
    "highlight_box", "soft_lift", "glow", "outline_burst", "flash", "bounce",
)

EMPHASIS_LABELS_PTBR = {
    "pop": "Pop", "punch": "Punch", "impact": "Impact", "fatality": "Fatality",
    "color_hit": "Color Hit", "shake": "Shake", "highlight_box": "Highlight Box",
    "soft_lift": "Soft Lift", "glow": "Glow", "outline_burst": "Outline Burst",
    "flash": "Flash", "bounce": "Bounce",
}

# multiplicador de intensidade → escala do efeito e duração
INTENSITIES = {"suave": 0.6, "normal": 1.0, "forte": 1.5}


def _emphasis_index(edits: dict | None) -> dict:
    """{"idx:<n>" | "ins:<id>" → spec} para consulta rápida por palavra."""
    idx: dict[str, dict] = {}
    for item in (edits or {}).get("word_emphasis") or []:
        if not isinstance(item, dict) or item.get("effect") not in EMPHASIS_EFFECTS:
            continue
        for i in item.get("idx") or []:
            idx[f"idx:{int(i)}"] = item
        for w in item.get("ins_ids") or []:
            idx[f"ins:{w}"] = item
    return idx


def _emphasis_for(word: dict, indice: dict) -> dict | None:
    if not indice:
        return None
    if word.get("ins_id"):
        achado = indice.get(f"ins:{word['ins_id']}")
        if achado:
            return achado
    if word.get("idx") is not None:
        return indice.get(f"idx:{int(word['idx'])}")
    return None


def _emphasis_tags(spec: dict, style: dict, t0_ms: int, dur_ms: int) -> tuple[str, str]:
    """(tags antes da palavra, tags de reset depois dela).

    As animações são ancoradas no instante EM QUE A PALAVRA É FALADA
    (t0_ms, relativo ao início do evento), então a ênfase acompanha a fala.
    O reset devolve o estado do estilo para as palavras seguintes."""
    efeito = spec.get("effect")
    k = INTENSITIES.get(str(spec.get("intensity") or "normal"), 1.0)
    d = max(90, min(600, int(dur_ms * 0.55) if dur_ms else 220))
    t1 = max(0, t0_ms)
    bord = float(style.get("outline") or 3)
    cor_base = hex_to_ass(style.get("highlight_color" if style.get("karaoke")
                                    else "text_color", "#FFFFFF"))
    cor_out = hex_to_ass(style.get("outline_color", "#000000"))
    cor = hex_to_ass(spec["color"]) if spec.get("color") else None
    cor_borda = hex_to_ass(spec["outline_color"]) if spec.get("outline_color") else None

    def esc(v: float) -> int:  # escala com intensidade, limitada para não estourar
        return int(round(100 + (v - 100) * k))

    def ang(v: float) -> float:
        """Rotação SEMPRE pequena: em libass \\frz gira em torno da âncora da
        linha, então ângulos grandes deslocariam a palavra (coberto por teste)."""
        return round(max(-5.0, min(5.0, v * k)), 2)

    reset = f"{{\\fscx100\\fscy100\\bord{bord:g}\\blur0\\frz0\\c{cor_base}\\3c{cor_out}}}"
    if efeito == "pop":
        t = (f"{{\\t({t1},{t1 + d // 2},\\fscx{esc(118)}\\fscy{esc(118)})"
             f"\\t({t1 + d // 2},{t1 + d},\\fscx100\\fscy100)}}")
    elif efeito == "punch":
        t = (f"{{\\t({t1},{t1 + max(40, d // 4)},\\fscx{esc(136)}\\fscy{esc(136)})"
             f"\\t({t1 + max(40, d // 4)},{t1 + d},\\fscx100\\fscy100)}}")
    elif efeito == "impact":
        t = (f"{{\\t({t1},{t1 + max(40, d // 4)},\\fscx{esc(128)}\\fscy{esc(128)}"
             f"\\bord{bord + 3 * k:g})"
             f"\\t({t1 + max(40, d // 4)},{t1 + d},\\fscx100\\fscy100\\bord{bord:g})}}")
    elif efeito == "fatality":
        # golpe: cresce muito, borda reforçada, cor quente e um tremor curto
        q = max(30, d // 6)
        cor_f = cor or hex_to_ass("#FF2D2D")
        t = (f"{{\\t({t1},{t1 + q},\\fscx{esc(142)}\\fscy{esc(142)}\\bord{bord + 4 * k:g}"
             f"\\c{cor_f})"
             f"\\t({t1 + q},{t1 + 2 * q},\\frz{ang(-2.5):g})"
             f"\\t({t1 + 2 * q},{t1 + 3 * q},\\frz{ang(2.5):g})"
             f"\\t({t1 + 3 * q},{t1 + 4 * q},\\frz0)"
             f"\\t({t1 + 4 * q},{t1 + d},\\fscx100\\fscy100\\bord{bord:g}\\c{cor_base})}}")
    elif efeito == "color_hit":
        cor_h = cor or hex_to_ass("#FFD400")
        t = (f"{{\\t({t1},{t1 + 40},\\c{cor_h})"
             f"\\t({t1 + d},{t1 + d + 120},\\c{cor_base})}}")
    elif efeito == "shake":
        q = max(25, d // 5)
        a = ang(3.0)
        t = (f"{{\\t({t1},{t1 + q},\\frz{-a:g})\\t({t1 + q},{t1 + 2 * q},\\frz{a:g})"
             f"\\t({t1 + 2 * q},{t1 + 3 * q},\\frz{-a / 2:g})"
             f"\\t({t1 + 3 * q},{t1 + 4 * q},\\frz0)}}")
    elif efeito == "highlight_box":
        # caixa possível dentro de UM evento: contorno grosso colorido, que em
        # libass envolve a palavra como um bloco sólido
        cor_cx = cor_borda or cor or hex_to_ass("#FFD400")
        t = (f"{{\\t({t1},{t1 + 60},\\bord{bord + 9 * k:g}\\3c{cor_cx})"
             f"\\t({t1 + d + 200},{t1 + d + 320},\\bord{bord:g}\\3c{cor_out})}}")
    elif efeito == "soft_lift":
        t = (f"{{\\t({t1},{t1 + d},\\fscx{esc(108)}\\fscy{esc(108)})"
             f"\\t({t1 + d},{t1 + int(d * 1.8)},\\fscx100\\fscy100)}}")
    elif efeito == "glow":
        t = (f"{{\\t({t1},{t1 + d // 2},\\blur{3 * k:g}\\bord{bord + 1.5 * k:g})"
             f"\\t({t1 + d // 2},{t1 + d},\\blur0\\bord{bord:g})}}")
    elif efeito == "outline_burst":
        t = (f"{{\\t({t1},{t1 + d // 2},\\bord{bord + 6 * k:g})"
             f"\\t({t1 + d // 2},{t1 + d},\\bord{bord:g})}}")
    elif efeito == "flash":
        cor_f = cor or hex_to_ass("#FFFFFF")
        t = (f"{{\\t({t1},{t1 + 30},\\c{cor_f}\\3c{cor_f})"
             f"\\t({t1 + 90},{t1 + 160},\\c{cor_base}\\3c{cor_out})}}")
    elif efeito == "bounce":
        q = max(35, d // 3)
        t = (f"{{\\t({t1},{t1 + q},\\fscx{esc(124)}\\fscy{esc(124)})"
             f"\\t({t1 + q},{t1 + 2 * q},\\fscx{esc(94)}\\fscy{esc(94)})"
             f"\\t({t1 + 2 * q},{t1 + 3 * q},\\fscx100\\fscy100)}}")
    else:
        return "", ""
    # cor fixa pedida pelo usuário vale enquanto a palavra existir (Ponto 24:
    # a ênfase é o override mais específico de todos)
    if cor and efeito not in ("color_hit", "fatality", "flash"):
        t = f"{{\\c{cor}}}" + t
    if cor_borda and efeito != "highlight_box":
        t = f"{{\\3c{cor_borda}}}" + t
    return t, reset


def build_ass(words: list[dict], caption_style: dict | None = None,
              brand_kit: dict | None = None, headline: str | None = None,
              res: tuple[int, int] = (1080, 1920), clip_duration: float | None = None,
              fps: float = DEFAULT_FPS, edits: dict | None = None) -> str:
    """`words`: [{"start_s","end_s","word"}] RELATIVOS ao clipe.

    `edits` traz a camada do corte — hoje usada para a ênfase por palavra
    (edits["word_emphasis"]); o texto já vem resolvido em `words`."""
    style = resolve_style(caption_style, brand_kit)
    karaoke = bool(style.get("karaoke"))
    primary = hex_to_ass(style["highlight_color" if karaoke else "text_color"])
    secondary = hex_to_ass(style["text_color"])
    outline_c = hex_to_ass(style["outline_color"])
    _bs = int(style.get("border_style") or 1)
    # BackColour no ASS é a caixa (border_style 3) OU a sombra (border_style 1):
    # shadow_color permite escolher a cor da sombra sem mexer na caixa.
    back_c = hex_to_ass(
        style.get("back_color", "#000000") if _bs == 3
        else style.get("shadow_color", style.get("back_color", "#000000")),
        alpha="00" if _bs == 3 else "96")
    bold = -1 if style.get("bold") else 0
    border_style = int(style.get("border_style") or 1)
    spacing = int(style.get("letter_spacing") or 0)
    ml, mr, anchor_top = _margens(style, res)
    an = _align_an(style.get("align") or "center")

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {res[0]}
PlayResY: {res[1]}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style['font_family']},{style['font_size']},{primary},{secondary},{outline_c},{back_c},{bold},0,0,0,100,100,{spacing},0,{border_style},{style['outline']},{style['shadow']},{an},{ml},{mr},{anchor_top},1
Style: Headline,{style['font_family']},{max(40, int(style['font_size'] * 0.72))},{hex_to_ass('#FFFFFF')},{hex_to_ass('#FFFFFF')},{hex_to_ass('#000000')},&H96000000,-1,0,0,0,100,100,0,0,1,{max(2, int(style['outline']) - 1)},0,8,60,60,140,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines: list[str] = []
    if headline:
        end_t = clip_duration if clip_duration else (words[-1]["end_s"] if words else 5.0)
        text = headline.replace("\n", "\\N")
        lines.append(f"Dialogue: 1,{_ts(0)},{_ts(end_t)},Headline,,0,0,0,,{text}")

    cards = build_cards(words, style)
    janelas = card_windows(cards, fps=fps)
    entrada = _anim_in_tags(style)
    palavra_fx = _anim_word_tags(style)
    enf_idx = _emphasis_index(edits)

    for card, (start_t, end_t) in zip(cards, janelas, strict=False):
        texts = [w["word"].strip() for w in card]
        if style.get("uppercase"):
            texts = [t.upper() for t in texts]
        breaks = set(split_lines(texts, int(style["max_chars"]), int(style["max_lines"])))
        parts: list[str] = []
        janela_cs = max(1, round((end_t - start_t) * 100))
        gasto_cs = 0
        for i, (w, text) in enumerate(zip(card, texts, strict=False)):
            sep = "\\N" if i in breaks else (" " if i > 0 else "")
            enf = _emphasis_for(w, enf_idx)
            fx_pre, fx_pos = ("", "")
            if enf:
                fx_pre, fx_pos = _emphasis_tags(
                    enf, style,
                    t0_ms=int(max(0.0, w["start_s"] - start_t) * 1000),
                    dur_ms=int(max(0.0, w["end_s"] - w["start_s"]) * 1000))
            if karaoke:
                dur_cs = max(1, round((w["end_s"] - w["start_s"]) * 100))
                if i == len(card) - 1:  # último {\k} nunca ultrapassa a janela do cartão
                    dur_cs = max(1, min(dur_cs, janela_cs - gasto_cs))
                gasto_cs += dur_cs
                parts.append(f"{sep}{{\\k{dur_cs}}}{fx_pre}{text}{fx_pos}")
            else:
                parts.append(f"{sep}{fx_pre}{text}{fx_pos}")
        corpo = "".join(parts)
        prefixo = palavra_fx if style.get("word_mode") else entrada
        lines.append(f"Dialogue: 0,{_ts(start_t)},{_ts(end_t)},Default,,0,0,0,,{prefixo}{corpo}")

    return header + "\n".join(lines) + "\n"


def words_for_cut(all_words: list[dict], start_s: float, end_s: float,
                  edits: dict | None = None) -> list[dict]:
    """Seleciona palavras do intervalo e desloca para o tempo do clipe (t−start).

    `edits["caption_words"]` (tempos do vídeo original) substitui integralmente;
    `edits["word_overrides"]` = {"<idx>": "novo texto"} corrige palavras pontuais
    (persistido no corte — a transcrição original permanece intacta)."""
    if edits and edits.get("caption_words"):
        source = edits["caption_words"]
    else:
        source = all_words
    overrides = (edits or {}).get("word_overrides") or {}
    out = []
    for w in source:
        if w["end_s"] <= start_s or w["start_s"] >= end_s:
            continue
        text = overrides.get(str(w.get("idx", ""))) or w["word"]
        out.append({"idx": w.get("idx"),
                    "start_s": round(max(0.0, w["start_s"] - start_s), 3),
                    "end_s": round(min(end_s, w["end_s"]) - start_s, 3),
                    "word": text})
    return out
