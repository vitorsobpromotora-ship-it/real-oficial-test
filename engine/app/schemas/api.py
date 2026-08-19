"""Modelos pydantic de request/response da API local."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None


class ProjectOut(BaseModel):
    id: str
    name: str
    description: str
    created_at: str
    updated_at: str
    sources_count: int = 0
    cuts_count: int = 0


class SourceCreate(BaseModel):
    origin: Literal["url", "file"]
    url: str | None = None
    file_path: str | None = None
    auto_process: bool = True
    options: dict[str, Any] = Field(default_factory=dict)


class SourceOut(BaseModel):
    id: str
    project_id: str
    origin: str
    source_url: str | None
    file_path: str | None
    audio_path: str | None
    title: str
    duration_s: float | None
    width: int | None
    height: int | None
    fps: float | None
    size_bytes: int | None
    status: str
    error: str | None
    created_at: str


class JobOut(BaseModel):
    id: str
    type: str
    status: str
    stage: str
    progress: float
    message: str
    error: str | None
    project_id: str | None
    source_video_id: str | None
    cut_id: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None
    result: dict | None = None


class SettingsOut(BaseModel):
    claude_model: str
    claude_fallback_model: str
    whisper_model: str
    output_dir: str
    use_batches: bool
    max_cuts_per_30min: int
    min_cut_seconds: float
    max_cut_seconds: float
    censor_enabled: bool
    censor_mode: str
    censor_extra_words: list[str]
    ui_language: str
    has_anthropic_api_key: bool
    anthropic_api_key_masked: str
    api_token: str
    data_dir: str
    version: str


class SettingsUpdate(BaseModel):
    anthropic_api_key: str | None = None
    claude_model: str | None = None
    claude_fallback_model: str | None = None
    whisper_model: str | None = None
    output_dir: str | None = None
    use_batches: bool | None = None
    max_cuts_per_30min: int | None = Field(default=None, ge=1, le=100)
    min_cut_seconds: float | None = Field(default=None, ge=5, le=60)
    max_cut_seconds: float | None = Field(default=None, ge=20, le=180)
    censor_enabled: bool | None = None
    censor_mode: Literal["beep", "mute"] | None = None
    censor_extra_words: list[str] | None = None


class CutOut(BaseModel):
    id: str
    source_video_id: str
    project_id: str
    start_s: float
    end_s: float
    duration_s: float
    score: float
    score_breakdown: dict | None
    rhpt_score: float
    semantic_score: float
    hook_text: str
    title: str
    hashtags: list | None
    reason: str
    status: str
    rank: int | None
    origin: str
    crop_plan: dict | None
    censor_plan: list | None
    caption_style: dict | None
    brand_kit_id: str | None
    edits: dict | None
    human_rank: int | None
    review_started_at: str | None
    reviewed_at: str | None
    created_at: str
    updated_at: str


class CutPatch(BaseModel):
    status: Literal["draft", "approved", "rejected"] | None = None
    start_s: float | None = Field(default=None, ge=0)
    end_s: float | None = Field(default=None, ge=0)
    title: str | None = None
    caption_style: dict | None = None
    brand_kit_id: str | None = None
    edits: dict | None = None
    human_rank: int | None = Field(default=None, ge=1)
    review_started: bool | None = None  # marca o início da revisão (métrica de relatório)


class BulkCutsIn(BaseModel):
    cut_ids: list[str] = Field(min_length=1)
    patch: CutPatch


class TestAnthropicIn(BaseModel):
    api_key: str | None = None  # se ausente, usa a chave salva


class OkOut(BaseModel):
    ok: bool = True
    detail: str = ""
