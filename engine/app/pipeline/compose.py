"""Brand Studio (F3): layouts de marca — canvas 9:16 com camadas compostas no render.

O layout persiste no kit (brand_kits.layout) neste formato, com coordenadas
SEMPRE no canvas de referência 1080×1920 (o render escala para prévia/final):

    {
      "version": 2,
      "canvas": {"w": 1080, "h": 1920},
      "background": {"type": "color|gradient|image|video|blur",
                     "color": "#101418", "color2": "#0a0d12",
                     "direction": "vertical|horizontal|diagonal",
                     "path": "...", "blur_sigma": 28},
      "layers": [   # ordem = z (primeiro = fundo, último = topo)
        {"id": "src", "type": "source", "x": 0, "y": 0, "w": 1080, "h": 1920,
         "radius": 0, "border_w": 0, "border_color": "#FFFFFF", "shadow": false,
         "opacity": 1.0, "hidden": false, "locked": false},
        {"id": "...", "type": "image", "path": "...", "x":..., "y":..., "w":..., "h":...,
         "opacity": 1.0, "anim": "none|fade|slide_up|slide_down|slide_left|slide_right",
         "start_s": 0, "end_s": null, "hidden": false},
        {"id": "...", "type": "text", "text": "{titulo}", "x":..., "y":..., "w":...,
         "font": "Montserrat", "size": 64, "color": "#FFFFFF", "bg": "#000000AA"|null,
         "align": "left|center|right", "bold": true,
         "anim": "none|fade|slide_up|scale|bounce", "start_s": 0, "end_s": null},
        {"id": "...", "type": "shape", "x":..., "y":..., "w":..., "h":...,
         "fill": "#FF4757", "radius": 0, "opacity": 1.0, "anim": ..., "start_s": ...},
        {"id": "...", "type": "video", "path": "...", "x":..., "y":..., "w":..., "h":...,
         "loop": true, "radius": 0, "start_s": 0, "end_s": null, "hidden": false},
        {"id": "cap", "type": "captions", "x": 65, "y": 1280, "w": 950}
      ]
    }

Kits SEM layout continuam no pipeline clássico byte a byte (migração de risco
zero); o Estúdio abre kits antigos convertendo os campos legados num layout
equivalente via layout_from_legacy() — nada deixa de abrir. O vídeo decorativo
é sempre mudo; texto usa libass (mesma engine das legendas), então acentos e
fontes embarcadas funcionam igual nas prévias e no final.
"""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)

CANVAS_W, CANVAS_H = 1080, 1920
MAX_LAYERS = 20
LAYER_TYPES = {"source", "image", "text", "shape", "video", "captions"}
BG_TYPES = {"color", "gradient", "image", "video", "blur"}
ANIMS = {"none", "fade", "slide_up", "slide_down", "slide_left", "slide_right",
         "scale", "bounce"}
ANIM_S = 0.35  # duração padrão das animações de entrada

# posições do logo legado (mesma geometria de LOGO_POSITIONS do render clássico)
_LEGACY_LOGO_XY = {"tl": (48, 96), "tr": (CANVAS_W - 194 - 48, 96),
                   "bl": (48, CANVAS_H - 140 - 110), "br": (CANVAS_W - 194 - 48, CANVAS_H - 140 - 110)}


def layout_of(kit: dict | None) -> dict | None:
    """Layout persistido do kit (None = kit legado → pipeline clássico)."""
    if not kit:
        return None
    lay = kit.get("layout")
    if not isinstance(lay, dict) or not lay.get("layers"):
        return None
    return lay


