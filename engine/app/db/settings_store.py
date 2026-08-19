"""Acesso à tabela settings + bootstrap do token da API local."""

from __future__ import annotations

import os
import secrets

from sqlalchemy import select

from .. import config
from .base import session
from .models import Setting


def get_setting(key: str, default=None):
    with session() as s:
        row = s.get(Setting, key)
        return row.value_json if row is not None else default


def set_setting(key: str, value) -> None:
    with session() as s:
        row = s.get(Setting, key)
        if row is None:
            s.add(Setting(key=key, value_json=value))
        else:
            row.value_json = value


def all_settings() -> dict:
    with session() as s:
        rows = s.execute(select(Setting)).scalars().all()
        return {r.key: r.value_json for r in rows}


def bootstrap_settings() -> str:
    """Garante defaults e o token da API; grava o token em <data_dir>/api_token (0600).

    Retorna o token ativo.
    """
    current = all_settings()
    for key, value in config.DEFAULT_SETTINGS.items():
        if key not in current:
            set_setting(key, value)

    token = current.get("api_token")
    if not token:
        token = secrets.token_urlsafe(32)
        set_setting("api_token", token)

    token_file = config.api_token_path()
    token_file.write_text(token, encoding="utf-8")
    if os.name == "posix":
        os.chmod(token_file, 0o600)
    return token
