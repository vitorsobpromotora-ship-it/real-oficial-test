"""Registro de uso/custo das chamadas de IA (Claude e OpenAI) e tradução de erros.

A tabela `claude_calls` guarda TODAS as chamadas de IA (a coluna `model`
distingue o provedor); os relatórios somam o custo total de IA a partir dela.
"""

from __future__ import annotations

import logging

from ..db.base import session
from ..db.models import ClaudeCall

log = logging.getLogger(__name__)

# USD por MTok (entrada, saída). Cache Anthropic: escrita 1.25x, leitura 0.10x da entrada.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "gpt-5.1": (1.25, 10.0),
    "gpt-5": (1.25, 10.0),
    "gpt-5-mini": (0.25, 2.0),
    "gpt-5-nano": (0.05, 0.40),
    "gpt-4.1": (2.0, 8.0),
    "gpt-4o": (2.5, 10.0),
}


def compute_cost_usd(model: str, input_tokens: int, output_tokens: int,
                     cache_read: int = 0, cache_creation: int = 0) -> float:
    p_in, p_out = PRICES_PER_MTOK.get(model, (5.0, 25.0))
    return round(
        (input_tokens * p_in + output_tokens * p_out
         + cache_read * p_in * 0.10 + cache_creation * p_in * 1.25) / 1_000_000, 6)


def record_ai_usage(model: str, *, input_tokens: int, output_tokens: int,
                    cache_read: int = 0, cache_creation: int = 0,
                    source_video_id: str | None = None, job_id: str | None = None) -> None:
    try:
        with session() as s:
            s.add(ClaudeCall(
                job_id=job_id, source_video_id=source_video_id, model=model,
                input_tokens=input_tokens, output_tokens=output_tokens,
                cache_read_tokens=cache_read, cache_creation_tokens=cache_creation,
                cost_usd=compute_cost_usd(model, input_tokens, output_tokens,
                                          cache_read, cache_creation)))
    except Exception:  # registro de custo nunca derruba o pipeline
        log.exception("Falha ao registrar uso de IA")


def friendly_ai_error(exc: Exception) -> str:
    """Traduz erros de API em mensagens acionáveis em PT-BR (sem jargão bruto)."""
    text = str(exc)
    low = text.lower()
    if "authentication" in low or "invalid x-api-key" in low or "incorrect api key" in low \
            or "api key is invalid" in low or "401" in low:
        return "Chave de API inválida ou revogada — confira a chave em Configurações."
    if "credit balance" in low or "insufficient_quota" in low or "billing" in low \
            or "exceeded your current quota" in low:
        return "A conta está sem créditos/quota para este modelo — verifique o faturamento do provedor."
    if "not_found" in low and "model" in low or "does not exist" in low and "model" in low:
        return f"O modelo configurado não está disponível para a sua conta ({text[:120]})."
    if "rate limit" in low or "429" in low or "overloaded" in low:
        return "O provedor está limitando as requisições agora (rate limit) — tente novamente em instantes."
    if "certificate" in low or "ssl" in low:
        return f"Falha de certificado TLS ao conectar na API — antivírus/proxy corporativo pode estar interceptando ({text[:120]})."
    if "timed out" in low or "timeout" in low:
        return "A chamada excedeu o tempo limite — conexão lenta ou instável com a API."
    if "connection" in low or "connect" in low:
        return "Não foi possível conectar à API — verifique internet, firewall e antivírus."
    return text[:300]
