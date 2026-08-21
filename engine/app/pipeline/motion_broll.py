"""B-roll (v4 FASE H) — mídia sobre o corte, com o áudio principal intacto.

Um efeito type="broll" do manifest referencia uma mídia da biblioteca do
projeto (target.media_id) e vira um INPUT extra + overlay no filtergraph:

    [N:v]fps=FPS,scale=…,setpts=PTS-STARTPTS+T0/TB[brK]
    [v][brK]overlay=X:Y:eof_action=pass:enable='between(t,T0,T1)'[vbrK]

Regras da validação empírica: setpts alinha o primeiro frame ao início da
janela; eof_action=pass devolve o principal se a mídia acabar antes; fps
normalizado; e o ÁUDIO DO B-ROLL NUNCA É MAPEADO — o áudio principal segue
inalterado por construção (modo Tela cheia troca só a imagem).

Modos: "overlay" (caixa posicionada, x/y/w normalizados) e "fullscreen"
(cobre o quadro). Imagens entram com -loop 1; vídeos aceitam trim_start e
loop. Mídia AUSENTE não derruba o render: o efeito é pulado com aviso e o
corte sai sem aquele b-roll (Entrega 82 — "Mídia ausente" recuperável).
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def collect(manifest: dict | None) -> list[dict]:
    return [e for e in (manifest or {}).get("effects", [])
            if e.get("type") == "broll" and e.get("enabled", True)]


def resolve_media(effect: dict, media_index: dict[str, dict]) -> dict | None:
    """Mídia do efeito; None (com aviso) se ausente da biblioteca/disco."""
    mid = (effect.get("target") or {}).get("media_id")
    m = media_index.get(str(mid or ""))
    if not m:
        log.warning("B-roll %s: mídia %s não está na biblioteca — pulado",
                    effect.get("id"), mid)
        return None
    if not Path(m["path"]).exists():
        log.warning("B-roll %s: arquivo ausente (%s) — pulado; use Relinkar",
                    effect.get("id"), m["path"])
        return None
    return m


def input_args(effect: dict, media: dict, dur_janela: float) -> list[str]:
    """Argumentos do INPUT extra deste b-roll."""
    args: list[str] = []
    eh_imagem = Path(media["path"]).suffix.lower() in IMAGE_EXTS
    params = effect.get("params") or {}
    if eh_imagem:
        args += ["-loop", "1", "-t", f"{dur_janela + 0.5:.3f}"]
    else:
        if params.get("loop"):
            args += ["-stream_loop", "-1"]
        trim = float(params.get("trim_start") or 0.0)
        if trim > 0:
            args += ["-ss", f"{trim:.3f}"]
        args += ["-t", f"{dur_janela + 0.5:.3f}"]
    return [*args, "-i", media["path"]]


def chain(effect: dict, input_index: int, k: int, out_w: int, out_h: int,
          fps: float) -> tuple[str, str]:
    """(cadeia de preparo "[N:v]…[brK]", argumentos do overlay) — quem monta
    os labels do overlay é o filtergraph (consome o [v] corrente)."""
    params = effect.get("params") or {}
    t0, t1 = float(effect["start"]), float(effect["end"])
    modo = str(params.get("mode") or "overlay")
    if modo == "fullscreen":
        # cobre o quadro TODO (cover): escala pelo maior lado e corta o excesso
        escala = (f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
                  f"crop={out_w}:{out_h}")
        x_px, y_px = 0, 0
    else:
        w_norm = min(1.0, max(0.15, float(params.get("w", 0.55))))
        w_px = int(out_w * w_norm) // 2 * 2
        x_px = int(out_w * float(params.get("x", 0.5)) - w_px / 2)
        y_px = int(out_h * float(params.get("y", 0.3)))
        escala = f"scale={w_px}:-2"
    prep = (f"[{input_index}:v]fps={fps:g},{escala},"
            f"setpts=PTS-STARTPTS+{t0:.3f}/TB")
    fade = float(params.get("transition_s") or 0.0) \
        if str(params.get("transition") or "cut") == "fade" else 0.0
    if fade > 0:
        prep += (f",format=yuva420p,fade=t=in:st={t0:.3f}:d={fade:.3f}:alpha=1,"
                 f"fade=t=out:st={max(t0, t1 - fade):.3f}:d={fade:.3f}:alpha=1")
    overlay = (f"overlay={x_px}:{y_px}:eof_action=pass"
               f":enable='between(t,{t0:.3f},{t1:.3f})'")
    return f"{prep}[br{k}]", overlay
