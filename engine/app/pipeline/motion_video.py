"""Video FX (v4 FASE F) — efeitos temporais de vídeo do Motion Manifest.

Cada preset é DADO (parâmetros, não função) e compila para um trecho de
filtergraph inserido DEPOIS da base (crop/EDL/scale, onde t = tempo de SAÍDA,
o relógio 00:00 do Editor) e ANTES das legendas — o vídeo treme/zooma/escurece
e o texto continua parado e legível.

As cadeias vêm de validação empírica com ffmpeg real (medição de pixels,
determinismo por hash de frames). Regras herdadas dessa validação:
- resolução SEMPRE injetada numericamente (iw/ih do crop congelam no init do
  grafo quando o scale anterior usa eval=frame — bug real encontrado);
- nada de random(): fases do shake derivam da seed via rng01 e entram como
  NÚMEROS na expressão; mesma seed → mesmo vídeo, "Nova variação" → outra;
- todo efeito é zero fora da própria janela (between/clip) — nenhum estado
  vaza para o resto do clipe.

`video_props_at()` avalia as MESMAS fórmulas para o preview do canvas
(espelhada em TS; bloco video_props de shared/motion-cases.json).
"""

from __future__ import annotations

import math

from . import motion

# ---------------------------------------------------------------------------
# Catálogo declarativo
# ---------------------------------------------------------------------------

VIDEO_PRESETS: dict[str, dict] = {
    "punch_zoom": {
        "id": "punch_zoom", "label": "Punch Zoom", "categoria": "Zoom",
        "descricao": "Zoom seco no impacto com retorno suave.",
        "params": {"amount": 0.12},
    },
    "zoom_out": {
        "id": "zoom_out", "label": "Zoom Out", "categoria": "Zoom",
        "descricao": "Abre o plano: começa fechado e assenta no enquadramento.",
        "params": {"amount": 0.10},
    },
    "shake": {
        "id": "shake", "label": "Shake", "categoria": "Câmera",
        "descricao": "Tremida procedural com decaimento — energia, não terremoto.",
        "params": {"amp": 14.0, "rot": 0.0},
    },
    "impact_shake": {
        "id": "impact_shake", "label": "Impact Shake", "categoria": "Câmera",
        "descricao": "Pancada única: forte no primeiro instante, morre rápido.",
        "params": {"amp": 22.0, "decay": 6.0},
    },
    "rgb_split": {
        "id": "rgb_split", "label": "RGB Split", "categoria": "Glitch",
        "descricao": "Canais vermelho/azul separados — estética de glitch.",
        "params": {"px": 10.0},
    },
    "darken": {
        "id": "darken", "label": "Escurecer", "categoria": "Cena",
        "descricao": "Escurece a cena para destacar o que importa.",
        "params": {"amount": 0.22},
    },
    "flash": {
        "id": "flash", "label": "Flash", "categoria": "Cena",
        "descricao": "Clarão branco que decai em ~150ms.",
        "params": {"amount": 0.42, "decay_s": 0.15},
    },
    "blur_pulse": {
        "id": "blur_pulse", "label": "Blur", "categoria": "Cena",
        "descricao": "Desfoque na janela — transição ou momento de confusão.",
        "params": {"sigma": 9.0},
    },
    "vignette_pulse": {
        "id": "vignette_pulse", "label": "Vinheta", "categoria": "Cena",
        "descricao": "Bordas escuras fecham o olhar no centro.",
        "params": {},
    },
    "grayscale_hit": {
        "id": "grayscale_hit", "label": "Preto e Branco", "categoria": "Cena",
        "descricao": "Drena a cor da cena na janela do efeito.",
        "params": {},
    },
}

# frequências FIXAS do shake (Hz) — o "tom" do tremor é sempre o mesmo;
# a variação por seed entra só nas FASES (rng01)
SHAKE_FREQS = (23.0, 31.0, 29.0, 37.0)


def preset_of(effect: dict) -> dict | None:
    return VIDEO_PRESETS.get(str(effect.get("preset") or ""))


def _p(effect: dict, preset: dict, nome: str, default: float = 0.0) -> float:
    """Parâmetro efetivo: params do efeito > params do preset > default."""
    ep = effect.get("params") or {}
    pp = preset.get("params") or {}
    return float(ep.get(nome, pp.get(nome, default)))


