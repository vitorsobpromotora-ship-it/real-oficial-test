"""Estágio de transcrição: faster-whisper (CTranslate2) com timestamps por palavra, PT-BR."""

from __future__ import annotations

import logging
from collections.abc import Callable

from sqlalchemy import select

from .. import config
from ..db import settings_store
from ..db.base import session
from ..db.models import SourceVideo, Transcript, TranscriptSegment, TranscriptWord

log = logging.getLogger(__name__)

_model_cache: dict[str, object] = {}
WORD_BATCH = 2000


def get_model(size: str):
    """Carrega (com cache) o modelo faster-whisper. Baixa para <data_dir>/models no 1º uso."""
    if size not in _model_cache:
        from faster_whisper import WhisperModel  # import tardio: pesado

        log.info("Carregando modelo whisper '%s'…", size)
        _model_cache[size] = WhisperModel(
            size, device="cpu", compute_type="int8",
            download_root=str(config.data_dir() / "models"),
        )
    return _model_cache[size]


def stage_transcribe(ctx, source_id: str, report: Callable[[float, str], None]) -> None:
    with session() as s:
        src = s.get(SourceVideo, source_id)
        if src is None or src.status != "ready":
            raise ValueError(f"Fonte {source_id} não está pronta para transcrição")
        audio_path, duration = src.audio_path, src.duration_s or 0.0
        existing = s.execute(
            select(Transcript.id).where(Transcript.source_video_id == source_id)
        ).scalar()
    if existing:
        report(1.0, "Transcrição já existente")
        return

    size = (ctx.payload.get("options") or {}).get("whisper_model") \
        or settings_store.get_setting("whisper_model") or "small"
    report(0.0, f"Transcrevendo (modelo {size})…")
    model = get_model(size)
    segments_iter, info = model.transcribe(
        audio_path, language="pt", word_timestamps=True, vad_filter=True, beam_size=5,
    )

    seg_rows: list[dict] = []
    word_rows: list[dict] = []
    full_parts: list[str] = []
    widx = 0
    for i, seg in enumerate(segments_iter):
        ctx.check_cancel()
        text = seg.text.strip()
        if not text:
            continue
        seg_rows.append({"idx": i, "start_s": float(seg.start), "end_s": float(seg.end), "text": text})
        full_parts.append(text)
        for w in seg.words or []:
            word_rows.append({
                "idx": widx, "start_s": float(w.start), "end_s": float(w.end),
                "word": w.word.strip(), "confidence": float(getattr(w, "probability", 1.0) or 1.0),
            })
            widx += 1
        if duration > 0:
            report(min(0.99, float(seg.end) / duration), f"Transcrevendo… {int(seg.end)}s/{int(duration)}s")

    with session() as s:
        t = Transcript(source_video_id=source_id, language=info.language or "pt",
                       model_size=size, full_text=" ".join(full_parts))
        s.add(t)
        s.flush()
        tid = t.id
        s.add_all([TranscriptSegment(transcript_id=tid, **row) for row in seg_rows])
        for start in range(0, len(word_rows), WORD_BATCH):
            s.add_all([TranscriptWord(transcript_id=tid, **row)
                       for row in word_rows[start:start + WORD_BATCH]])
            s.flush()
    report(1.0, f"Transcrição concluída ({len(word_rows)} palavras)")
