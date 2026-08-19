"""Legendas ASS estilizadas com karaokê por palavra e quebra de linha PT-BR.

Tempos das Dialogue lines são RELATIVOS ao início do corte (o render usa o clipe
já aparado). Karaokê: PrimaryColour = cor "cantada" (destaque), SecondaryColour =
cor base — o preenchimento progressivo é do próprio libass via {\\k}.
"""

from __future__ import annotations

# Palavras após as quais não se quebra linha (artigos, preposições, clíticos comuns).
NO_BREAK_AFTER = {
    "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas", "um", "uma", "o", "a",
    "os", "as", "que", "e", "ou", "para", "pra", "por", "com", "sem", "se", "ao", "à",
    "aos", "às", "meu", "minha", "seu", "sua", "não", "mais", "muito", "já", "vou", "vai",
}

PRESETS: dict[str, dict] = {
    "clean": {
        "font_family": "Inter", "font_size": 64, "bold": True, "uppercase": False,
        "text_color": "#FFFFFF", "highlight_color": "#FFFFFF", "outline_color": "#000000",
        "outline": 3, "shadow": 0, "margin_v": 420, "max_chars": 22, "max_lines": 2,
        "karaoke": False,
    },
    "bold_karaoke": {
        "font_family": "Montserrat", "font_size": 72, "bold": True, "uppercase": True,
        "text_color": "#FFFFFF", "highlight_color": "#FFD400", "outline_color": "#000000",
        "outline": 4, "shadow": 1, "margin_v": 420, "max_chars": 18, "max_lines": 2,
        "karaoke": True,
    },
    "podcast": {
        "font_family": "Inter", "font_size": 56, "bold": False, "uppercase": False,
        "text_color": "#F5F5F5", "highlight_color": "#7CFC00", "outline_color": "#101010",
        "outline": 2, "shadow": 0, "margin_v": 360, "max_chars": 26, "max_lines": 2,
        "karaoke": True,
    },
    "minimal": {
        "font_family": "Inter", "font_size": 52, "bold": False, "uppercase": False,
        "text_color": "#FFFFFF", "highlight_color": "#FFFFFF", "outline_color": "#000000",
        "outline": 1, "shadow": 0, "margin_v": 380, "max_chars": 28, "max_lines": 1,
        "karaoke": False,
    },
}

MAX_CARD_SECONDS = 3.5
CARD_GAP_BREAK = 0.6


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
                # move a quebra para antes da palavra funcional
                breaks.append(i - 1)
            else:
                breaks.append(i)
            line_len = len(word)
        else:
            line_len += add
    return breaks


def build_cards(words: list[dict], style: dict) -> list[list[dict]]:
    """Agrupa palavras em 'cartões' de legenda: quebra em pausas, duração e tamanho."""
    max_len = style["max_chars"] * style["max_lines"]
    cards: list[list[dict]] = []
    current: list[dict] = []
    text_len = 0
    for w in words:
        gap = w["start_s"] - current[-1]["end_s"] if current else 0.0
        dur = w["end_s"] - current[0]["start_s"] if current else 0.0
        if current and (gap > CARD_GAP_BREAK or dur > MAX_CARD_SECONDS
                        or text_len + len(w["word"]) + 1 > max_len):
            cards.append(current)
            current = []
            text_len = 0
        current.append(w)
        text_len += len(w["word"]) + 1
    if current:
        cards.append(current)
    return cards


def build_ass(words: list[dict], caption_style: dict | None = None,
              brand_kit: dict | None = None, headline: str | None = None,
              res: tuple[int, int] = (1080, 1920), clip_duration: float | None = None) -> str:
    """`words`: [{"start_s","end_s","word"}] RELATIVOS ao clipe."""
    style = resolve_style(caption_style, brand_kit)
    karaoke = bool(style.get("karaoke"))
    primary = hex_to_ass(style["highlight_color" if karaoke else "text_color"])
    secondary = hex_to_ass(style["text_color"])
    outline_c = hex_to_ass(style["outline_color"])
    bold = -1 if style.get("bold") else 0

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {res[0]}
PlayResY: {res[1]}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style['font_family']},{style['font_size']},{primary},{secondary},{outline_c},&H96000000,{bold},0,0,0,100,100,0,0,1,{style['outline']},{style['shadow']},2,60,60,{style['margin_v']},1
Style: Headline,{style['font_family']},{max(40, int(style['font_size'] * 0.75))},{hex_to_ass('#FFFFFF')},{hex_to_ass('#FFFFFF')},{outline_c},&H96000000,-1,0,0,0,100,100,0,0,1,{max(2, style['outline'] - 1)},0,8,60,60,140,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines: list[str] = []
    if headline:
        end_t = clip_duration if clip_duration else (words[-1]["end_s"] if words else 5.0)
        text = headline.replace("\n", "\\N")
        lines.append(f"Dialogue: 1,{_ts(0)},{_ts(end_t)},Headline,,0,0,0,,{text}")

    for card in build_cards(words, style):
        texts = [w["word"].strip() for w in card]
        if style.get("uppercase"):
            texts = [t.upper() for t in texts]
        breaks = set(split_lines(texts, style["max_chars"], style["max_lines"]))
        parts: list[str] = []
        for i, (w, text) in enumerate(zip(card, texts, strict=False)):
            sep = "\\N" if i in breaks else (" " if i > 0 else "")
            if karaoke:
                dur_cs = max(1, round((w["end_s"] - w["start_s"]) * 100))
                parts.append(f"{sep}{{\\k{dur_cs}}}{text}")
            else:
                parts.append(f"{sep}{text}")
        start_t, end_t = card[0]["start_s"], card[-1]["end_s"] + 0.12
        lines.append(f"Dialogue: 0,{_ts(start_t)},{_ts(end_t)},Default,,0,0,0,,{''.join(parts)}")

    return header + "\n".join(lines) + "\n"


def words_for_cut(all_words: list[dict], start_s: float, end_s: float,
                  edits: dict | None = None) -> list[dict]:
    """Seleciona palavras do intervalo e desloca para o tempo do clipe (t−start).

    `edits["caption_words"]` (tempos do vídeo original) substitui integralmente;
    `edits["word_overrides"]` = {"<idx>": "novo texto"} corrige palavras pontuais.
    """
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
        out.append({"start_s": round(max(0.0, w["start_s"] - start_s), 3),
                    "end_s": round(min(end_s, w["end_s"]) - start_s, 3),
                    "word": text})
    return out