def _fases(seed: int) -> list[float]:
    return [motion.rng01(seed, i) * 2.0 * math.pi for i in range(4)]


def _janela(effect: dict) -> tuple[float, float, float]:
    t0, t1 = float(effect["start"]), float(effect["end"])
    return t0, t1, max(0.05, t1 - t0)


# ---------------------------------------------------------------------------
# Avaliação para o preview (espelhada em TS — videoPropsAt)
# ---------------------------------------------------------------------------

VIDEO_NEUTRAL = {"zoom": 1.0, "dx": 0.0, "dy": 0.0, "rot": 0.0, "darken": 0.0,
                 "blur": 0.0, "gray": 0.0, "flash": 0.0, "rgb": 0.0}


def _smooth(u: float) -> float:
    u = 0.0 if u < 0.0 else 1.0 if u > 1.0 else u
    return u * u * (3.0 - 2.0 * u)


def _clip01(u: float) -> float:
    return 0.0 if u < 0.0 else 1.0 if u > 1.0 else u


def video_props_at(effect: dict, preset: dict, t: float) -> dict:
    """Estado do vídeo no instante t (tempo de SAÍDA) — mesmas fórmulas que as
    expressões do filtergraph avaliam frame a frame."""
    props = dict(VIDEO_NEUTRAL)
    t0, t1, dur = _janela(effect)
    if not effect.get("enabled", True) or t < t0 or t >= t1:
        return props
    k = motion.intensity_k(effect.get("intensity", "normal"))
    pid = preset["id"]
    ts = t - t0
    if pid == "punch_zoom":
        am = _p(effect, preset, "amount") * k
        attack = min(0.18, dur * 0.35)
        release = dur - attack
        props["zoom"] = 1.0 + am * (_clip01(ts / attack)
                                    - _smooth(_clip01((ts - attack) / release)))
    elif pid == "zoom_out":
        am = _p(effect, preset, "amount") * k
        props["zoom"] = 1.0 + am * (1.0 - _smooth(_clip01(ts / dur)))
    elif pid in ("shake", "impact_shake"):
        amp = _p(effect, preset, "amp") * k
        f = _fases(int(effect.get("seed") or 1))
        env = (math.exp(-_p(effect, preset, "decay", 6.0) * ts / dur)
               if pid == "impact_shake" else max(0.0, 1.0 - ts / dur))
        f1, f2, f3, f4 = SHAKE_FREQS
        props["dx"] = amp * env * (0.6 * math.sin(2 * math.pi * f1 * ts + f[0])
                                   + 0.4 * math.sin(2 * math.pi * f2 * ts + f[1]))
        props["dy"] = amp * env * (0.6 * math.sin(2 * math.pi * f3 * ts + f[2])
                                   + 0.4 * math.sin(2 * math.pi * f4 * ts + f[3]))
    elif pid == "rgb_split":
        props["rgb"] = _p(effect, preset, "px") * k
    elif pid == "darken":
        props["darken"] = min(0.85, _p(effect, preset, "amount") * k)
    elif pid == "flash":
        decay = _p(effect, preset, "decay_s", 0.15)
        props["flash"] = min(1.0, _p(effect, preset, "amount") * k) \
            * max(0.0, 1.0 - ts / decay)
    elif pid == "blur_pulse":
        props["blur"] = _p(effect, preset, "sigma") * k
    elif pid == "vignette_pulse":
        props["darken"] = 0.12  # aproximação do preview; o render usa vignette real
    elif pid == "grayscale_hit":
        props["gray"] = 1.0
    return props


# ---------------------------------------------------------------------------
# Compilação → filtergraph
# ---------------------------------------------------------------------------