def layout_from_legacy(kit: dict | None) -> dict:
    """Converte um kit legado (logo + posição) num layout equivalente, para o
    Estúdio abrir QUALQUER kit sem falhar. O resultado renderiza igual ao
    pipeline clássico: vídeo em tela cheia + logo no canto + legendas padrão."""
    layers: list[dict] = [{
        "id": "src", "type": "source", "x": 0, "y": 0, "w": CANVAS_W, "h": CANVAS_H,
        "radius": 0, "border_w": 0, "border_color": "#FFFFFF", "shadow": False,
        "opacity": 1.0, "hidden": False, "locked": False,
    }]
    if kit and kit.get("logo_path"):
        x, y = _LEGACY_LOGO_XY.get(kit.get("logo_position") or "tr", _LEGACY_LOGO_XY["tr"])
        layers.append({"id": "logo", "type": "image", "path": kit["logo_path"],
                       "x": x, "y": y, "w": 194, "h": 194,
                       "opacity": float(kit.get("logo_opacity") or 1.0),
                       "anim": "none", "start_s": 0, "end_s": None, "hidden": False})
    layers.append({"id": "cap", "type": "captions", "x": 65, "y": 1280, "w": 950})
    return {"version": 2, "canvas": {"w": CANVAS_W, "h": CANVAS_H},
            "background": {"type": "color", "color": "#000000"}, "layers": layers}


def validate_layout(lay: dict) -> list[str]:
    """Erros estruturais de um layout enviado pelo Estúdio (lista vazia = ok)."""
    erros: list[str] = []
    if not isinstance(lay, dict):
        return ["layout deve ser um objeto"]
    layers = lay.get("layers")
    if not isinstance(layers, list) or not layers:
        return ["layout precisa de pelo menos uma camada"]
    if len(layers) > MAX_LAYERS:
        erros.append(f"máximo de {MAX_LAYERS} camadas")
    bg = lay.get("background") or {}
    if bg and bg.get("type") not in BG_TYPES:
        erros.append(f"fundo inválido: {bg.get('type')}")
    n_source = 0
    for i, layer in enumerate(layers):
        rot = f"camada {i + 1}"
        t = layer.get("type")
        if t not in LAYER_TYPES:
            erros.append(f"{rot}: tipo desconhecido '{t}'")
            continue
        if t == "source":
            n_source += 1
        if t in ("image", "video") and not layer.get("path"):
            erros.append(f"{rot}: falta o arquivo (path)")
        if t == "text" and not (layer.get("text") or "").strip():
            erros.append(f"{rot}: texto vazio")
        for k in ("x", "y"):
            v = layer.get(k, 0)
            if not isinstance(v, (int, float)) or v < -400 or v > 2400:
                erros.append(f"{rot}: {k} fora do canvas")
        for k in ("w", "h"):
            if k == "h" and t in ("text", "captions"):
                continue
            v = layer.get(k, 0)
            if not isinstance(v, (int, float)) or v < 8 or v > 2400:
                erros.append(f"{rot}: {k} inválido")
        anim = layer.get("anim") or "none"
        if anim not in ANIMS:
            erros.append(f"{rot}: animação desconhecida '{anim}'")
    if n_source == 0:
        erros.append("o layout precisa da camada do vídeo do corte (type=source)")
    if n_source > 1:
        erros.append("apenas uma camada de vídeo do corte é permitida")
    return erros


def _visible(lay: dict) -> list[dict]:
    return [layer for layer in lay["layers"] if not layer.get("hidden")]


def source_layer(lay: dict) -> dict:
    for layer in _visible(lay):
        if layer["type"] == "source":
            return layer
    return {"type": "source", "x": 0, "y": 0, "w": CANVAS_W, "h": CANVAS_H}


def caption_overrides(lay: dict) -> dict:
    """Camada 'captions' → overrides de estilo (âncora/margens em 1080×1920)."""
    cap = next((x for x in _visible(lay) if x["type"] == "captions"), None)
    if not cap:
        return {}
    x = int(cap.get("x", 65))
    w = int(cap.get("w", 950))
    return {"anchor_top": int(cap.get("y", 1280)),
            "margin_l": max(0, x), "margin_r": max(0, CANVAS_W - x - w)}


def _even(v: float) -> int:
    return max(2, int(round(v / 2)) * 2)


def box_px(v, scale: float) -> int:
    """Dimensão de camada no canvas escalado (sempre par, exigência dos codecs)."""
    return _even(float(v) * scale)


def _bgr(color: str) -> tuple[int, int, int]:
    c = (color or "#000000").lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return int(c[4:6], 16), int(c[2:4], 16), int(c[0:2], 16)


def _alpha_of(color: str, fallback: float = 1.0) -> float:
    c = (color or "").lstrip("#")
    if len(c) == 8:
        return int(c[6:8], 16) / 255.0
    return fallback


