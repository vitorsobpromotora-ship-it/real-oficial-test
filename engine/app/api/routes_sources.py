"""Fontes de vídeo: importação (URL/arquivo), consulta, transcrição e reprocessamento."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select

from ..db.base import session
from ..db.models import Project, SourceVideo, Transcript, TranscriptSegment, TranscriptWord
from ..schemas.api import OkOut, SourceCreate, SourceOut
from .deps import require_token

router = APIRouter(dependencies=[Depends(require_token)])


def to_out(v: SourceVideo) -> SourceOut:
    return SourceOut(id=v.id, project_id=v.project_id, origin=v.origin, source_url=v.source_url,
                     file_path=v.file_path, audio_path=v.audio_path, title=v.title,
                     duration_s=v.duration_s, width=v.width,
                     height=v.height, fps=v.fps, size_bytes=v.size_bytes, status=v.status,
                     error=v.error, created_at=v.created_at)


@router.post("/projects/{project_id}/sources", status_code=201)
def create_source(project_id: str, body: SourceCreate, request: Request):
    if body.origin == "url" and not body.url:
        raise HTTPException(422, "origin=url exige o campo url")
    if body.origin == "file":
        if not body.file_path:
            raise HTTPException(422, "origin=file exige o campo file_path")
        if not Path(body.file_path).exists():
            raise HTTPException(422, f"Arquivo não encontrado: {body.file_path}")
    with session() as s:
        if s.get(Project, project_id) is None:
            raise HTTPException(404, "Projeto não encontrado")
        src = SourceVideo(project_id=project_id, origin=body.origin, source_url=body.url,
                          file_path=body.file_path,
                          title=Path(body.file_path).stem if body.file_path else "")
        s.add(src)
        s.flush()
        source_id = src.id
        out = to_out(src)

    job_id = None
    if body.auto_process:
        job_id = request.app.state.runner.submit(
            "process_source", {"source_video_id": source_id, "options": body.options},
            project_id=project_id, source_video_id=source_id)
    return {"source": out.model_dump(), "job_id": job_id}


@router.get("/projects/{project_id}/sources", response_model=list[SourceOut])
def list_sources(project_id: str):
    with session() as s:
        rows = s.execute(select(SourceVideo).where(SourceVideo.project_id == project_id)
                         .order_by(SourceVideo.created_at.desc())).scalars().all()
        return [to_out(v) for v in rows]


@router.get("/sources/{source_id}", response_model=SourceOut)
def get_source(source_id: str):
    with session() as s:
        v = s.get(SourceVideo, source_id)
        if v is None:
            raise HTTPException(404, "Fonte não encontrada")
        return to_out(v)


@router.delete("/sources/{source_id}", response_model=OkOut)
def delete_source(source_id: str):
    with session() as s:
        v = s.get(SourceVideo, source_id)
        if v is None:
            raise HTTPException(404, "Fonte não encontrada")
        s.delete(v)
    return OkOut(ok=True, detail="Fonte excluída")


@router.get("/sources/{source_id}/transcript")
def get_transcript(source_id: str, include_words: bool = Query(default=False)):
    with session() as s:
        t = s.execute(select(Transcript).where(Transcript.source_video_id == source_id)
                      .order_by(Transcript.created_at.desc())).scalars().first()
        if t is None:
            raise HTTPException(404, "Transcrição ainda não disponível")
        segments = s.execute(select(TranscriptSegment).where(TranscriptSegment.transcript_id == t.id)
                             .order_by(TranscriptSegment.idx)).scalars().all()
        words_count = s.execute(select(func.count()).where(TranscriptWord.transcript_id == t.id)).scalar()
        body = {
            "id": t.id, "source_video_id": source_id, "language": t.language,
            "model_size": t.model_size, "full_text": t.full_text, "words_count": words_count,
            "segments": [{"idx": x.idx, "start_s": x.start_s, "end_s": x.end_s, "text": x.text}
                         for x in segments],
        }
        if include_words:
            words = s.execute(select(TranscriptWord).where(TranscriptWord.transcript_id == t.id)
                              .order_by(TranscriptWord.idx)).scalars().all()
            body["words"] = [{"idx": w.idx, "start_s": w.start_s, "end_s": w.end_s,
                              "word": w.word, "confidence": w.confidence} for w in words]
        return body


@router.post("/sources/{source_id}/process")
def process_source(source_id: str, request: Request, body: dict | None = None):
    with session() as s:
        v = s.get(SourceVideo, source_id)
        if v is None:
            raise HTTPException(404, "Fonte não encontrada")
        project_id = v.project_id
    job_id = request.app.state.runner.submit(
        "process_source", {"source_video_id": source_id, "options": (body or {}).get("options", {})},
        project_id=project_id, source_video_id=source_id)
    return {"job_id": job_id}
