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
from . import captions, censor
from .reframe import apply_framing_override, plan_crop

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


def _shift_plan(crop_plan: dict, start: float, end: float) -> dict:
    """Converte o plano (tempos da fonte) para tempos relativos ao clipe, cobrindo [0, dur]."""
    dur = end - start
    segs = []
    for seg in crop_plan.get("segments", []):
        s = max(0.0, seg["start"] - start)
        e = min(dur, seg["end"] - start)
        if e - s > 0.05:
            segs.append({"start": round(s, 3), "end": round(e, 3),
                         "x0": seg["x0"], "x1": seg["x1"]})
    if not segs:
        segs = [{"start": 0.0, "end": round(dur, 3),
                 "x0": crop_plan.get("segments", [{}])[0].get("x0", 0) if crop_plan.get("segments") else 0,
                 "x1": 0}]
        segs[0]["x1"] = segs[0]["x0"]
    segs[0]["start"] = 0.0
    segs[-1]["end"] = round(dur, 3)
    for prev, nxt in zip(segs, segs[1:], strict=False):
        nxt["start"] = prev["end"]
    return {**crop_plan, "segments": segs}


def build_filtergraph(*, crop_plan: dict, duration: float, out_w: int, out_h: int,
                      subs_file: str | None, fonts_dir: str | None,
                      censor_intervals: list[dict], censor_mode: str,
                      logo: dict | None, beep_input_index: int | None,
                      logo_input_index: int | None) -> tuple[str, str, str]:
    """Retorna (filter_complex, video_label, audio_label)."""
    chains: list[str] = []

    # --- vídeo: crop por segmentos OU blur_pad ---
    if crop_plan.get("mode") == "blur_pad":
        chains.append("[0:v]split=2[bgsrc][fgsrc]")
        chains.append(f"[bgsrc]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
                      f"crop={out_w}:{out_h},gblur=sigma=28[bg]")
        chains.append(f"[fgsrc]scale={out_w}:-2[fg]")
        chains.append("[bg][fg]overlay=(W-w)/2:(H-h)/2[vbase]")
    else:
        segs = crop_plan["segments"]
        crop_w, crop_h = crop_plan["crop_w"], crop_plan["crop_h"]
        if len(segs) == 1 and segs[0]["x0"] == segs[0]["x1"]:
            chains.append(f"[0:v]crop={crop_w}:{crop_h}:{segs[0]['x0']}:0,"
                          f"scale={out_w}:{out_h}:flags=lanczos[vbase]")
        else:
            chains.append(f"[0:v]split={len(segs)}" + "".join(f"[s{i}]" for i in range(len(segs))))
            for i, seg in enumerate(segs):
                d = max(0.05, seg["end"] - seg["start"])
                if seg["x0"] == seg["x1"]:
                    x_expr = str(seg["x0"])
                else:
                    x_expr = f"{seg['x0']}+({seg['x1']}-{seg['x0']})*(t/{d:.3f})"
                chains.append(f"[s{i}]trim={seg['start']:.3f}:{seg['end']:.3f},"
                              f"setpts=PTS-STARTPTS,crop={crop_w}:{crop_h}:{x_expr}:0[c{i}]")
            concat_in = "".join(f"[c{i}]" for i in range(len(segs)))
            chains.append(f"{concat_in}concat=n={len(segs)}:v=1:a=0,"
                          f"scale={out_w}:{out_h}:flags=lanczos[vbase]")

    v = "vbase"
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

    # --- áudio: censura + loudnorm ---
    a = "0:a"
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
    return ";".join(chains), f"[{v}]", "[aout]"


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
                kit = {"logo_path": k.logo_path, "logo_position": k.logo_position,
                       "logo_opacity": k.logo_opacity, "primary_color": k.primary_color,
                       "secondary_color": k.secondary_color, "font_family": k.font_family,
                       "caption_preset": k.caption_preset, "caption_style": k.caption_style,
                       "headline_template": k.headline_template}
        t = s.execute(select(Transcript).where(Transcript.source_video_id == src.id)
                      .order_by(Transcript.created_at.desc())).scalars().first()
        words: list[dict] = []
        if t is not None:
            rows = s.execute(select(TranscriptWord)
                             .where(TranscriptWord.transcript_id == t.id,
                                    TranscriptWord.end_s > cut.start_s,
                                    TranscriptWord.start_s < cut.end_s)
                             .order_by(TranscriptWord.idx)).scalars().all()
            words = [{"idx": w.idx, "start_s": w.start_s, "end_s": w.end_s, "word": w.word}
                     for w in rows]
        return {
            "render": {"id": r.id, "kind": r.kind, "overrides": r.preset_snapshot or {}},
            "cut": {"id": cut.id, "start_s": cut.start_s, "end_s": cut.end_s,
                    "title": cut.title, "caption_style": cut.caption_style,
                    "censor_plan": cut.censor_plan, "crop_plan": cut.crop_plan,
                    "edits": cut.edits},
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
    start, end = cut["start_s"], cut["end_s"]
    duration = end - start

    _update_render(render_id, status="running", started_at=utcnow())
    ctx.publish("render.progress", {"render_id": render_id, "progress": 0.0, "status": "running"})
    ctx.report(stage="render", progress=0.0, message=f"Renderizando {kind}…", force=True)

    out_w, out_h = (540, 960) if kind == "preview" else (1080, 1920)
    crf = "28" if kind == "preview" else str(overrides.get("crf", 19))
    preset = overrides.get("video_preset", "ultrafast" if kind == "preview" else "veryfast")

    crop_plan = cut["crop_plan"]
    if not crop_plan:
        ctx.report(stage="render", message="Calculando enquadramento…", force=True)
        crop_plan = plan_crop(src["file_path"], start, end, src["width"], src["height"],
                              cancel_check=ctx.check_cancel)
        with session() as s:
            row = s.get(CutCandidate, cut["id"])
            if row is not None:
                row.crop_plan = crop_plan
    framing = (cut["edits"] or {}).get("framing")
    crop_plan = apply_framing_override(crop_plan, framing, src["width"], src["height"],
                                       start, end)
    plan_rel = _shift_plan(crop_plan, start, end)

    words_rel = captions.words_for_cut(bundle["words"], start, end, cut["edits"])
    caption_style = overrides.get("caption_style") or cut["caption_style"]
    headline = overrides.get("headline")
    if headline is None and kit and kit.get("headline_template"):
        headline = kit["headline_template"].replace("{titulo}", cut["title"] or "")

    censor_enabled = overrides.get("censor_enabled")
    if censor_enabled is None:
        censor_enabled = bool(settings_store.get_setting("censor_enabled"))
    censor_mode = overrides.get("censor_mode") or settings_store.get_setting("censor_mode") or "beep"
    intervals: list[dict] = []
    if censor_enabled:
        if cut["censor_plan"]:
            intervals = [{"start": max(0.0, i["start"] - start), "end": min(duration, i["end"] - start)}
                         for i in cut["censor_plan"] if i["end"] > start and i["start"] < end]
        else:
            extra = settings_store.get_setting("censor_extra_words") or []
            intervals = censor.find_intervals(words_rel, censor.load_wordlist(extra))

    logo = None
    if kit and kit.get("logo_path") and Path(kit["logo_path"]).exists():
        logo = {"path": kit["logo_path"], "position": kit.get("logo_position", "tr"),
                "opacity": kit.get("logo_opacity", 1.0)}

    workdir = Path(tempfile.mkdtemp(prefix="render_", dir=config.data_dir() / "tmp"))
    try:
        subs_file = None
        if words_rel or headline:
            ass_text = captions.build_ass(words_rel, caption_style, kit, headline=headline,
                                          clip_duration=duration,
                                          fps=float(src.get("fps") or 30.0))
            (workdir / "subs.ass").write_text(ass_text, encoding="utf-8")
            subs_file = "subs.ass"
        fonts_dir = None
        if subs_file and bundled_fonts_dir():
            shutil.copytree(bundled_fonts_dir(), workdir / "fonts", dirs_exist_ok=True)
            fonts_dir = "fonts"

        args: list[str] = ["-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", src["file_path"]]
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

        graph, v_label, a_label = build_filtergraph(
            crop_plan=plan_rel, duration=duration, out_w=out_w, out_h=out_h,
            subs_file=subs_file, fonts_dir=fonts_dir, censor_intervals=intervals,
            censor_mode=censor_mode, logo=logo, beep_input_index=beep_idx,
            logo_input_index=logo_idx)

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
