"""Renderização: filtergraph único (trim/crop/concat → scale → legendas ASS → logo →
censura de áudio → loudnorm) em uma passada de ffmpeg, com input seeking (-ss/-to)
para fontes longas. Tempos internos são RELATIVOS ao clipe.
"""

from __future__ import annotations

import logging
import re
import shutil
import tempfile
import unicodedata
from pathlib import Path

from sqlalchemy import select

from .. import config
from ..db import settings_store
from ..db.base import session
from ..db.models import (
    BrandKit,
    CutCandidate,
    Render,
    RenderBatch,
    SourceVideo,
    Transcript,
    TranscriptWord,
    utcnow,
)
from ..jobs.registry import job_handler
from ..services import ffmpeg
from . import captions, censor, compose, motion_callout, motion_video
from . import edl as edl_mod
from .reframe import apply_framing_override, apply_punch_in, apply_segment_overrides, plan_crop

log = logging.getLogger(__name__)

LOGO_POSITIONS = {
    "tl": ("48", "96"),
    "tr": ("W-w-48", "96"),
    "bl": ("48", "H-h-140"),
    "br": ("W-w-48", "H-h-140"),
}


def slugify(text: str, max_len: int = 48) -> str:
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:max_len] or "corte"


def _fade_tags(item: dict, *, audio: bool) -> str:
    """Sufixo de filtros fade/afade de junção de um pedaço já em tempo local (pós-setpts)."""
    dur = item["end"] - item["start"]
    f = "afade" if audio else "fade"
    out = ""
    if item.get("fade_in"):
        out += f",{f}=t=in:st=0:d={item['fade_in']:.3f}"
    if item.get("fade_out"):
        out += f",{f}=t=out:st={max(0.0, dur - item['fade_out']):.3f}:d={item['fade_out']:.3f}"
    return out


