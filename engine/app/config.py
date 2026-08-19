"""Configuração global do motor: diretórios de dados, versão e defaults de settings."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "real-oficial"
VERSION = "1.2.1"
API_PREFIX = "/api/v1"

if getattr(sys, "frozen", False):  # binário PyInstaller: assets ficam em _MEIPASS
    ENGINE_ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
else:
    ENGINE_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ENGINE_ROOT / "assets"

# Chaves persistidas na tabela settings e seus valores iniciais.
DEFAULT_SETTINGS: dict = {
    "default_agent": "claude",  # claude | gpt | local — agente padrão dos processamentos
    "anthropic_api_key": "",
    "claude_model": "claude-opus-5",
    "claude_fallback_model": "claude-sonnet-5",
    "openai_api_key": "",
    "openai_model": "gpt-5.1",
    "openai_fallback_model": "",  # vazio → sem contingência no GPT
    "whisper_model": "small",
    "output_dir": "",  # vazio → <data_dir>/renders
    "use_batches": False,
    "max_cuts_per_30min": 15,
    "min_cut_seconds": 15.0,
    "max_cut_seconds": 90.0,
    "censor_enabled": False,
    "censor_mode": "beep",  # beep | mute
    "censor_extra_words": [],
    "ui_language": "pt-BR",
}


def data_dir() -> Path:
    """Diretório de dados do usuário (banco, mídia, renders, modelos, logs)."""
    env = os.environ.get("REAL_OFICIAL_DATA_DIR")
    base = Path(env) if env else Path.home() / ".real-oficial"
    return base


def ensure_dirs(base: Path | None = None) -> Path:
    base = base or data_dir()
    for sub in ("", "media", "media/sources", "media/audio", "renders", "models", "logs", "tmp"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    return base


def db_path() -> Path:
    return data_dir() / "real-oficial.sqlite3"


def api_token_path() -> Path:
    return data_dir() / "api_token"


def models_dir() -> Path:
    """Modelos de IA (whisper, YuNet). Sobrescrevível via REAL_OFICIAL_MODELS_DIR (cache de CI)."""
    env = os.environ.get("REAL_OFICIAL_MODELS_DIR")
    p = Path(env) if env else data_dir() / "models"
    p.mkdir(parents=True, exist_ok=True)
    return p


def renders_dir(output_dir_setting: str | None = None) -> Path:
    if output_dir_setting:
        p = Path(output_dir_setting)
        p.mkdir(parents=True, exist_ok=True)
        return p
    return data_dir() / "renders"