def _ffcolor(color: str) -> str:
    c = (color or "#000000").lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return f"0x{c[:6]}"


def _rounded_rect_mask(w: int, h: int, radius: int) -> np.ndarray:
    """Máscara 0–255 de retângulo com cantos arredondados."""
    m = np.zeros((h, w), dtype=np.uint8)
    r = int(max(0, min(radius, min(w, h) // 2)))
    if r == 0:
        m[:] = 255
        return m
    cv2.rectangle(m, (r, 0), (w - r, h), 255, -1)
    cv2.rectangle(m, (0, r), (w, h - r), 255, -1)
    for cx, cy in ((r, r), (w - r, r), (r, h - r), (w - r, h - r)):
        cv2.circle(m, (cx, cy), r, 255, -1)
    return m


def _write_png(path: Path, bgra: np.ndarray) -> str:
    cv2.imwrite(str(path), bgra)
    return path.name  # caminhos RELATIVOS ao cwd do render (regra do projeto)


def make_shape_png(path: Path, w: int, h: int, fill: str, radius: int) -> str:
    b, g, r = _bgr(fill)
    a = _alpha_of(fill)
    mask = _rounded_rect_mask(w, h, radius)
    img = np.zeros((h, w, 4), dtype=np.uint8)
    img[:, :, 0], img[:, :, 1], img[:, :, 2] = b, g, r
    img[:, :, 3] = (mask.astype(np.float32) * a).astype(np.uint8)
    return _write_png(path, img)


def make_border_png(path: Path, w: int, h: int, radius: int, color: str, width: int) -> str:
    outer = _rounded_rect_mask(w, h, radius)
    inner = np.zeros_like(outer)
    iw, ih = w - 2 * width, h - 2 * width
    if iw > 2 and ih > 2:
        inner[width:h - width, width:w - width] = _rounded_rect_mask(iw, ih, max(0, radius - width))
    ring = cv2.subtract(outer, inner)
    b, g, r = _bgr(color)
    img = np.zeros((h, w, 4), dtype=np.uint8)
    img[:, :, 0], img[:, :, 1], img[:, :, 2] = b, g, r
    img[:, :, 3] = ring
    return _write_png(path, img)


def make_shadow_png(path: Path, w: int, h: int, radius: int, blur: int = 25) -> tuple[str, int]:
    """Sombra suave da caixa; devolve (arquivo, pad) — o overlay desloca -pad."""
    pad = blur * 2
    mask = np.zeros((h + pad * 2, w + pad * 2), dtype=np.uint8)
    mask[pad:pad + h, pad:pad + w] = _rounded_rect_mask(w, h, radius)
    mask = cv2.GaussianBlur(mask, (0, 0), blur)
    img = np.zeros((*mask.shape, 4), dtype=np.uint8)
    img[:, :, 3] = (mask.astype(np.float32) * 0.55).astype(np.uint8)
    return _write_png(path, img), pad


def make_mask_png(path: Path, w: int, h: int, radius: int) -> str:
    m = _rounded_rect_mask(w, h, radius)
    img = cv2.merge([m, m, m])
    return _write_png(path, img)


# ---------------------------------------------------------------- texto (ASS)

_TEXT_ANIM = {
    "fade": "{{\\fad(250,200)}}",
    "slide_up": "{{\\fad(200,150)\\move({mx},{my_from},{mx},{my},0,320)}}",
    "scale": "{{\\fad(150,120)\\fscx78\\fscy78\\t(0,300,\\fscx100\\fscy100)}}",
    "bounce": "{{\\fad(100,100)\\fscx70\\fscy70\\t(0,180,\\fscx112\\fscy112)"
              "\\t(180,320,\\fscx100\\fscy100)}}",
}


def _ass_ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    return f"{h}:{m:02d}:{seconds % 60:05.2f}"


def text_layers_ass(lay: dict, *, titulo: str, out_dur: float) -> str | None:
    """Todas as camadas de texto num único .ass (PlayRes = canvas 1080×1920)."""
    from .captions import hex_to_ass  # noqa: PLC0415

    texts = [x for x in _visible(lay) if x["type"] == "text"]
    if not texts:
        return None
    styles, events = [], []
    for i, t in enumerate(texts):
        font = t.get("font") or "Montserrat"
        size = int(t.get("size") or 64)
        cor = hex_to_ass(t.get("color") or "#FFFFFF")
        bold = -1 if t.get("bold", True) else 0
        bg = t.get("bg")
        if bg:
            a = 255 - int(_alpha_of(bg) * 255)
            back = hex_to_ass(bg[:7], f"{a:02X}")
            border_style, outline = 3, 12
        else:
            back = "&H00000000"
            border_style, outline = 1, 3
        styles.append(
            f"Style: T{i},{font},{size},{cor},{cor},&H00000000,{back},{bold},0,0,0,"
            f"100,100,0,0,{border_style},{outline},0,7,0,0,0,1")
        x, y, w = int(t.get("x", 60)), int(t.get("y", 120)), int(t.get("w", 960))
        align = t.get("align") or "center"
        if align == "center":
            an, px = 8, x + w // 2
        elif align == "right":
            an, px = 9, x + w
        else:
            an, px = 7, x
        anim = t.get("anim") or "none"
        tag = _TEXT_ANIM.get(anim, "")
        tag = tag.format(mx=px, my=y, my_from=y + 46)
        pos = f"{{\\an{an}\\pos({px},{y})}}"
        texto = (t.get("text") or "").replace("{titulo}", titulo or "").strip()
        texto = texto.replace("\n", "\\N")
        ini = float(t.get("start_s") or 0.0)
        fim = t.get("end_s")
        fim = out_dur if fim in (None, 0) else min(float(fim), out_dur)
        if fim > ini and texto:
            events.append(f"Dialogue: {i},{_ass_ts(ini)},{_ass_ts(fim)},T{i},,0,0,0,,"
                          f"{pos}{tag}{texto}")
    if not events:
        return None
    head = ("[Script Info]\nScriptType: v4.00+\n"
            f"PlayResX: {CANVAS_W}\nPlayResY: {CANVAS_H}\nWrapStyle: 2\n"
            "ScaledBorderAndShadow: yes\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n")
    return head + "\n".join(styles) + "\n\n[Events]\nFormat: Layer, Start, End, Style, " \
        "Name, MarginL, MarginR, MarginV, Effect, Text\n" + "\n".join(events) + "\n"


# ---------------------------------------------------------------- composição

def plan_composition(lay: dict, *, scale: float, out_dur: float, workdir: Path,
                     titulo: str) -> dict:
    """Gera os ativos (PNGs via OpenCV, ASS de textos) e lista os arquivos que
    o render deve adicionar como inputs do ffmpeg. Arquivos de camada que não
    existem mais são pulados com aviso (o render nunca falha por um enfeite)."""
    comp: dict = {"files": [], "assets": {}, "text_ass": None, "warnings": []}
    sx = lambda v: _even(float(v) * scale)  # noqa: E731

    bg = lay.get("background") or {}
    if bg.get("type") in ("image", "video"):
        p = bg.get("path") or ""
        if Path(p).exists():
            comp["files"].append({"key": "bg", "kind": "image" if bg["type"] == "image" else "video",
                                  "path": p, "loop": True})
        else:
            comp["warnings"].append(f"fundo: arquivo não encontrado ({p}) — usando cor sólida")

    for i, layer in enumerate(_visible(lay)):
        key = f"L{i}"
        t = layer["type"]
        w, h = sx(layer.get("w", 200)), sx(layer.get("h", 200))
        if t == "source":
            radius = int(round(float(layer.get("radius") or 0) * scale))
            if radius > 0:
                comp["assets"][f"{key}mask"] = make_mask_png(workdir / f"{key}mask.png", w, h, radius)
                comp["files"].append({"key": f"{key}mask", "kind": "image",
                                      "path": str(workdir / f"{key}mask.png"), "loop": True})
            if layer.get("shadow"):
                blur = max(8, int(25 * scale))
                _nome, pad = make_shadow_png(workdir / f"{key}shadow.png", w, h, radius, blur)
                comp["assets"][f"{key}shadowpad"] = pad
                comp["files"].append({"key": f"{key}shadow", "kind": "image",
                                      "path": str(workdir / f"{key}shadow.png"), "loop": True})
            bw = int(round(float(layer.get("border_w") or 0) * scale))
            if bw > 0:
                comp["assets"][f"{key}border"] = make_border_png(
                    workdir / f"{key}border.png", w, h, radius,
                    layer.get("border_color") or "#FFFFFF", bw)
                comp["files"].append({"key": f"{key}border", "kind": "image",
                                      "path": str(workdir / f"{key}border.png"), "loop": True})
        elif t == "shape":
            radius = int(round(float(layer.get("radius") or 0) * scale))
            make_shape_png(workdir / f"{key}.png", w, h, layer.get("fill") or "#FF4757", radius)
            comp["files"].append({"key": key, "kind": "image",
                                  "path": str(workdir / f"{key}.png"), "loop": True})
        elif t in ("image", "video"):
            p = layer.get("path") or ""
            if Path(p).exists():
                comp["files"].append({"key": key, "kind": "image" if t == "image" else "video",
                                      "path": p, "loop": bool(layer.get("loop", True))})
            else:
                comp["warnings"].append(f"camada {i + 1}: arquivo não encontrado ({p}) — pulada")

    comp["text_ass"] = text_layers_ass(lay, titulo=titulo, out_dur=out_dur)
    comp["caption_overrides"] = caption_overrides(lay)
    return comp


def _anim_overlay(layer: dict, x: int, y: int, scale: float) -> tuple[str, str, str]:
    """(x_expr, y_expr, prefiltro_de_fade) da animação de entrada da camada."""
    anim = layer.get("anim") or "none"
    st = float(layer.get("start_s") or 0.0)
    dist = int(60 * scale)
    prog = f"min(1\\,(t-{st:.3f})/{ANIM_S})"
    fade = ""
    if anim != "none":
        fade = f",fade=t=in:st={st:.3f}:d={ANIM_S:.3f}:alpha=1"
    xs, ys = str(x), str(y)
    if anim == "slide_up":
        ys = f"{y}+(1-{prog})*{dist}"
    elif anim == "slide_down":
        ys = f"{y}-(1-{prog})*{dist}"
    elif anim == "slide_left":
        xs = f"{x}+(1-{prog})*{dist}"
    elif anim == "slide_right":
        xs = f"{x}-(1-{prog})*{dist}"
    return xs, ys, fade


def _enable(layer: dict, out_dur: float) -> str:
    ini = float(layer.get("start_s") or 0.0)
    fim = layer.get("end_s")
    fim = None if fim in (None, 0) else float(fim)
    if ini <= 0 and (fim is None or fim >= out_dur):
        return ""
    fim = out_dur if fim is None else min(fim, out_dur)
    return f":enable='between(t\\,{ini:.3f}\\,{fim:.3f})'"


def build_chains(lay: dict, comp: dict, *, scale: float, out_dur: float,
                 base_label: str, bg_src_label: str | None,
                 idx: dict[str, int], subs_file: str | None,
                 text_ass_file: str | None, fonts_dir: str | None,
                 fps: float = 30.0) -> tuple[list[str], str]:
    """Cadeias do filtergraph que compõem o canvas inteiro.

    base_label = vídeo do corte já enquadrado NO TAMANHO da camada source
    (cover). bg_src_label = cópia do mesmo vídeo para fundo 'blur' (ou None).
    idx mapeia comp['files'][key] → índice de input do ffmpeg. O fundo é
    normalizado para o fps da fonte (o overlay herda o clock do fundo)."""
    W, H = _even(CANVAS_W * scale), _even(CANVAS_H * scale)
    sx = lambda v: int(round(float(v) * scale))  # noqa: E731
    chains: list[str] = []
    rate = max(10.0, min(60.0, float(fps or 30.0)))

    bg = lay.get("background") or {"type": "color", "color": "#000000"}
    tipo = bg.get("type") or "color"
    if tipo == "gradient":
        c0, c1 = _ffcolor(bg.get("color") or "#101418"), _ffcolor(bg.get("color2") or "#000000")
        d = bg.get("direction") or "vertical"
        x1, y1 = (W, 0) if d == "horizontal" else (W, H) if d == "diagonal" else (0, H)
        chains.append(f"gradients=s={W}x{H}:c0={c0}:c1={c1}:x0=0:y0=0:x1={x1}:y1={y1}"
                      f":d={out_dur:.3f},fps={rate:g}[bg0]")
    elif tipo in ("image", "video") and "bg" in idx:
        chains.append(f"[{idx['bg']}:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
                      f"crop={W}:{H},setpts=PTS-STARTPTS,fps={rate:g}[bg0]")
    elif tipo == "blur" and bg_src_label:
        sigma = int(bg.get("blur_sigma") or 28)
        chains.append(f"[{bg_src_label}]scale={W}:{H}:force_original_aspect_ratio=increase,"
                      f"crop={W}:{H},gblur=sigma={sigma}[bg0]")
    else:
        chains.append(f"color=c={_ffcolor(bg.get('color') or '#000000')}:s={W}x{H}"
                      f":d={out_dur:.3f}:r={rate:g}[bg0]")

    cur = "bg0"
    n = 0

    def over(top: str, x_expr, y_expr, extra: str = "") -> None:
        nonlocal cur, n
        n += 1
        chains.append(f"[{cur}][{top}]overlay={x_expr}:{y_expr}{extra}[cmp{n}]")
        cur = f"cmp{n}"

    def apply_ass(f: str) -> None:
        nonlocal cur, n
        n += 1
        arg = f"ass={f}"
        if fonts_dir:
            arg += f":fontsdir={fonts_dir}"
        chains.append(f"[{cur}]{arg}[cmp{n}]")
        cur = f"cmp{n}"

    subs_aplicado = text_aplicado = False
    for i, layer in enumerate(_visible(lay)):
        key = f"L{i}"
        t = layer["type"]
        x, y = sx(layer.get("x", 0)), sx(layer.get("y", 0))
        w, h = _even(float(layer.get("w", 200)) * scale), _even(float(layer.get("h", 200)) * scale)
        if t == "source":
            if f"{key}shadow" in idx:
                pad = int(comp["assets"].get(f"{key}shadowpad", 50))
                sh_off = sx(12)
                chains.append(f"[{idx[f'{key}shadow']}:v]format=rgba[shp{n}]")
                over(f"shp{n}", x - pad + sh_off, y - pad + sh_off)
            lbl = base_label
            if f"{key}mask" in idx:
                chains.append(f"[{lbl}]format=rgba[srgba{n}]")
                chains.append(f"[{idx[f'{key}mask']}:v]format=gray[smk{n}]")
                chains.append(f"[srgba{n}][smk{n}]alphamerge[smc{n}]")
                lbl = f"smc{n}"
            op = float(layer.get("opacity", 1.0) or 1.0)
            if op < 0.999:
                chains.append(f"[{lbl}]format=rgba,colorchannelmixer=aa={op:.2f}[sop{n}]")
                lbl = f"sop{n}"
            over(lbl, x, y)
            if f"{key}border" in idx:
                chains.append(f"[{idx[f'{key}border']}:v]format=rgba[sbd{n}]")
                over(f"sbd{n}", x, y)
        elif t in ("image", "shape"):
            if key not in idx:
                continue
            op = float(layer.get("opacity", 1.0) or 1.0)
            fit = ("" if t == "shape"
                   else f"scale={w}:{h}:force_original_aspect_ratio=decrease,")
            opf = f",colorchannelmixer=aa={op:.2f}" if op < 0.999 else ""
            xs, ys, fade = _anim_overlay(layer, x, y, scale)
            chains.append(f"[{idx[key]}:v]{fit}format=rgba{opf}{fade}[ly{n}]")
            over(f"ly{n}", xs, ys, _enable(layer, out_dur))
        elif t == "video":
            if key not in idx:
                continue
            radius = int(round(float(layer.get("radius") or 0) * scale))
            chains.append(f"[{idx[key]}:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
                          f"crop={w}:{h},setpts=PTS-STARTPTS[lv{n}]")
            lbl = f"lv{n}"
            if radius > 0 and f"{key}mask" in comp["assets"]:
                pass  # máscaras de vídeo decorativo ficam para depois (documentado)
            over(lbl, x, y, _enable(layer, out_dur))
        elif t == "captions":
            if subs_file and not subs_aplicado:
                apply_ass(subs_file)
                subs_aplicado = True
        elif t == "text":
            if text_ass_file and not text_aplicado:
                apply_ass(text_ass_file)
                text_aplicado = True
    if text_ass_file and not text_aplicado:
        apply_ass(text_ass_file)
    if subs_file and not subs_aplicado:
        apply_ass(subs_file)
    chains.append(f"[{cur}]format=yuv420p[vcanvas]")
    return chains, "vcanvas"


# ---------------------------------------------------------------- templates

TEMPLATES: list[dict] = [
    {"id": "tela_cheia", "name": "Tela cheia (clássico)",
     "description": "Vídeo ocupa o canvas inteiro; legendas na posição padrão.",
     "layout": {"version": 2, "canvas": {"w": CANVAS_W, "h": CANVAS_H},
                "background": {"type": "color", "color": "#000000"},
                "layers": [
                    {"id": "src", "type": "source", "x": 0, "y": 0, "w": 1080, "h": 1920,
                     "radius": 0, "border_w": 0, "shadow": False, "opacity": 1.0},
                    {"id": "cap", "type": "captions", "x": 65, "y": 1280, "w": 950}]}},
    {"id": "moldura", "name": "Moldura sobre fundo desfocado",
     "description": "Vídeo emoldurado com cantos arredondados e sombra, título no topo.",
     "layout": {"version": 2, "canvas": {"w": CANVAS_W, "h": CANVAS_H},
                "background": {"type": "blur", "blur_sigma": 30},
                "layers": [
                    {"id": "src", "type": "source", "x": 90, "y": 300, "w": 900, "h": 1160,
                     "radius": 36, "border_w": 6, "border_color": "#FFFFFF",
                     "shadow": True, "opacity": 1.0},
                    {"id": "tit", "type": "text", "text": "{titulo}", "x": 70, "y": 130,
                     "w": 940, "font": "Montserrat", "size": 62, "color": "#FFFFFF",
                     "bg": None, "align": "center", "bold": True, "anim": "slide_up",
                     "start_s": 0, "end_s": None},
                    {"id": "cap", "type": "captions", "x": 90, "y": 1540, "w": 900}]}},
    {"id": "faixa_titulo", "name": "Faixa de título",
     "description": "Vídeo em tela cheia com faixa de destaque e título no topo.",
     "layout": {"version": 2, "canvas": {"w": CANVAS_W, "h": CANVAS_H},
                "background": {"type": "color", "color": "#000000"},
                "layers": [
                    {"id": "src", "type": "source", "x": 0, "y": 0, "w": 1080, "h": 1920,
                     "radius": 0, "border_w": 0, "shadow": False, "opacity": 1.0},
                    {"id": "faixa", "type": "shape", "x": 0, "y": 96, "w": 1080, "h": 150,
                     "fill": "#0A0D12B4", "radius": 0, "opacity": 1.0, "anim": "fade",
                     "start_s": 0, "end_s": None},
                    {"id": "tit", "type": "text", "text": "{titulo}", "x": 60, "y": 128,
                     "w": 960, "font": "Montserrat", "size": 56, "color": "#FFFFFF",
                     "bg": None, "align": "center", "bold": True, "anim": "fade",
                     "start_s": 0, "end_s": None},
                    {"id": "cap", "type": "captions", "x": 65, "y": 1280, "w": 950}]}},
    {"id": "podcast_card", "name": "Cartão de podcast",
     "description": "Vídeo no alto sobre fundo em degradê, título embaixo e legendas na base.",
     "layout": {"version": 2, "canvas": {"w": CANVAS_W, "h": CANVAS_H},
                "background": {"type": "gradient", "color": "#1A2230", "color2": "#0A0D12",
                               "direction": "vertical"},
                "layers": [
                    {"id": "src", "type": "source", "x": 60, "y": 170, "w": 960, "h": 1210,
                     "radius": 28, "border_w": 0, "shadow": True, "opacity": 1.0},
                    {"id": "tit", "type": "text", "text": "{titulo}", "x": 80, "y": 1425,
                     "w": 920, "font": "Montserrat", "size": 58, "color": "#FFD400",
                     "bg": None, "align": "center", "bold": True, "anim": "scale",
                     "start_s": 0, "end_s": None},
                    {"id": "cap", "type": "captions", "x": 90, "y": 1560, "w": 900}]}},
]
