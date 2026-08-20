"""Schema completo do Real Oficial (SQLite). PKs UUID hex; tempos em ISO-8601 UTC."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value_json: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON, nullable=True)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(32), default=utcnow)
    updated_at: Mapped[str] = mapped_column(String(32), default=utcnow, onupdate=utcnow)


class SourceVideo(Base):
    __tablename__ = "source_videos"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    origin: Mapped[str] = mapped_column(String(8))  # url | file
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="importing")  # importing|ready|failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), default=utcnow)


class Transcript(Base):
    __tablename__ = "transcripts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    source_video_id: Mapped[str] = mapped_column(
        ForeignKey("source_videos.id", ondelete="CASCADE"), index=True
    )
    language: Mapped[str] = mapped_column(String(8), default="pt")
    model_size: Mapped[str] = mapped_column(String(16), default="small")
    full_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(32), default=utcnow)


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transcript_id: Mapped[str] = mapped_column(
        ForeignKey("transcripts.id", ondelete="CASCADE"), index=True
    )
    idx: Mapped[int] = mapped_column(Integer)
    start_s: Mapped[float] = mapped_column(Float)
    end_s: Mapped[float] = mapped_column(Float)
    text: Mapped[str] = mapped_column(Text)


class TranscriptWord(Base):
    __tablename__ = "transcript_words"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transcript_id: Mapped[str] = mapped_column(ForeignKey("transcripts.id", ondelete="CASCADE"))
    idx: Mapped[int] = mapped_column(Integer)
    start_s: Mapped[float] = mapped_column(Float)
    end_s: Mapped[float] = mapped_column(Float)
    word: Mapped[str] = mapped_column(String(80))
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    __table_args__ = (Index("ix_words_transcript_start", "transcript_id", "start_s"),)


class CutCandidate(Base):
    __tablename__ = "cut_candidates"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    source_video_id: Mapped[str] = mapped_column(
        ForeignKey("source_videos.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    start_s: Mapped[float] = mapped_column(Float)
    end_s: Mapped[float] = mapped_column(Float)
    score: Mapped[float] = mapped_column(Float, default=0.0)  # 0–100
    score_breakdown: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # 18 parâmetros 0–10
    rhpt_score: Mapped[float] = mapped_column(Float, default=0.0)
    semantic_score: Mapped[float] = mapped_column(Float, default=0.0)
    hook_text: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(String(300), default="")
    hashtags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    verdict: Mapped[str] = mapped_column(String(12), default="revisar")  # postar|revisar|descartar
    analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # análise editorial detalhada
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft|approved|rejected
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    origin: Mapped[str] = mapped_column(String(16), default="claude")  # claude|heuristic
    crop_plan: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    censor_plan: Mapped[list | None] = mapped_column(JSON, nullable=True)
    caption_style: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    brand_kit_id: Mapped[str | None] = mapped_column(
        ForeignKey("brand_kits.id", ondelete="SET NULL"), nullable=True
    )
    edits: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # trims, textos de legenda
    edl: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # edição não destrutiva (Editor)
    human_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_started_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reviewed_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), default=utcnow)
    updated_at: Mapped[str] = mapped_column(String(32), default=utcnow, onupdate=utcnow)


class BrandKit(Base):
    __tablename__ = "brand_kits"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    logo_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_position: Mapped[str] = mapped_column(String(2), default="tr")  # tl|tr|bl|br
    logo_opacity: Mapped[float] = mapped_column(Float, default=1.0)
    primary_color: Mapped[str] = mapped_column(String(9), default="#FFFFFF")
    secondary_color: Mapped[str] = mapped_column(String(9), default="#FFD400")
    font_family: Mapped[str] = mapped_column(String(80), default="Inter")
    caption_preset: Mapped[str] = mapped_column(String(40), default="bold_karaoke")
    caption_style: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # overrides do preset
    headline_template: Mapped[str] = mapped_column(String(200), default="")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String(32), default=utcnow)
    updated_at: Mapped[str] = mapped_column(String(32), default=utcnow, onupdate=utcnow)


class RenderBatch(Base):
    __tablename__ = "render_batches"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), default="")
    total: Mapped[int] = mapped_column(Integer, default=0)
    done: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|running|done|failed
    created_at: Mapped[str] = mapped_column(String(32), default=utcnow)


class Render(Base):
    __tablename__ = "renders"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    cut_id: Mapped[str] = mapped_column(ForeignKey("cut_candidates.id", ondelete="CASCADE"), index=True)
    batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("render_batches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    brand_kit_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    preset_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(String(8), default="final")  # preview|final
    status: Mapped[str] = mapped_column(String(16), default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    job_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), default=utcnow)
    started_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String(32), nullable=True)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    type: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    stage: Mapped[str] = mapped_column(String(40), default="")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    project_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    source_video_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    cut_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    created_at: Mapped[str] = mapped_column(String(32), default=utcnow)
    started_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String(32), nullable=True)


class ClaudeCall(Base):
    __tablename__ = "claude_calls"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    source_video_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    model: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_creation_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[str] = mapped_column(String(32), default=utcnow)


class StageTiming(Base):
    __tablename__ = "stage_timings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_video_id: Mapped[str] = mapped_column(String(32), index=True)
    stage: Mapped[str] = mapped_column(String(40))
    seconds: Mapped[float] = mapped_column(Float)
    created_at: Mapped[str] = mapped_column(String(32), default=utcnow)
