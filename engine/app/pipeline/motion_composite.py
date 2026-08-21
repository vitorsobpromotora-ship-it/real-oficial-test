"""Composite presets (v4 FASE G) — um preset que comanda TEXTO + VÍDEO + CENA.

A Fatality de verdade não é um efeito de palavra: é uma sequência orquestrada
(Entrega 109): o zoom COMEÇA ANTES do golpe, a cena escurece, o texto estoura
no hit, a câmera leva a pancada, o RGB rasga no pico e tudo se recolhe.

Regras estruturais:
- O composite é DADO: uma lista de "parts", cada uma um preset já existente
  (texto/vídeo) com offset relativo ao HIT e duração própria. Nenhuma parte
  nova de render é inventada aqui — só orquestração.
- EXPANDE em EffectInstances REAIS no manifest, todas com o mesmo `group`:
  ficam visíveis nas tracks, individualmente editáveis e removíveis
  (Entrega 77 — nada é "baked"), e o grupo pode ser excluído de uma vez.
- Determinismo: as seeds das partes derivam da seed do grupo (hash32) —
  recriar com a mesma seed reproduz o mesmo movimento.
- Intensidade Suave/Normal/Forte vale para o conjunto; partes marcadas com
  `min_intensity` só entram nos níveis mais pesados (a Fatality Suave não
  tem RGB split — menos partes, não só amplitudes menores).
"""

from __future__ import annotations

from . import motion

_NIVEL = {"suave": 0, "normal": 1, "forte": 2}

COMPOSITE_PRESETS: dict[str, dict] = {
    "fatality_composta": {
        "id": "fatality_composta", "label": "Fatality", "categoria": "Composições",
        "descricao": "O golpe final completo: a cena arma o bote, o texto "
                     "estoura, a câmera sente e tudo se recolhe.",
        "parts": [
            # SETUP/BUILD: o zoom arma ANTES do golpe (T−300ms)
            {"type": "video_fx", "preset": "punch_zoom", "offset_ms": -300,
             "dur_ms": 850, "params": {"amount": 0.10}},
            # a cena escurece um instante antes (T−150ms)
            {"type": "video_fx", "preset": "darken", "offset_ms": -150,
             "dur_ms": 1000, "params": {"amount": 0.16}},
            # HIT: o texto Fatality no instante da palavra (dur = palavra+cauda)
            {"type": "text_emphasis", "preset": "fatality", "offset_ms": 0,
             "dur": "word"},
            # a câmera leva a pancada logo após o impacto
            {"type": "video_fx", "preset": "impact_shake", "offset_ms": 40,
             "dur_ms": 380, "params": {"amp": 16.0}},
            # pico de RGB — só do nível normal para cima
            {"type": "video_fx", "preset": "rgb_split", "offset_ms": 100,
             "dur_ms": 220, "params": {"px": 8.0}, "min_intensity": "normal"},
            # flash seco no hit — só no Forte
            {"type": "video_fx", "preset": "flash", "offset_ms": 0,
             "dur_ms": 200, "params": {"amount": 0.30}, "min_intensity": "forte"},
        ],
    },
    "punchline_composta": {
        "id": "punchline_composta", "label": "Punchline", "categoria": "Composições",
        "descricao": "Rima de efeito: punch no texto com um zoom seco junto.",
        "parts": [
            {"type": "video_fx", "preset": "punch_zoom", "offset_ms": -120,
             "dur_ms": 600, "params": {"amount": 0.08}},
            {"type": "text_emphasis", "preset": "punch", "offset_ms": 0,
             "dur": "word"},
            {"type": "video_fx", "preset": "impact_shake", "offset_ms": 30,
             "dur_ms": 280, "params": {"amp": 10.0}, "min_intensity": "forte"},
        ],
    },
}


def expand_composite(composite_id: str, *, t_hit: float, dur_word: float,
                     target: dict, intensity: str = "normal",
                     seed_base: int = 1) -> list[dict]:
    """Expande o composite em EffectInstances reais (mesmo `group`).

    `t_hit`: instante do golpe (início da palavra, tempo de SAÍDA);
    `dur_word`: duração falada da palavra (a parte de texto ganha uma cauda).
    Offsets negativos são clampados em 0 (golpe no comecinho do corte)."""
    preset = COMPOSITE_PRESETS.get(composite_id)
    if not preset:
        return []
    nivel = _NIVEL.get(str(intensity), 1)
    gid = motion.novo_id()
    out: list[dict] = []
    for i, part in enumerate(preset["parts"]):
        if _NIVEL.get(str(part.get("min_intensity", "suave")), 0) > nivel:
            continue
        start = max(0.0, t_hit + part["offset_ms"] / 1000.0)
        if part.get("dur") == "word":
            end = t_hit + max(0.35, dur_word + 0.25)
        else:
            end = start + part["dur_ms"] / 1000.0
        out.append({
            "id": f"{gid}{i:02d}",
            "type": part["type"],
            "preset": part["preset"],
            "target": target if part["type"] == "text_emphasis"
            else {"kind": "video"},
            "start": round(start, 4),
            "end": round(end, 4),
            "intensity": intensity,
            "params": dict(part.get("params") or {}),
            "enabled": True,
            "seed": motion.hash32((seed_base + i * 0x9E37) & 0xFFFFFFFF),
            "group": gid,
            "group_label": preset["label"],
        })
    return out
