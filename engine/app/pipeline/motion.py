"""Motion Engine — modelo declarativo e avaliador determinístico (v4 FASE B).

O MOTION MANIFEST é a fonte única da verdade dos efeitos de movimento de um
corte (cut.motion). O preview do Editor (TypeScript) e o render final (este
módulo → ASS/filtergraph) leem o MESMO manifest e avaliam as MESMAS funções —
`shared/motion-cases.json` prova a paridade nos dois lados, como o contrato
WYSIWYG das legendas.

Regras estruturais:
- EFEITO É DADO, não função: presets são descrições serializadas; nenhum
  renderFatality() hardcoded.
- Determinismo absoluto: mesmo manifest + mesmo corte → mesmo vídeo. Nada de
  random() em runtime; variação vem de `seed` persistida por efeito.
- Tempo dos efeitos em TEMPO DE SAÍDA (o relógio 00:00 do Editor), como os
  cartões de legenda.
"""

from __future__ import annotations

import math
import uuid

# ---------------------------------------------------------------------------
# Easing — biblioteca fechada, espelhada byte a byte em app/src/editor/motion.ts
# ---------------------------------------------------------------------------


def _linear(u: float) -> float:
    return u


def _ease_in(u: float) -> float:
    return u * u * u


def _ease_out(u: float) -> float:
    return 1.0 - (1.0 - u) ** 3


def _ease_in_out(u: float) -> float:
    return 4.0 * u * u * u if u < 0.5 else 1.0 - ((-2.0 * u + 2.0) ** 3) / 2.0


def _back_out(u: float) -> float:
    c1 = 1.70158
    c3 = c1 + 1.0
    return 1.0 + c3 * (u - 1.0) ** 3 + c1 * (u - 1.0) ** 2


def _elastic_out(u: float) -> float:
    if u <= 0.0:
        return 0.0
    if u >= 1.0:
        return 1.0
    c4 = (2.0 * math.pi) / 3.0
    return 2.0 ** (-10.0 * u) * math.sin((u * 10.0 - 0.75) * c4) + 1.0


def _bounce_out(u: float) -> float:
    n1, d1 = 7.5625, 2.75
    if u < 1.0 / d1:
        return n1 * u * u
    if u < 2.0 / d1:
        u -= 1.5 / d1
        return n1 * u * u + 0.75
    if u < 2.5 / d1:
        u -= 2.25 / d1
        return n1 * u * u + 0.9375
    u -= 2.625 / d1
    return n1 * u * u + 0.984375


EASINGS = {
    "linear": _linear,
    "ease_in": _ease_in,
    "ease_out": _ease_out,
    "ease_in_out": _ease_in_out,
    "back_out": _back_out,
    "elastic_out": _elastic_out,
    "bounce_out": _bounce_out,
    # apelidos de produto (Entrega 24): o usuário escolhe uma sensação, não
    # uma curva — mas a curva por baixo é a mesma biblioteca fechada
    "suave": _ease_in_out,
    "rapido": _ease_out,
    "impacto": _back_out,
    "elastico": _elastic_out,
}

EASING_LABELS_PTBR = {
    "linear": "Linear",
    "suave": "Suave",
    "rapido": "Rápido",
    "impacto": "Impacto",
    "elastico": "Elástico",
    "bounce_out": "Quicado",
}


def ease(nome: str | None, u: float) -> float:
    """Aplica a curva `nome` a u∈[0,1] (clampa fora do intervalo)."""
    u = 0.0 if u < 0.0 else 1.0 if u > 1.0 else u
    return EASINGS.get(nome or "linear", _linear)(u)


# ---------------------------------------------------------------------------
# Keyframes — avaliação de propriedade em qualquer t (Entrega 60)
# ---------------------------------------------------------------------------