def _fx_chain(effect: dict, preset: dict, w: int, h: int) -> str | None:
    """Trecho de filtro do efeito (sem labels), com t = tempo de SAÍDA."""
    t0, t1, dur = _janela(effect)
    k = motion.intensity_k(effect.get("intensity", "normal"))
    pid = preset["id"]
    ent = f"between(t,{t0:.3f},{t1:.3f})"
    if pid in ("punch_zoom", "zoom_out"):
        am = _p(effect, preset, "amount") * k
        if pid == "punch_zoom":
            attack = min(0.18, dur * 0.35)
            release = dur - attack
            z = (f"(1+{am:.4f}*(clip((t-{t0:.3f})/{attack:.3f},0,1)"
                 f"-st(0,clip((t-{t0 + attack:.3f})/{release:.3f},0,1))"
                 f"*ld(0)*(3-2*ld(0))))")
        else:
            z = (f"(1+{am:.4f}*{ent}*(1-st(0,clip((t-{t0:.3f})/{dur:.3f},0,1))"
                 f"*ld(0)*(3-2*ld(0))))")
        # resolução injetada numericamente: iw/ih do crop congelam no init
        # quando o scale usa eval=frame (bug encontrado na validação empírica)
        return (f"scale=w='trunc({w}*{z}/2)*2':h='trunc({h}*{z}/2)*2'"
                f":eval=frame:flags=bicubic,"
                f"crop={w}:{h}:'{w}*({z}-1)/2':'{h}*({z}-1)/2'")
    if pid in ("shake", "impact_shake"):
        amp = _p(effect, preset, "amp") * k
        m = int(math.ceil(amp) + 4)
        m += m % 2  # margem par (croma 4:2:0)
        f = _fases(int(effect.get("seed") or 1))
        env = (f"exp(-{_p(effect, preset, 'decay', 6.0):.2f}*(t-{t0:.3f})/{dur:.3f})"
               if pid == "impact_shake"
               else f"max(0\\,1-(t-{t0:.3f})/{dur:.3f})")
        f1, f2, f3, f4 = SHAKE_FREQS
        sx = (f"(0.6*sin(2*PI*{f1}*(t-{t0:.3f})+{f[0]:.4f})"
              f"+0.4*sin(2*PI*{f2}*(t-{t0:.3f})+{f[1]:.4f}))")
        sy = (f"(0.6*sin(2*PI*{f3}*(t-{t0:.3f})+{f[2]:.4f})"
              f"+0.4*sin(2*PI*{f4}*(t-{t0:.3f})+{f[3]:.4f}))")
        return (f"pad=iw+{2 * m}:ih+{2 * m}:{m}:{m},"
                f"crop=iw-{2 * m}:ih-{2 * m}"
                f":x='{m}+{ent}*{amp:.2f}*{env}*{sx}'"
                f":y='{m}+{ent}*{amp:.2f}*{env}*{sy}'")
    if pid == "rgb_split":
        px = int(round(_p(effect, preset, "px") * k * w / 1080.0)) or 1
        return f"rgbashift=rh={px}:bh={-px}:edge=smear:enable='{ent}'"
    if pid == "darken":
        am = min(0.85, _p(effect, preset, "amount") * k)
        return f"eq=brightness=-{am:.3f}:saturation=0.9:enable='{ent}'"
    if pid == "flash":
        am = min(1.0, _p(effect, preset, "amount") * k)
        decay = _p(effect, preset, "decay_s", 0.15)
        return (f"eq=brightness='{am:.3f}*{ent}"
                f"*max(0\\,1-(t-{t0:.3f})/{decay:.3f})':eval=frame")
    if pid == "blur_pulse":
        # sigma é definido na referência 1080 e escala com a resolução real —
        # prévia 540 e final 1080 têm o MESMO grau de desfoque aparente
        sigma = max(0.5, _p(effect, preset, "sigma") * k * w / 1080.0)
        return f"gblur=sigma={sigma:.2f}:enable='{ent}'"
    if pid == "vignette_pulse":
        return f"vignette=angle=PI/4.4:enable='{ent}'"
    if pid == "grayscale_hit":
        return f"hue=s=0:enable='{ent}'"
    return None


def compile_video_fx(manifest: dict | None, out_w: int, out_h: int) -> list[str]:
    """Cadeias de FX do manifest, em ordem DETERMINÍSTICA (a do manifest
    normalizado: start, layer, id). Presets desconhecidos são ignorados —
    um manifest de versão futura não derruba o render."""
    chains: list[str] = []
    for e in (manifest or {}).get("effects", []):
        if e.get("type") != "video_fx" or not e.get("enabled", True):
            continue
        preset = preset_of(e)
        if not preset:
            continue
        chain = _fx_chain(e, preset, out_w, out_h)
        if chain:
            chains.append(chain)
    if chains:
        chains[-1] += ",format=yuv420p"  # rgbashift & cia. voltam ao 4:2:0
    return chains
