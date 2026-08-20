"""Configurações: leitura (chaves mascaradas), atualização e teste REAL dos provedores de IA.

O teste percorre exatamente o caminho usado pela análise (streaming/saída
estruturada), não uma chamada simplificada — se ele passa, a análise funciona.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from .. import config
from ..db import settings_store as store
from ..schemas.api import OkOut, SettingsOut, SettingsUpdate, TestAIIn, TestAnthropicIn
from .deps import require_token

router = APIRouter(dependencies=[Depends(require_token)])

TEST_SYSTEM = ("Você é um verificador de conexão. Responda no formato estruturado pedido "
               "com a lista de segmentos VAZIA.")
TEST_USER = "Teste de conexão do Real Oficial. Retorne segments = [] (nenhum segmento)."


def _mask(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 10:
        return "•" * len(key)
    return f"{key[:7]}…{key[-4:]}"


@router.get("/settings", response_model=SettingsOut)
def get_settings(request: Request):
    s = store.all_settings()
    anthropic_key = s.get("anthropic_api_key") or ""
    openai_key = s.get("openai_api_key") or ""
    return SettingsOut(
        default_agent=s.get("default_agent", "claude") or "claude",
        cut_profile=s.get("cut_profile", "balanceado") or "balanceado",
        claude_model=s.get("claude_model", "claude-opus-5"),
        claude_fallback_model=s.get("claude_fallback_model", "claude-sonnet-5"),
        openai_model=s.get("openai_model", "gpt-5.1") or "gpt-5.1",
        openai_fallback_model=s.get("openai_fallback_model", "") or "",
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
        has_anthropic_api_key=bool(anthropic_key),
        anthropic_api_key_masked=_mask(anthropic_key),
        has_openai_api_key=bool(openai_key),
        openai_api_key_masked=_mask(openai_key),
        api_token=s.get("api_token", ""),
        data_dir=str(config.data_dir()),
        version=config.VERSION,
    )


@router.put("/settings", response_model=SettingsOut)
def update_settings(body: SettingsUpdate, request: Request):
    for key, value in body.model_dump(exclude_none=True).items():
        store.set_setting(key, value)
    return get_settings(request)


def _run_ai_test(provider: str, api_key: str | None) -> OkOut:
    from ..services.ai_usage import friendly_ai_error

    if provider == "gpt":
        key = api_key or store.get_setting("openai_api_key") or ""
        model = store.get_setting("openai_model") or "gpt-5.1"
        if not key:
            return OkOut(ok=False, detail="Nenhuma chave OpenAI configurada")
        from ..services.openai_client import OpenAIClient

        client = OpenAIClient(key, model, timeout=90.0)
    else:
        key = api_key or store.get_setting("anthropic_api_key") or ""
        model = store.get_setting("claude_model") or "claude-opus-5"
        if not key:
            return OkOut(ok=False, detail="Nenhuma chave Anthropic configurada")
        from ..services.claude_client import SemanticClient

        client = SemanticClient(key, model, timeout=90.0)
    try:
        client.analyze_chunk(TEST_SYSTEM, TEST_USER)
        return OkOut(ok=True, detail=f"Conexão OK — {model} respondeu pelo caminho real da análise "
                                     f"(streaming + saída estruturada)")
    except Exception as exc:  # noqa: BLE001 — resposta amigável na UI
        return OkOut(ok=False, detail=f"Falha com {model}: {friendly_ai_error(exc)}")


@router.post("/settings/test-ai", response_model=OkOut)
def test_ai(body: TestAIIn):
    """Testa o provedor pelo MESMO caminho da análise de verdade."""
    return _run_ai_test(body.provider, body.api_key)


@router.post("/settings/test-anthropic", response_model=OkOut)
def test_anthropic(body: TestAnthropicIn):
    """Compatibilidade: equivale a test-ai com provider=claude."""
    return _run_ai_test("claude", body.api_key)
