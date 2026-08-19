"""Configurações: leitura (com chave mascarada), atualização e teste da chave Anthropic."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from .. import config
from ..db import settings_store as store
from ..schemas.api import OkOut, SettingsOut, SettingsUpdate, TestAnthropicIn
from .deps import require_token

router = APIRouter(dependencies=[Depends(require_token)])


def _mask(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 10:
        return "•" * len(key)
    return f"{key[:7]}…{key[-4:]}"


@router.get("/settings", response_model=SettingsOut)
def get_settings(request: Request):
    s = store.all_settings()
    api_key = s.get("anthropic_api_key") or ""
    return SettingsOut(
        claude_model=s.get("claude_model", "claude-opus-5"),
        claude_fallback_model=s.get("claude_fallback_model", "claude-sonnet-5"),
        whisper_model=s.get("whisper_model", "small"),
        output_dir=s.get("output_dir", "") or "",
        use_batches=bool(s.get("use_batches", False)),
        max_cuts_per_30min=int(s.get("max_cuts_per_30min", 15)),
        min_cut_seconds=float(s.get("min_cut_seconds", 15.0)),
        max_cut_seconds=float(s.get("max_cut_seconds", 90.0)),
        censor_enabled=bool(s.get("censor_enabled", False)),
        censor_mode=s.get("censor_mode", "beep"),
        censor_extra_words=list(s.get("censor_extra_words", []) or []),
        ui_language=s.get("ui_language", "pt-BR"),
        has_anthropic_api_key=bool(api_key),
        anthropic_api_key_masked=_mask(api_key),
        api_token=s.get("api_token", ""),
        data_dir=str(config.data_dir()),
        version=config.VERSION,
    )


@router.put("/settings", response_model=SettingsOut)
def update_settings(body: SettingsUpdate, request: Request):
    for key, value in body.model_dump(exclude_none=True).items():
        store.set_setting(key, value)
    return get_settings(request)


@router.post("/settings/test-anthropic", response_model=OkOut)
def test_anthropic(body: TestAnthropicIn):
    api_key = body.api_key or store.get_setting("anthropic_api_key") or ""
    if not api_key:
        return OkOut(ok=False, detail="Nenhuma chave de API configurada")
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key, max_retries=1, timeout=20.0)
        model = store.get_setting("claude_model") or "claude-opus-5"
        client.messages.create(
            model=model,
            max_tokens=32,
            messages=[{"role": "user", "content": "Responda apenas: ok"}],
        )
        return OkOut(ok=True, detail=f"Conexão OK com {model}")
    except Exception as exc:  # noqa: BLE001 — resposta amigável na UI
        return OkOut(ok=False, detail=f"Falha: {exc}")