def eval_keyframes(kfs: list[dict], u: float) -> float:
    """Valor da propriedade em u∈[0,1] (tempo normalizado na duração do efeito).

    Cada keyframe: {"t": 0..1, "v": número, "ease": curva do SEGMENTO que
    chega nele}. Fora do intervalo, clampa no primeiro/último valor — nunca
    extrapola (um efeito não "vaza" além dos seus keyframes).
    """
    if not kfs:
        return 0.0
    if u <= kfs[0]["t"]:
        return float(kfs[0]["v"])
    for a, b in zip(kfs, kfs[1:]):
        if u <= b["t"]:
            span = b["t"] - a["t"]
            k = 0.0 if span <= 0 else (u - a["t"]) / span
            return float(a["v"]) + (float(b["v"]) - float(a["v"])) * ease(b.get("ease"), k)
    return float(kfs[-1]["v"])


# ---------------------------------------------------------------------------
# Ruído determinístico — shake/jitter reproduzível por seed (Entregas 12, 46)
# ---------------------------------------------------------------------------


def hash32(x: int) -> int:
    """Hash inteiro 32 bits — operações espelháveis exatamente em JS (>>> / imul)."""
    x &= 0xFFFFFFFF
    x = ((x ^ 61) ^ (x >> 16)) & 0xFFFFFFFF
    x = (x + ((x << 3) & 0xFFFFFFFF)) & 0xFFFFFFFF
    x = (x ^ (x >> 4)) & 0xFFFFFFFF
    x = (x * 0x27D4EB2D) & 0xFFFFFFFF
    x = (x ^ (x >> 15)) & 0xFFFFFFFF
    return x


def rng01(seed: int, i: int) -> float:
    """Número pseudoaleatório estável em [0,1) — só de (seed, i)."""
    return hash32((seed & 0xFFFFFFFF) ^ hash32((i + 0x9E3779B9) & 0xFFFFFFFF)) / 4294967296.0


def shake_offset(t: float, seed: int, amp_x: float, amp_y: float,
                 rot_deg: float, freq: float) -> tuple[float, float, float]:
    """Câmera shake PROCEDURAL (não terremoto): soma de senos dessincronizados
    com fases derivadas da seed. Puro e determinístico — preview e render
    avaliam o mesmo deslocamento em qualquer t (segundos desde o início do hit).
    """
    f = [rng01(seed, i) * 2.0 * math.pi for i in range(5)]
    tau = 2.0 * math.pi * freq
    dx = amp_x * (math.sin(tau * t + f[0]) * 0.62 + math.sin(tau * 1.7 * t + f[1]) * 0.38)
    dy = amp_y * (math.sin(tau * 1.3 * t + f[2]) * 0.62 + math.sin(tau * 2.1 * t + f[3]) * 0.38)
    rot = rot_deg * math.sin(tau * 0.9 * t + f[4])
    return dx, dy, rot


# ---------------------------------------------------------------------------
# Manifest — validação e normalização (Entregas 2, 81)
# ---------------------------------------------------------------------------

MANIFEST_VERSION = 1

EFFECT_TYPES = ("text_emphasis", "text_callout", "video_fx", "broll", "transition", "sfx")
TARGET_KINDS = ("words", "card", "video", "clip", "media")
INTENSITIES = ("suave", "normal", "forte")
INTENSITY_K = {"suave": 0.6, "normal": 1.0, "forte": 1.5}


def novo_id() -> str:
    return uuid.uuid4().hex[:12]


def seed_de(texto: str) -> int:
    """Seed padrão derivada do id do efeito — estável entre aberturas."""
    h = 0
    for ch in texto:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return h or 1


