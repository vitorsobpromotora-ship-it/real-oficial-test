"""Cortes: listagem por projeto/fonte, revisão (aprovar/rejeitar/ajustar) e edição em massa."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select

from ..db.base import session
from ..db.models import CutCandidate, SourceVideo, utcnow
from ..pipeline import edl as edl_mod
from ..pipeline import motion as motion_mod
from ..schemas.api import BulkCutsIn, CutOut, CutPatch, OkOut
from .deps import require_token

router = APIRouter(dependencies=[Depends(require_token)])


# ciclo de RENDER derivado dos registros de Render (kind=final) — nunca uma flag
# no corte: o estado editorial e o estado técnico não podem se contaminar.
RENDER_STATE = {"queued": "queued", "running": "rendering", "done": "rendered",
                "failed": "render_failed", "canceled": "not_rendered"}


def render_info(s, cut_ids: list[str]) -> dict:
    """Render FINAL mais recente de cada corte, em uma única consulta."""
    from ..db.models import Render  # noqa: PLC0415

    if not cut_ids:
        return {}
    rows = s.execute(select(Render).where(Render.cut_id.in_(cut_ids), Render.kind == "final")
                     .order_by(Render.created_at)).scalars().all()
    return {r.cut_id: r for r in rows}  # ordem ascendente: o mais recente prevalece


def to_out(c: CutCandidate, render=None) -> CutOut:
    state = RENDER_STATE.get(render.status, "not_rendered") if render is not None else "not_rendered"
    outdated = bool(render is not None and state == "rendered"
                    and (render.edit_revision or 0) < (c.edit_revision or 1))
    return CutOut(
        id=c.id, source_video_id=c.source_video_id, project_id=c.project_id,
        start_s=c.start_s, end_s=c.end_s, duration_s=round(c.end_s - c.start_s, 3),
        score=c.score, score_breakdown=c.score_breakdown, rhpt_score=c.rhpt_score,
        semantic_score=c.semantic_score, hook_text=c.hook_text, title=c.title,
        hashtags=c.hashtags, reason=c.reason, verdict=c.verdict or "revisar",
        analysis=c.analysis, status=c.status, rank=c.rank, origin=c.origin,
        crop_plan=c.crop_plan, censor_plan=c.censor_plan, caption_style=c.caption_style,
        brand_kit_id=c.brand_kit_id, edits=c.edits, edl=c.edl, motion=c.motion,
        description=c.description or "", platform_metadata=c.platform_metadata,
        edit_revision=c.edit_revision or 1, render_state=state, render_outdated=outdated,
        latest_render_id=render.id if render is not None else None,
        human_rank=c.human_rank,
        review_started_at=c.review_started_at, reviewed_at=c.reviewed_at,
        created_at=c.created_at, updated_at=c.updated_at)


@router.get("/projects/{project_id}/cuts", response_model=list[CutOut])
def list_cuts(project_id: str, status: str | None = Query(default=None),
              source_video_id: str | None = Query(default=None),
              sort: str = Query(default="score")):
    with session() as s:
        q = select(CutCandidate).where(CutCandidate.project_id == project_id)
        if status:
            estados = [status, "pending_review"] if status == "draft" else [status]
            q = q.where(CutCandidate.status.in_(estados))
        else:  # reservas só aparecem quando pedidas ("Mostrar mais oportunidades")
            q = q.where(CutCandidate.status != "reserve")
        if source_video_id:
            q = q.where(CutCandidate.source_video_id == source_video_id)
        if sort == "time":
            q = q.order_by(CutCandidate.start_s)
        else:
            q = q.order_by(CutCandidate.score.desc())
        rows = s.execute(q).scalars().all()
        renders = render_info(s, [c.id for c in rows])
        return [to_out(c, renders.get(c.id)) for c in rows]


@router.get("/cuts/{cut_id}", response_model=CutOut)
def get_cut(cut_id: str):
    with session() as s:
        c = s.get(CutCandidate, cut_id)
        if c is None:
            raise HTTPException(404, "Corte não encontrado")
        return to_out(c, render_info(s, [cut_id]).get(cut_id))


def _invalidate_previews(s, cut_id: str) -> None:
    """Ajuste visual torna a prévia antiga obsoleta: remove registros e arquivo."""
    from .. import config  # noqa: PLC0415
    from ..db.models import Render  # noqa: PLC0415

    rows = s.execute(select(Render).where(Render.cut_id == cut_id,
                                          Render.kind == "preview")).scalars().all()
    for r in rows:
        s.delete(r)
    (config.data_dir() / "media" / "previews" / f"{cut_id}.mp4").unlink(missing_ok=True)
    strips = config.data_dir() / "media" / "filmstrips"
    if strips.exists():
        for f in strips.glob(f"{cut_id}-*.jpg"):
            f.unlink(missing_ok=True)


@router.get("/cuts/{cut_id}/words")
def cut_words(cut_id: str, pad_s: float = Query(default=15.0, ge=0.0, le=60.0)):
    """Palavras da transcrição na janela do corte ± pad_s (tempos da FONTE).

    O Editor usa isto para snapping e correção de palavras sem baixar a
    transcrição inteira de fontes longas."""
    from ..db.models import Transcript, TranscriptWord  # noqa: PLC0415

    with session() as s:
        c = s.get(CutCandidate, cut_id)
        if c is None:
            raise HTTPException(404, "Corte não encontrado")
        t = s.execute(select(Transcript).where(Transcript.source_video_id == c.source_video_id)
                      .order_by(Transcript.created_at.desc())).scalars().first()
        if t is None:
            return {"words": []}
        env_a, env_b = edl_mod.envelope(_edl_efetiva(c, c.edl))
        rows = s.execute(select(TranscriptWord)
                         .where(TranscriptWord.transcript_id == t.id,
                                TranscriptWord.end_s > env_a - pad_s,
                                TranscriptWord.start_s < env_b + pad_s)
                         .order_by(TranscriptWord.idx)).scalars().all()
        return {"words": [{"idx": w.idx, "start_s": w.start_s, "end_s": w.end_s,
                           "word": w.word} for w in rows]}


@router.get("/captions/presets")
def caption_presets():
    """Presets de legenda com rótulos PT-BR — fonte única de verdade para a UI."""
    from ..pipeline.captions import PRESET_LABELS_PTBR, PRESETS  # noqa: PLC0415

    return {"presets": [{"id": nome, "label": PRESET_LABELS_PTBR.get(nome, nome), **campos}
                        for nome, campos in PRESETS.items()]}


@router.get("/motion/presets")
def motion_presets():
    """Catálogo declarativo do Motion Engine — o preview TS avalia AS MESMAS
    trilhas de keyframes que o compilador ASS do render (paridade)."""
    from ..pipeline.motion_text import TEXT_PRESETS  # noqa: PLC0415

    return {"presets": list(TEXT_PRESETS.values()),
            "easings": motion_mod.EASING_LABELS_PTBR}


@router.get("/cuts/{cut_id}/caption-cards")
def caption_cards(cut_id: str):
    """Cartões de legenda RESOLVIDOS pelo MESMO código do render (WYSIWYG).

    Devolve o estilo efetivo (preset ← kit ← corte, incluindo a área de legenda
    do Estúdio) e os cartões em TEMPO DE SAÍDA da EDL — o canvas do Editor só
    precisa desenhar o que vier aqui; o agrupamento nunca é recalculado na UI."""
    from ..db.models import BrandKit, Transcript, TranscriptWord  # noqa: PLC0415
    from ..pipeline import captions, compose  # noqa: PLC0415

    with session() as s:
        c = s.get(CutCandidate, cut_id)
        if c is None:
            raise HTTPException(404, "Corte não encontrado")
        src = s.get(SourceVideo, c.source_video_id)
        kit = None
        if c.brand_kit_id:
            k = s.get(BrandKit, c.brand_kit_id)
            if k is not None:
                kit = {"primary_color": k.primary_color, "secondary_color": k.secondary_color,
                       "font_family": k.font_family, "caption_preset": k.caption_preset,
                       "caption_style": k.caption_style, "layout": k.layout}
        eff = _edl_efetiva(c, c.edl)
        env_a, env_b = edl_mod.envelope(eff)
        t = s.execute(select(Transcript).where(Transcript.source_video_id == c.source_video_id)
                      .order_by(Transcript.created_at.desc())).scalars().first()
        words: list[dict] = []
        if t is not None:
            rows = s.execute(select(TranscriptWord)
                             .where(TranscriptWord.transcript_id == t.id,
                                    TranscriptWord.end_s > env_a,
                                    TranscriptWord.start_s < env_b)
                             .order_by(TranscriptWord.idx)).scalars().all()
            words = [{"idx": w.idx, "start_s": w.start_s, "end_s": w.end_s, "word": w.word}
                     for w in rows]
        edits, caption_style = c.edits, c.caption_style
        fps = float(src.fps) if src and src.fps else 30.0

    words_out = edl_mod.map_words(words, eff, edits)
    style = captions.resolve_style(caption_style, kit)
    lay = compose.layout_of(kit)
    if lay is not None:
        style = {**style, **compose.caption_overrides(lay)}
    enf_idx = captions._emphasis_index(edits)
    cards = captions.build_cards(words_out, style)
    janelas = captions.card_windows(cards, fps=fps)
    out = []
    for card, (a, b) in zip(cards, janelas, strict=False):
        textos = [w["word"] for w in card]
        breaks = captions.split_lines(
            [t2.upper() for t2 in textos] if style.get("uppercase") else textos,
            int(style.get("max_chars") or 18), int(style.get("max_lines") or 2))
        out.append({"start": a, "end": b, "breaks": breaks,
                    "words": [{"idx": w.get("idx"), "ins_id": w.get("ins_id"),
                               "start_s": w["start_s"], "end_s": w["end_s"],
                               "word": w["word"],
                               "emphasis": captions._emphasis_for(w, enf_idx)}
                              for w in card]})
    return {"style": style, "fps": fps, "out_duration": edl_mod.out_duration(eff),
            "cards": out}


@router.post("/cuts/{cut_id}/pauses-preview")
def pauses_preview(cut_id: str, body: dict | None = None):
    """Calcula (SEM aplicar) a EDL com pausas removidas no nível pedido.

    body: {"nivel": "leve" | "normal" | "agressivo"}. O Editor mostra o
    resultado na timeline; nada muda até o usuário salvar. Respeita a edição
    existente: só corta pausas DENTRO dos trechos mantidos."""
    from ..db.models import Transcript, TranscriptWord  # noqa: PLC0415
    from ..pipeline import pauses  # noqa: PLC0415

    nivel = (body or {}).get("nivel", "normal")
    if nivel not in pauses.NIVEIS:
        raise HTTPException(422, "nivel deve ser leve, normal ou agressivo")
    with session() as s:
        c = s.get(CutCandidate, cut_id)
        if c is None:
            raise HTTPException(404, "Corte não encontrado")
        eff = _edl_efetiva(c, c.edl)
        t = s.execute(select(Transcript).where(Transcript.source_video_id == c.source_video_id)
                      .order_by(Transcript.created_at.desc())).scalars().first()
        if t is None:
            raise HTTPException(422, "Sem transcrição — processe a fonte primeiro")
        env_a, env_b = edl_mod.envelope(eff)
        rows = s.execute(select(TranscriptWord)
                         .where(TranscriptWord.transcript_id == t.id,
                                TranscriptWord.end_s > env_a,
                                TranscriptWord.start_s < env_b)
                         .order_by(TranscriptWord.idx)).scalars().all()
        words = [{"start_s": w.start_s, "end_s": w.end_s, "word": w.word} for w in rows]
    edl_novo, stats = pauses.edl_sem_pausas(words, edl_mod.segments_of(eff), nivel)
    # preserva fades/áudio da edição atual — só a linha de segmentos muda
    edl_novo.update({"fade_in_s": eff["fade_in_s"], "fade_out_s": eff["fade_out_s"],
                     "transition_s": eff["transition_s"], "audio": eff["audio"]})
    return {"edl": edl_novo, **stats}


@router.get("/cuts/{cut_id}/waveform")
def cut_waveform(cut_id: str, pps: int = Query(default=40, ge=10, le=100),
                 pad_s: float = Query(default=15.0, ge=0.0, le=60.0)):
    """Picos de áudio para a timeline do Editor (janela do corte ± pad_s).

    Lê do WAV da fonte apenas a janela necessária — fontes de horas continuam
    baratas. `peaks` = amplitude 0–1, um valor a cada 1/pps segundos."""
    from pathlib import Path  # noqa: PLC0415

    import numpy as np  # noqa: PLC0415
    import soundfile as sf  # noqa: PLC0415

    with session() as s:
        c = s.get(CutCandidate, cut_id)
        if c is None:
            raise HTTPException(404, "Corte não encontrado")
        src = s.get(SourceVideo, c.source_video_id)
        if src is None or not src.audio_path or not Path(src.audio_path).exists():
            raise HTTPException(404, "Áudio da fonte não disponível — reprocesse a fonte")
        eff = _edl_efetiva(c, c.edl)
        audio_path, src_dur = src.audio_path, float(src.duration_s or 0.0)
    env_a, env_b = edl_mod.envelope(eff)
    a = max(0.0, env_a - pad_s)
    b = env_b + pad_s
    if src_dur > 0:
        b = min(b, src_dur)
    with sf.SoundFile(audio_path) as f:
        sr = f.samplerate
        f.seek(min(int(a * sr), len(f)))
        data = f.read(max(0, int((b - a) * sr)), dtype="float32", always_2d=True)[:, 0]
    bucket = max(1, sr // pps)
    usable = (len(data) // bucket) * bucket
    peaks: list[float] = []
    if usable:
        peaks = [round(float(p), 3)
                 for p in np.abs(data[:usable]).reshape(-1, bucket).max(axis=1)]
    spp = bucket / sr  # segundos por pico (pps efetivo = 1/spp)
    return {"start_s": round(a, 3), "end_s": round(a + len(peaks) * spp, 3),
            "pps": round(1.0 / spp, 3), "peaks": peaks, "source_duration_s": src_dur}


VISUAL_FIELDS = {"start_s", "end_s", "framing", "punch_in", "title", "caption_style",
                 "brand_kit_id", "edits", "edl", "motion"}


def _edl_efetiva(c: CutCandidate, edl_in: dict | None) -> dict:
    return edl_mod.cut_edl({"edl": edl_in, "start_s": c.start_s, "end_s": c.end_s})


def _apply_patch(s, c: CutCandidate, patch: CutPatch) -> None:
    # exclude_unset (e não exclude_none): null explícito significa LIMPAR o campo
    # (ex.: brand_kit_id=null remove o kit; caption_style=null volta ao padrão).
    data = patch.model_dump(exclude_unset=True)

    # chaves de edits geridas por campos dedicados do PATCH (framing/punch_in):
    # o Editor as envia FORA de edits, então compará-las aqui daria "mudou"
    # em todo salvamento e inflaria edit_revision sem nenhuma edição real.
    _GERIDAS = ("framing", "punch_in")

    def _sem_geridas(d: dict | None) -> dict:
        return {k: v for k, v in (d or {}).items() if k not in _GERIDAS}

    def _mudou(field: str, value) -> bool:
        if field == "edits":
            return _sem_geridas(c.edits) != _sem_geridas(value)
        if field == "framing":
            return ((c.edits or {}).get("framing") or "auto") != (value or "auto")
        if field == "punch_in":
            return ((c.edits or {}).get("punch_in") or "off") != (value or "off")
        if field in ("start_s", "end_s"):
            return value is not None and getattr(c, field) != value
        if field == "edl":  # compara as EDLs EFETIVAS (normalizadas), não o JSON cru
            if value is None:
                return c.edl is not None
            return _edl_efetiva(c, c.edl) != _edl_efetiva(c, value)
        if field == "motion":  # compara manifests NORMALIZADOS (reenvio igual ≠ edição)
            try:
                return c.motion != motion_mod.validate_manifest(value)
            except ValueError:
                return True  # inválido nunca chega a gravar; o 422 vem adiante
        return getattr(c, field) != value

    # só invalida prévias quando o valor visual de fato muda (aprovar reenviando
    # o mesmo estilo/kit não descarta a prévia já renderizada)
    visual_change = any(_mudou(f, v) for f, v in data.items() if f in VISUAL_FIELDS)
    if "review_started" in data:
        if data.pop("review_started") and not c.review_started_at:
            c.review_started_at = utcnow()
    if data.get("status"):
        novo = data.pop("status")
        c.status = "pending_review" if novo == "draft" else novo  # "draft" = sinônimo legado
        if c.status in ("approved", "rejected"):
            c.reviewed_at = utcnow()
        elif c.status == "pending_review":
            c.reviewed_at = None  # Restaurar para revisão: volta a exigir decisão
    else:
        data.pop("status", None)
    if data.get("start_s") is not None or data.get("end_s") is not None:
        new_start = data.pop("start_s", None)
        new_end = data.pop("end_s", None)
        new_start = c.start_s if new_start is None else new_start
        new_end = c.end_s if new_end is None else new_end
        if new_end <= new_start:
            raise HTTPException(422, "end_s deve ser maior que start_s")
        if (new_start, new_end) != (c.start_s, c.end_s):
            c.start_s, c.end_s = new_start, new_end
            c.crop_plan = None  # trim invalida o plano de enquadramento; será recalculado
            # trim rápido fora do Editor apara a EDL existente em vez de descartá-la
            c.edl = edl_mod.edl_clamped(c.edl, new_start, new_end)
    else:
        data.pop("start_s", None)
        data.pop("end_s", None)
    if "edl" in data:
        new_edl = data.pop("edl")
        if new_edl is None:
            c.edl = None  # descarta a edição; volta ao corte simples start→end
        else:
            src = s.get(SourceVideo, c.source_video_id)
            erros = edl_mod.validate_edl(new_edl, src.duration_s if src else None)
            if erros:
                raise HTTPException(422, "EDL inválida: " + "; ".join(erros))
            eff = _edl_efetiva(c, new_edl)
            env_a, env_b = edl_mod.envelope(eff)
            if (round(env_a, 3), round(env_b, 3)) != (round(c.start_s, 3), round(c.end_s, 3)):
                c.crop_plan = None  # envelope mudou → enquadramento recalculado no render
                c.start_s, c.end_s = env_a, env_b
            # edição equivalente ao corte simples não precisa de EDL persistida
            c.edl = None if eff == _edl_efetiva(c, None) else eff
    if "motion" in data:
        try:
            c.motion = motion_mod.validate_manifest(data.pop("motion"))
        except ValueError as exc:
            raise HTTPException(422, f"Motion Manifest inválido: {exc}") from None
    for field in ("title", "description", "platform_metadata", "caption_style",
                  "brand_kit_id", "edits", "human_rank"):
        if field in data:
            limpa = data[field] is None and field in ("title", "description")
            setattr(c, field, "" if limpa else data[field])
    if "framing" in data:
        f = data.pop("framing")
        edits = dict(c.edits or {})
        if f and f != "auto":
            edits["framing"] = f
        else:
            edits.pop("framing", None)  # auto/null → volta ao enquadramento automático
        c.edits = edits or None
    if "punch_in" in data:
        p = data.pop("punch_in")
        edits = dict(c.edits or {})
        if p and p != "off":
            edits["punch_in"] = p
        else:
            edits.pop("punch_in", None)
        c.edits = edits or None
    if visual_change:
        _invalidate_previews(s, c.id)
        # revisão de edição: é ela que detecta "render desatualizado"
        # (edit_revision > revisão carimbada no render concluído)
        c.edit_revision = (c.edit_revision or 1) + 1
    c.updated_at = utcnow()


@router.patch("/cuts/{cut_id}", response_model=CutOut)
def patch_cut(cut_id: str, patch: CutPatch):
    with session() as s:
        c = s.get(CutCandidate, cut_id)
        if c is None:
            raise HTTPException(404, "Corte não encontrado")
        _apply_patch(s, c, patch)
        s.flush()
        return to_out(c, render_info(s, [cut_id]).get(cut_id))


@router.post("/cuts/bulk", response_model=OkOut)
def bulk_patch(body: BulkCutsIn):
    with session() as s:
        rows = s.execute(select(CutCandidate).where(CutCandidate.id.in_(body.cut_ids))).scalars().all()
        if len(rows) != len(set(body.cut_ids)):
            raise HTTPException(404, "Um ou mais cortes não foram encontrados")
        for c in rows:
            _apply_patch(s, c, body.patch)
    return OkOut(ok=True, detail=f"{len(rows)} cortes atualizados")


@router.post("/cuts/{cut_id}/preview")
def preview_cut(cut_id: str, request: Request):
    """Enfileira um render de pré-visualização (540×960 rápido) do corte.

    Se já houver uma prévia na fila/em andamento, retorna essa em vez de duplicar."""
    from ..db.models import Render  # noqa: PLC0415

    with session() as s:
        c = s.get(CutCandidate, cut_id)
        if c is None:
            raise HTTPException(404, "Corte não encontrado")
        ativo = s.execute(select(Render).where(
            Render.cut_id == cut_id, Render.kind == "preview",
            Render.status.in_(("queued", "running")))).scalars().first()
        if ativo is not None:
            return {"render_id": ativo.id, "job_id": ativo.job_id}
        r = Render(cut_id=cut_id, kind="preview")
        s.add(r)
        s.flush()
        render_id, project_id, source_id = r.id, c.project_id, c.source_video_id
    job_id = request.app.state.runner.submit("render_cut", {"render_id": render_id},
                                             project_id=project_id, source_video_id=source_id,
                                             cut_id=cut_id)
    with session() as s:
        r = s.get(Render, render_id)
        r.job_id = job_id
    return {"render_id": render_id, "job_id": job_id}


@router.delete("/cuts/{cut_id}", response_model=OkOut)
def delete_cut(cut_id: str):
    with session() as s:
        c = s.get(CutCandidate, cut_id)
        if c is None:
            raise HTTPException(404, "Corte não encontrado")
        s.delete(c)
    return OkOut(ok=True, detail="Corte excluído")
