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


class TestAnthropicIn(BaseModel):
    api_key: str | None = None  # se ausente, usa a chave salva


class OkOut(BaseModel):
    ok: bool = True
    detail: str = ""