def _video_base_chains(*, crop_plan: dict, video_trims: list[dict] | None,
                       out_w: int, out_h: int, fit: str = "stretch") -> tuple[list[str], str]:
    """Cadeias do vídeo-base (EDL + enquadramento) até [vbase] em out_w×out_h.

    fit="stretch" é o caminho clássico (o plano de crop já tem a proporção da
    saída); fit="cover" preenche caixas de proporção arbitrária do Brand Studio."""
    chains: list[str] = []
    if fit == "cover":
        final_scale = (f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase:"
                       f"flags=lanczos,crop={out_w}:{out_h}")
    else:
        final_scale = f"scale={out_w}:{out_h}:flags=lanczos"
    mode = crop_plan.get("mode")
    if mode in ("blur_pad", "fit_pad", "two_person", "split_screen"):
        src_v = "0:v"
        if video_trims and len(video_trims) > 1:
            n = len(video_trims)
            chains.append(f"[0:v]split={n}" + "".join(f"[bt{i}]" for i in range(n)))
            for i, tr in enumerate(video_trims):
                chains.append(f"[bt{i}]trim={tr['start']:.3f}:{tr['end']:.3f},"
                              f"setpts=PTS-STARTPTS{_fade_tags(tr, audio=False)}[bc{i}]")
            chains.append("".join(f"[bc{i}]" for i in range(n)) +
                          f"concat=n={n}:v=1:a=0[vcut]")
            src_v = "vcut"
        if mode == "blur_pad":
            chains.append(f"[{src_v}]split=2[bgsrc][fgsrc]")
            chains.append(f"[bgsrc]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
                          f"crop={out_w}:{out_h},gblur=sigma=28[bg]")
            chains.append(f"[fgsrc]scale={out_w}:-2[fg]")
            chains.append("[bg][fg]overlay=(W-w)/2:(H-h)/2[vbase]")
        elif mode == "fit_pad":
            # vídeo INTEIRO (sem corte) com barras — modo "Fit"
            chains.append(f"[{src_v}]scale={out_w}:{out_h}:force_original_aspect_ratio="
                          f"decrease:flags=lanczos,"
                          f"pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2:black[vbase]")
        else:
            # duas pessoas: painéis empilhados (two_person) ou lado a lado (split_screen)
            panels = crop_plan.get("panels") or [{"x": 0}, {"x": 0}]
            cw, ch = crop_plan["crop_w"], crop_plan["crop_h"]
            if mode == "two_person":
                pw, ph, stack = out_w, out_h // 2, "vstack"
            else:
                pw, ph, stack = out_w // 2, out_h, "hstack"
            chains.append(f"[{src_v}]split=2[p0][p1]")
            for i, p in enumerate(panels[:2]):
                chains.append(f"[p{i}]crop={cw}:{ch}:{p['x']}:0,"
                              f"scale={pw}:{ph}:flags=lanczos[pp{i}]")
            chains.append(f"[pp0][pp1]{stack}[vbase]")
    else:
        segs = crop_plan["segments"]
        crop_w, crop_h = crop_plan["crop_w"], crop_plan["crop_h"]

        def _zoom_geom(seg: dict) -> tuple[int, int, int, int]:
            """(cw, ch, dx, dy) do punch-in do segmento (zoom central)."""
            z = float(seg.get("zoom") or 1.0)
            if z <= 1.001:
                return crop_w, crop_h, 0, 0
            cw2 = max(2, int(crop_w / z) // 2 * 2)
            ch2 = max(2, int(crop_h / z) // 2 * 2)
            return cw2, ch2, (crop_w - cw2) // 2, (crop_h - ch2) // 2

        if len(segs) == 1 and segs[0]["x0"] == segs[0]["x1"] and \
                not segs[0].get("fade_in") and not segs[0].get("fade_out") and \
                not segs[0].get("zoom"):
            chains.append(f"[0:v]crop={crop_w}:{crop_h}:{segs[0]['x0']}:0,"
                          f"{final_scale}[vbase]")
        else:
            chains.append(f"[0:v]split={len(segs)}" + "".join(f"[s{i}]" for i in range(len(segs))))
            for i, seg in enumerate(segs):
                d = max(0.05, seg["end"] - seg["start"])
                cw2, ch2, dx, dy = _zoom_geom(seg)
                if seg["x0"] == seg["x1"]:
                    x_expr = str(seg["x0"] + dx)
                else:
                    x_expr = f"{seg['x0'] + dx}+({seg['x1']}-{seg['x0']})*(t/{d:.3f})"
                piece = (f"[s{i}]trim={seg['start']:.3f}:{seg['end']:.3f},"
                         f"setpts=PTS-STARTPTS,crop={cw2}:{ch2}:{x_expr}:{dy}")
                if (cw2, ch2) != (crop_w, crop_h):
                    # zoom muda a dimensão do pedaço: volta ao tamanho comum p/ o concat
                    piece += f",scale={crop_w}:{crop_h}:flags=lanczos"
                chains.append(piece + f"{_fade_tags(seg, audio=False)}[c{i}]")
            concat_in = "".join(f"[c{i}]" for i in range(len(segs)))
            chains.append(f"{concat_in}concat=n={len(segs)}:v=1:a=0,"
                          f"{final_scale}[vbase]")
    return chains, "vbase"


def _global_fade_chain(v: str, video_fades: dict | None, duration: float) -> tuple[str | None, str]:
    """Fade global de entrada/saída sobre a composição pronta."""
    fades = video_fades or {}
    fi, fo = float(fades.get("fade_in_s") or 0.0), float(fades.get("fade_out_s") or 0.0)
    if fi <= 0 and fo <= 0:
        return None, v
    parts = []
    if fi > 0:
        parts.append(f"fade=t=in:st=0:d={fi:.3f}")
    if fo > 0:
        parts.append(f"fade=t=out:st={max(0.0, duration - fo):.3f}:d={fo:.3f}")
    return f"[{v}]{','.join(parts)}[vfade]", "vfade"


def _audio_chains(*, censor_intervals: list[dict], censor_mode: str,
                  beep_input_index: int | None, audio_chunks: list[dict] | None,
                  audio_fx: dict | None, duration: float) -> tuple[list[str], str]:
    """Áudio completo: seleção EDL → ganho/mute/fades → censura → loudnorm."""
    chains: list[str] = []
    a = "0:a"
    if audio_chunks and len(audio_chunks) > 1:
        n = len(audio_chunks)
        chains.append(f"[0:a]asplit={n}" + "".join(f"[aa{i}]" for i in range(n)))
        for i, ch in enumerate(audio_chunks):
            chains.append(f"[aa{i}]atrim={ch['start']:.3f}:{ch['end']:.3f},"
                          f"asetpts=PTS-STARTPTS{_fade_tags(ch, audio=True)}[ac{i}]")
        chains.append("".join(f"[ac{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[acat]")
        a = "acat"
    fx = audio_fx or {}
    if fx.get("mute"):
        chains.append(f"[{a}]volume=0[amuteall]")
        a = "amuteall"
    else:
        gain = float(fx.get("gain_db") or 0.0)
        if abs(gain) >= 0.05:
            chains.append(f"[{a}]volume={gain:+.1f}dB[again]")
            a = "again"
        afi, afo = float(fx.get("fade_in_s") or 0.0), float(fx.get("fade_out_s") or 0.0)
        if afi > 0 or afo > 0:
            parts = []
            if afi > 0:
                parts.append(f"afade=t=in:st=0:d={afi:.3f}")
            if afo > 0:
                parts.append(f"afade=t=out:st={max(0.0, duration - afo):.3f}:d={afo:.3f}")
            chains.append(f"[{a}]{','.join(parts)}[afades]")
            a = "afades"
    if censor_intervals:
        enable = "+".join(f"between(t\\,{i['start']:.3f}\\,{i['end']:.3f})"
                          for i in censor_intervals)
        chains.append(f"[{a}]volume=enable='{enable}':volume=0[amute]")
        a = "amute"
        if censor_mode == "beep" and beep_input_index is not None:
            not_enable = f"1-min(1\\,{enable})"
            chains.append(f"[{beep_input_index}:a]volume=0.35,"
                          f"volume=enable='{not_enable}':volume=0[beepg]")
            chains.append(f"[{a}][beepg]amix=inputs=2:duration=first:normalize=0[amix]")
            a = "amix"
    chains.append(f"[{a}]loudnorm=I=-14:TP=-1.5:LRA=11[aout]")
    return chains, "[aout]"


def build_filtergraph(*, crop_plan: dict, duration: float, out_w: int, out_h: int,
                      subs_file: str | None, fonts_dir: str | None,
                      censor_intervals: list[dict], censor_mode: str,
                      logo: dict | None, beep_input_index: int | None,
                      logo_input_index: int | None,
                      video_trims: list[dict] | None = None,
                      audio_chunks: list[dict] | None = None,
                      audio_fx: dict | None = None,
                      video_fades: dict | None = None,
                      fx_chains: list[str] | None = None) -> tuple[str, str, str]:
    """Grafo clássico (tela cheia): retorna (filter_complex, video_label, audio_label).

    EDL: em modo crop os trims vêm embutidos nos segments do crop_plan (tempo
    do INPUT + fades de junção); em blur_pad chegam via `video_trims`. O áudio
    segue a MESMA EDL via `audio_chunks` (atrim/concat), depois `audio_fx`
    (ganho/mute/fades) e `video_fades` (fades globais do clipe). Todos os
    parâmetros novos são opcionais — ausentes, o grafo é o clássico de 1 trecho.
    `duration` é a duração de SAÍDA (base dos fades globais)."""
    chains, v = _video_base_chains(crop_plan=crop_plan, video_trims=video_trims,
                                   out_w=out_w, out_h=out_h)
    # Video FX do Motion Manifest: depois da base (t = tempo de SAÍDA) e ANTES
    # das legendas — o vídeo treme/zooma/escurece, o texto continua parado
    for i, fx in enumerate(fx_chains or []):
        chains.append(f"[{v}]{fx}[vfx{i}]")
        v = f"vfx{i}"
    if subs_file:
        ass_arg = f"ass={subs_file}"
        if fonts_dir:
            ass_arg += f":fontsdir={fonts_dir}"
        chains.append(f"[{v}]{ass_arg}[vsub]")
        v = "vsub"
    if logo is not None and logo_input_index is not None:
        logo_w = int(out_w * 0.18)
        opacity = float(logo.get("opacity", 1.0))
        x, y = LOGO_POSITIONS.get(logo.get("position", "tr"), LOGO_POSITIONS["tr"])
        chains.append(f"[{logo_input_index}:v]scale={logo_w}:-1,format=rgba,"
                      f"colorchannelmixer=aa={opacity:.2f}[logo]")
        chains.append(f"[{v}][logo]overlay={x}:{y}[vlogo]")
        v = "vlogo"
    fade_chain, v = _global_fade_chain(v, video_fades, duration)
    if fade_chain:
        chains.append(fade_chain)
    a_chains, a_label = _audio_chains(censor_intervals=censor_intervals,
                                      censor_mode=censor_mode,
                                      beep_input_index=beep_input_index,
                                      audio_chunks=audio_chunks, audio_fx=audio_fx,
                                      duration=duration)
    chains += a_chains
    return ";".join(chains), f"[{v}]", a_label


def _fades_de_juncao(items: list[dict], transition_s: float) -> None:
    """Marca fade-out/fade-in nos pedaços vizinhos de cada junção da EDL.

    Emendas internas do plano de crop (mesmo edl_seg) não recebem fade — são
    trocas de enquadramento, não cortes de edição."""
    if transition_s <= 0:
        return
    for prev, nxt in zip(items, items[1:], strict=False):
        if prev.get("edl_seg") == nxt.get("edl_seg"):
            continue
        d_out = min(transition_s, max(0.0, (prev["end"] - prev["start"]) / 2))
        d_in = min(transition_s, max(0.0, (nxt["end"] - nxt["start"]) / 2))
        if d_out >= 0.03:
            prev["fade_out"] = round(d_out, 3)
        if d_in >= 0.03:
            nxt["fade_in"] = round(d_in, 3)


def _load_render_bundle(render_id: str) -> dict:
    with session() as s:
        r = s.get(Render, render_id)
        if r is None:
            raise ValueError(f"Render {render_id} não existe")
        cut = s.get(CutCandidate, r.cut_id)
        if cut is None:
            raise ValueError("Corte do render não existe mais")
        src = s.get(SourceVideo, cut.source_video_id)
        if src is None or not src.file_path:
            raise ValueError("Fonte do corte indisponível")
        kit = None
        kit_id = r.brand_kit_id or cut.brand_kit_id
        if kit_id:
            k = s.get(BrandKit, kit_id)
            if k is not None:
                kit = {"id": k.id, "logo_path": k.logo_path, "logo_position": k.logo_position,
                       "logo_opacity": k.logo_opacity, "primary_color": k.primary_color,
                       "secondary_color": k.secondary_color, "font_family": k.font_family,
                       "caption_preset": k.caption_preset, "caption_style": k.caption_style,
                       "layout": k.layout, "headline_template": k.headline_template}
        t = s.execute(select(Transcript).where(Transcript.source_video_id == src.id)
                      .order_by(Transcript.created_at.desc())).scalars().first()
        eff = edl_mod.cut_edl({"edl": cut.edl, "start_s": cut.start_s, "end_s": cut.end_s})
        env_a, env_b = edl_mod.envelope(eff)
        words: list[dict] = []
        if t is not None:
            rows = s.execute(select(TranscriptWord)
                             .where(TranscriptWord.transcript_id == t.id,
                                    TranscriptWord.end_s > env_a,
                                    TranscriptWord.start_s < env_b)
                             .order_by(TranscriptWord.idx)).scalars().all()
            words = [{"idx": w.idx, "start_s": w.start_s, "end_s": w.end_s, "word": w.word}
                     for w in rows]
        return {
            "render": {"id": r.id, "kind": r.kind, "overrides": r.preset_snapshot or {}},
            "cut": {"id": cut.id, "start_s": cut.start_s, "end_s": cut.end_s,
                    "title": cut.title, "caption_style": cut.caption_style,
                    "censor_plan": cut.censor_plan, "crop_plan": cut.crop_plan,
                    "edits": cut.edits, "edl": cut.edl, "motion": cut.motion,
                    "edit_revision": cut.edit_revision or 1},
            "source": {"id": src.id, "file_path": src.file_path,
                       "width": src.width or 1920, "height": src.height or 1080,
                       "fps": src.fps or 30.0},
            "kit": kit, "words": words,
        }


def _update_render(render_id: str, **fields) -> None:
    with session() as s:
        r = s.get(Render, render_id)
        if r is None:
            return
        for k, v in fields.items():
            setattr(r, k, v)
        if fields.get("status") in ("done", "failed", "canceled") and r.batch_id:
            batch = s.get(RenderBatch, r.batch_id)
            if batch is not None:
                batch.done += 1
                if batch.done >= batch.total:
                    batch.status = "done"


def bundled_fonts_dir() -> str | None:
    fonts = config.ASSETS_DIR / "fonts"
    if fonts.exists() and any(fonts.glob("*.ttf")):
        return str(fonts)
    return None


@job_handler("render_cut", lane="render")
def render_cut(ctx) -> dict:
    render_id = ctx.payload["render_id"]
    bundle = _load_render_bundle(render_id)
    cut, src, kit = bundle["cut"], bundle["source"], bundle["kit"]
    overrides = bundle["render"]["overrides"]
    kind = bundle["render"]["kind"]
    # A MESMA EDL dirige prévia e render final; cortes sem EDL usam a implícita
    # [start_s → end_s] — o caminho clássico, byte a byte.
    edl = edl_mod.cut_edl(cut)
    env_a, env_b = edl_mod.envelope(edl)
    in_dur = env_b - env_a          # janela decodificada do input (-ss/-t)
    duration = edl_mod.out_duration(edl)   # duração de SAÍDA do clipe
    multi = len(edl["segments"]) > 1

    # carimba a revisão de edição que ESTE render materializa (o corte é lido
    # agora, na execução): é a base do aviso "render desatualizado"
    _update_render(render_id, status="running", started_at=utcnow(),
                   edit_revision=cut.get("edit_revision") or 1)
    ctx.publish("render.progress", {"render_id": render_id, "progress": 0.0, "status": "running"})
    ctx.report(stage="render", progress=0.0, message=f"Renderizando {kind}…", force=True)

    out_w, out_h = (540, 960) if kind == "preview" else (1080, 1920)
    crf = "28" if kind == "preview" else str(overrides.get("crf", 19))
    preset = overrides.get("video_preset", "ultrafast" if kind == "preview" else "veryfast")

    crop_plan = cut["crop_plan"]
    if not crop_plan:
        ctx.report(stage="render", message="Calculando enquadramento…", force=True)
        crop_plan = plan_crop(src["file_path"], env_a, env_b, src["width"], src["height"],
                              cancel_check=ctx.check_cancel)
        with session() as s:
            row = s.get(CutCandidate, cut["id"])
            if row is not None:
                row.crop_plan = crop_plan
    edits = cut["edits"] or {}
    crop_plan = apply_framing_override(crop_plan, edits.get("framing"),
                                       src["width"], src["height"], env_a, env_b)
    crop_plan = apply_segment_overrides(crop_plan, edits.get("framing_segments"),
                                        src["width"])
    crop_plan = apply_punch_in(crop_plan, edits.get("punch_in"))
    plan_rel = edl_mod.slice_crop_plan(crop_plan, edl)
    video_trims = None
    if plan_rel.get("mode") in ("blur_pad", "fit_pad", "two_person", "split_screen"):
        if multi:  # modos sem segmentos também precisam selecionar os trechos da EDL
            video_trims = [{"start": round(a - env_a, 3), "end": round(b - env_a, 3),
                            "edl_seg": i}
                           for i, (a, b) in enumerate(edl_mod.segments_of(edl))]
            _fades_de_juncao(video_trims, edl["transition_s"])
    else:
        # pedaços com trim em tempo do INPUT (fonte − env_a) + fades de junção
        graph_segs = [{"start": round(p["src_start"] - env_a, 3),
                       "end": round(p["src_end"] - env_a, 3),
                       "x0": p["x0"], "x1": p["x1"], "edl_seg": p["edl_seg"]}
                      for p in plan_rel["segments"]]
        _fades_de_juncao(graph_segs, edl["transition_s"])
        plan_rel = {**plan_rel, "segments": graph_segs}

    audio_sel = None
    if multi:
        audio_sel = [{**ch, "edl_seg": i}
                     for i, ch in enumerate(edl_mod.audio_chunks(edl, env_a))]
        _fades_de_juncao(audio_sel, edl["transition_s"])

    words_rel = edl_mod.map_words(bundle["words"], edl, cut["edits"])
    caption_style = overrides.get("caption_style") or cut["caption_style"]
    headline = overrides.get("headline")
    if headline is None and kit and kit.get("headline_template"):
        headline = kit["headline_template"].replace("{titulo}", cut["title"] or "")

    # Brand Studio: kit com layout → composição de canvas em camadas.
    # Kits sem layout seguem o pipeline clássico byte a byte.
    lay = compose.layout_of(kit)
    scale_c = out_w / compose.CANVAS_W
    if lay is not None:
        headline = None  # {titulo} é camada de texto do layout, não evento no subs.ass
        caption_style = {**(caption_style or {}), **compose.caption_overrides(lay)}

    censor_enabled = overrides.get("censor_enabled")
    if censor_enabled is None:
        censor_enabled = bool(settings_store.get_setting("censor_enabled"))
    censor_mode = overrides.get("censor_mode") or settings_store.get_setting("censor_mode") or "beep"
    intervals: list[dict] = []
    if censor_enabled and not edl["audio"]["mute"]:
        if cut["censor_plan"]:
            intervals = edl_mod.map_intervals(cut["censor_plan"], edl)
        else:
            extra = settings_store.get_setting("censor_extra_words") or []
            intervals = censor.find_intervals(words_rel, censor.load_wordlist(extra))

    logo = None
    if lay is None and kit and kit.get("logo_path") and Path(kit["logo_path"]).exists():
        logo = {"path": kit["logo_path"], "position": kit.get("logo_position", "tr"),
                "opacity": kit.get("logo_opacity", 1.0)}

    workdir = Path(tempfile.mkdtemp(prefix="render_", dir=config.data_dir() / "tmp"))
    try:
        subs_file = None
        if words_rel or headline:
            ass_text = captions.build_ass(words_rel, caption_style, kit, headline=headline,
                                          clip_duration=duration,
                                          fps=float(src.get("fps") or 30.0),
                                          edits=cut["edits"],
                                          motion=cut.get("motion"))
            (workdir / "subs.ass").write_text(ass_text, encoding="utf-8")
            subs_file = "subs.ass"
        comp = None
        text_ass_file = None
        if lay is not None:
            comp = compose.plan_composition(lay, scale=scale_c, out_dur=duration,
                                            workdir=workdir, titulo=cut["title"] or "")
            for aviso in comp["warnings"]:
                log.warning("layout do kit: %s", aviso)
            if comp["text_ass"]:
                (workdir / "layout.ass").write_text(comp["text_ass"], encoding="utf-8")
                text_ass_file = "layout.ass"
        fonts_dir = None
        if (subs_file or text_ass_file) and bundled_fonts_dir():
            shutil.copytree(bundled_fonts_dir(), workdir / "fonts", dirs_exist_ok=True)
            fonts_dir = "fonts"

        args: list[str] = ["-ss", f"{env_a:.3f}", "-t", f"{in_dur:.3f}", "-i", src["file_path"]]
        next_idx = 1
        logo_idx = beep_idx = None
        if logo is not None:
            args += ["-i", logo["path"]]
            logo_idx = next_idx
            next_idx += 1
        if intervals and censor_mode == "beep":
            args += ["-f", "lavfi", "-t", f"{duration:.3f}", "-i", "sine=frequency=1000"]
            beep_idx = next_idx
            next_idx += 1
        idx_map: dict[str, int] = {}
        if comp is not None:
            for extra in comp["files"]:
                if extra["kind"] == "image":
                    args += ["-loop", "1", "-t", f"{duration:.3f}", "-i", extra["path"]]
                else:
                    if extra.get("loop", True):
                        args += ["-stream_loop", "-1"]
                    args += ["-t", f"{duration:.3f}", "-i", extra["path"]]
                idx_map[extra["key"]] = next_idx
                next_idx += 1

        if lay is None:
            graph, v_label, a_label = build_filtergraph(
                crop_plan=plan_rel, duration=duration, out_w=out_w, out_h=out_h,
                subs_file=subs_file, fonts_dir=fonts_dir, censor_intervals=intervals,
                censor_mode=censor_mode, logo=logo, beep_input_index=beep_idx,
                logo_input_index=logo_idx, video_trims=video_trims, audio_chunks=audio_sel,
                audio_fx=edl["audio"],
                video_fades={"fade_in_s": edl["fade_in_s"], "fade_out_s": edl["fade_out_s"]},
                fx_chains=motion_video.compile_video_fx(cut.get("motion"), out_w, out_h)
                + [c for e, pr in motion_callout.collect(cut.get("motion"))
                   if (c := motion_callout.background_chain(e, pr, out_w, out_h))])
        else:
            src_l = compose.source_layer(lay)
            box_w = compose.box_px(src_l.get("w", 1080), scale_c)
            box_h = compose.box_px(src_l.get("h", 1920), scale_c)
            chains, vb = _video_base_chains(crop_plan=plan_rel, video_trims=video_trims,
                                            out_w=box_w, out_h=box_h, fit="cover")
            for fx_i, fx in enumerate(
                    motion_video.compile_video_fx(cut.get("motion"), box_w, box_h)
                    + [c for e, pr in motion_callout.collect(cut.get("motion"))
                       if (c := motion_callout.background_chain(e, pr, box_w, box_h))]):
                chains.append(f"[{vb}]{fx}[vmfx{fx_i}]")
                vb = f"vmfx{fx_i}"
            bg_lbl = None
            if (lay.get("background") or {}).get("type") == "blur":
                chains.append(f"[{vb}]split=2[vmain][vbgsrc]")
                vb, bg_lbl = "vmain", "vbgsrc"
            comp_chains, v = compose.build_chains(
                lay, comp, scale=scale_c, out_dur=duration, base_label=vb,
                bg_src_label=bg_lbl, idx=idx_map, subs_file=subs_file,
                text_ass_file=text_ass_file, fonts_dir=fonts_dir,
                fps=float(src.get("fps") or 30.0))
            chains += comp_chains
            fade_chain, v = _global_fade_chain(
                v, {"fade_in_s": edl["fade_in_s"], "fade_out_s": edl["fade_out_s"]}, duration)
            if fade_chain:
                chains.append(fade_chain)
            a_chains, a_label = _audio_chains(
                censor_intervals=intervals, censor_mode=censor_mode,
                beep_input_index=beep_idx, audio_chunks=audio_sel,
                audio_fx=edl["audio"], duration=duration)
            graph = ";".join(chains + a_chains)
            v_label = f"[{v}]"

        if kind == "preview":
            out_path = config.data_dir() / "media" / "previews" / f"{cut['id']}.mp4"
        else:
            out_dir = config.renders_dir(settings_store.get_setting("output_dir") or "")
            out_path = out_dir / f"{slugify(cut['title'])}-{cut['id'][:8]}.mp4"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        args += ["-filter_complex", graph, "-map", v_label, "-map", a_label,
                 "-c:v", "libx264", "-preset", preset, "-crf", crf, "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out_path)]

        def on_progress(frac: float) -> None:
            _update_render(render_id, progress=round(frac, 3))
            ctx.publish("render.progress", {"render_id": render_id,
                                            "progress": round(frac, 3), "status": "running"})
            ctx.report(progress=frac)

        ffmpeg.run(args, duration=duration, progress_cb=on_progress,
                   cancel_check=ctx.check_cancel, cwd=workdir)

        _update_render(render_id, status="done", progress=1.0, output_path=str(out_path),
                       finished_at=utcnow())
        ctx.publish("render.progress", {"render_id": render_id, "progress": 1.0,
                                        "status": "done", "output_path": str(out_path)})
        ctx.report(stage="render", progress=1.0, message="Render concluído", force=True)
        return {"render_id": render_id, "output_path": str(out_path)}
    except BaseException as exc:
        status = "canceled" if type(exc).__name__ == "JobCancelled" else "failed"
        _update_render(render_id, status=status, error=str(exc), finished_at=utcnow())
        ctx.publish("render.progress", {"render_id": render_id, "status": status})
        raise
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
