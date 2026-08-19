"""Estágio de análise: RHPT + análise semântica (Claude/heurística) → candidatos persistidos."""

from __future__ import annotations

import logging

from sqlalchemy import select

from ..db import settings_store
from ..db.base import session
from ..db.models import SourceVideo, Transcript, TranscriptSegment, TranscriptWord
from . import candidates as cand
from .audio_features import compute_features
from .semantic import analyze_semantic

log = logging.getLogger(__name__)


def _load_transcript(source_video_id: str) -> tuple[list[dict], list[dict]]:
    with session() as s:
        t = s.execute(select(Transcript).where(Transcript.source_video_id == source_video_id)
                      .order_by(Transcript.created_at.desc())).scalars().first()
        if t is None:
            raise ValueError("Transcrição inexistente — rode o estágio de transcrição antes")
        sentences = [{"start_s": x.start_s, "end_s": x.end_s, "text": x.text}
                     for x in s.execute(select(TranscriptSegment)
                                        .where(TranscriptSegment.transcript_id == t.id)
                                        .order_by(TranscriptSegment.idx)).scalars().all()]
        words = [{"start_s": w.start_s, "end_s": w.end_s, "word": w.word}
                 for w in s.execute(select(TranscriptWord)
                                    .where(TranscriptWord.transcript_id == t.id)
                                    .order_by(TranscriptWord.idx)).scalars().all()]
    return sentences, words


def stage_analyze(ctx, source_id: str, report) -> None:
    force = bool(ctx.payload.get("options", {}).get("force_analyze"))
    if not force and cand.existing_count(source_id) > 0:
        report(1.0, "Análise já existente")
        return

    with session() as s:
        src = s.get(SourceVideo, source_id)
        if src is None or src.status != "ready":
            raise ValueError("Fonte não está pronta para análise")
        audio_path, duration, project_id = src.audio_path, src.duration_s or 0.0, src.project_id

    sentences, words = _load_transcript(source_id)
    if not sentences:
        report(1.0, "Transcrição vazia — nenhum corte gerado")
        cand.persist_candidates(source_id, project_id, [])
        return

    report(0.02, "Analisando áudio (RHPT)…")
    features = compute_features(audio_path, words,
                                progress_cb=lambda f: report(0.02 + f * 0.23, "Analisando áudio (RHPT)…"),
                                cancel_check=ctx.check_cancel)

    opts = ctx.payload.get("options", {}) or {}
    min_s = float(opts.get("min_cut_seconds") or settings_store.get_setting("min_cut_seconds") or 15.0)
    max_s = float(opts.get("max_cut_seconds") or settings_store.get_setting("max_cut_seconds") or 90.0)
    per30 = int(opts.get("max_cuts_per_30min")
                or settings_store.get_setting("max_cuts_per_30min") or 15)
    target = max(3, min(60, round(duration / 60.0 / 30.0 * per30))) if duration else 10

    raw, meta = analyze_semantic(ctx, source_id, sentences, features, duration,
                                 lambda f, m="": report(0.25 + f * 0.6, m or "Análise semântica…"),
                                 min_s=min_s, max_s=max_s, target_count=target,
                                 agent=opts.get("agent"))

    report(0.87, "Consolidando candidatos…")
    final, stats = cand.finalize_candidates(raw, sentences, features, min_s=min_s, max_s=max_s,
                                            duration=duration, target_count=target)
    n = cand.persist_candidates(source_id, project_id, final)
    report(1.0, f"{n} cortes sugeridos (alvo {stats['alvo']}; {stats['brutos']} candidatos "
                f"brutos, {stats['apos_dedup']} após remover sobreposições){_ai_note(meta)}")


def _ai_note(meta: dict) -> str:
    """Sufixo honesto sobre o uso de IA na mensagem final do job."""
    agent, chunks, ok = meta.get("agent"), meta.get("chunks", 0), meta.get("ia_ok", 0)
    if agent == "local":
        return " · análise local (sem IA, escolhida)"
    if not chunks:
        return ""
    rotulo = {"claude": "Claude", "gpt": "GPT"}.get(agent, agent)
    modelo = f" {meta['model']}" if meta.get("model") else ""
    if ok >= chunks:
        return f" · IA {rotulo}{modelo} em {ok}/{chunks} trechos"
    causa = f" — último erro: {meta['erro']}" if meta.get("erro") else ""
    return (f" · ATENÇÃO: IA {rotulo}{modelo} funcionou em só {ok}/{chunks} trechos; "
            f"o restante usou análise local{causa}")