def intensity_k(v) -> float:
    """Intensidade → fator numérico (nomes de produto ou valor custom 0..2)."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return max(0.0, min(2.0, float(v)))
    return INTENSITY_K.get(str(v), 1.0)


def _erro(msg: str) -> ValueError:
    return ValueError(msg)


def _valida_keyframes(kfs, eid: str) -> dict:
    if not isinstance(kfs, dict):
        raise _erro(f"efeito {eid}: keyframes deve ser um objeto propriedade → lista")
    out: dict[str, list[dict]] = {}
    for prop, lista in kfs.items():
        if not isinstance(lista, list):
            raise _erro(f"efeito {eid}: keyframes de '{prop}' deve ser uma lista")
        norm = []
        for kf in lista:
            if not isinstance(kf, dict) or "t" not in kf or "v" not in kf:
                raise _erro(f"efeito {eid}: keyframe de '{prop}' precisa de t e v")
            t = float(kf["t"])
            if not 0.0 <= t <= 1.0:
                raise _erro(f"efeito {eid}: keyframe t={t} fora de 0..1")
            item = {"t": t, "v": float(kf["v"])}
            if kf.get("ease"):
                if kf["ease"] not in EASINGS:
                    raise _erro(f"efeito {eid}: easing desconhecido '{kf['ease']}'")
                item["ease"] = kf["ease"]
            norm.append(item)
        out[prop] = sorted(norm, key=lambda k: k["t"])
    return out


def _valida_efeito(e: dict) -> dict:
    if not isinstance(e, dict):
        raise _erro("cada efeito do manifest deve ser um objeto")
    out = dict(e)  # preserva chaves extras (compatibilidade p/ frente)
    eid = str(e.get("id") or novo_id())
    out["id"] = eid
    tipo = e.get("type")
    if tipo not in EFFECT_TYPES:
        raise _erro(f"efeito {eid}: tipo desconhecido '{tipo}'")
    preset = e.get("preset")
    if not preset or not isinstance(preset, str):
        raise _erro(f"efeito {eid}: preset é obrigatório")
    try:
        start = float(e.get("start", 0.0))
        end = float(e.get("end", 0.0))
    except (TypeError, ValueError):
        raise _erro(f"efeito {eid}: start/end devem ser números") from None
    if start < 0 or end <= start:
        raise _erro(f"efeito {eid}: intervalo inválido ({start}→{end})")
    out["start"], out["end"] = round(start, 4), round(end, 4)
    alvo = e.get("target") or {"kind": "video"}
    if not isinstance(alvo, dict) or alvo.get("kind") not in TARGET_KINDS:
        raise _erro(f"efeito {eid}: target.kind deve ser um de {TARGET_KINDS}")
    out["target"] = alvo
    inten = e.get("intensity", "normal")
    if not (inten in INTENSITIES
            or (isinstance(inten, (int, float)) and not isinstance(inten, bool)
                and 0.0 <= float(inten) <= 2.0)):
        raise _erro(f"efeito {eid}: intensidade '{inten}' inválida (suave/normal/forte ou 0..2)")
    out["intensity"] = inten
    if e.get("easing") is not None and e["easing"] not in EASINGS:
        raise _erro(f"efeito {eid}: easing desconhecido '{e['easing']}'")
    out["enabled"] = bool(e.get("enabled", True))
    out["params"] = e.get("params") if isinstance(e.get("params"), dict) else {}
    out["keyframes"] = _valida_keyframes(e.get("keyframes") or {}, eid)
    out["seed"] = int(e["seed"]) & 0xFFFFFFFF if e.get("seed") is not None else seed_de(eid)
    out["layer"] = int(e.get("layer", 0))
    return out


def validate_manifest(m: dict | None) -> dict | None:
    """Valida e NORMALIZA um Motion Manifest. Retorna None para manifest vazio
    (nenhum efeito) — o banco guarda NULL e cortes antigos continuam abrindo.

    Levanta ValueError com mensagem em PT-BR para estrutura inválida; chaves
    desconhecidas são preservadas (um manifest de versão futura não é destruído,
    só o que este motor entende é validado).
    """
    if m is None:
        return None
    if not isinstance(m, dict):
        raise _erro("motion deve ser um objeto {version, effects}")
    effects = m.get("effects", [])
    if not isinstance(effects, list):
        raise _erro("motion.effects deve ser uma lista")
    normalizados = [_valida_efeito(e) for e in effects]
    if not normalizados and not m.get("assets"):
        return None
    out = dict(m)
    out["version"] = int(m.get("version", MANIFEST_VERSION))
    out["effects"] = sorted(normalizados, key=lambda e: (e["start"], e["layer"], e["id"]))
    out["assets"] = m.get("assets") if isinstance(m.get("assets"), list) else []
    return out


def effects_at(manifest: dict | None, t_out: float) -> list[dict]:
    """Efeitos habilitados ativos no instante t (tempo de SAÍDA)."""
    if not manifest:
        return []
    return [e for e in manifest.get("effects", [])
            if e.get("enabled", True) and e["start"] <= t_out < e["end"]]
