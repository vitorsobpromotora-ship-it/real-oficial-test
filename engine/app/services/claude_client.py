"""Cliente Claude para análise semântica: saída estruturada, cache de prompt,
registro de custo e detecção de recusa. A escada de fallback fica em pipeline/semantic.py.
"""

from __future__ import annotations

import logging

from ..db.base import session
from ..db.models import ClaudeCall
from ..schemas.claude import ChunkAnalysis

log = logging.getLogger(__name__)

# USD por MTok (entrada, saída). Cache: escrita 1.25x, leitura 0.10x da entrada.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


class RefusalError(RuntimeError):
    """O modelo recusou a análise (stop_reason == 'refusal')."""


def compute_cost_usd(model: str, input_tokens: int, output_tokens: int,
                     cache_read: int = 0, cache_creation: int = 0) -> float:
    p_in, p_out = PRICES_PER_MTOK.get(model, (5.0, 25.0))
    return round(
        (input_tokens * p_in + output_tokens * p_out
         + cache_read * p_in * 0.10 + cache_creation * p_in * 1.25) / 1_000_000, 6)


def estimate_cost_per_hour_usd(model: str) -> float:
    """Estimativa pré-processamento: ~5 chunks/h; ≈22k tokens de entrada e ≈11k de saída
    (inclui thinking adaptativo) por hora de vídeo falado."""
    p_in, p_out = PRICES_PER_MTOK.get(model, (5.0, 25.0))
    return round((22_000 * p_in + 11_000 * p_out) / 1_000_000, 4)


class SemanticClient:
    def __init__(self, api_key: str, model: str, timeout: float = 240.0):
        import anthropic

        self._anthropic = anthropic
        self.model = model
        self.client = anthropic.Anthropic(api_key=api_key, max_retries=3, timeout=timeout)

    def request_kwargs(self, system_text: str, user_text: str, model: str | None = None) -> dict:
        """Kwargs da chamada (separado para testabilidade sem rede)."""
        return {
            "model": model or self.model,
            "max_tokens": 16000,
            "thinking": {"type": "adaptive"},
            "system": [{"type": "text", "text": system_text,
                        "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": user_text}],
            "output_format": ChunkAnalysis,
        }

    def analyze_chunk(self, system_text: str, user_text: str, *, model: str | None = None,
                      source_video_id: str | None = None, job_id: str | None = None) -> ChunkAnalysis:
        kwargs = self.request_kwargs(system_text, user_text, model)
        response = self.client.messages.parse(**kwargs)
        self._record_usage(response, kwargs["model"], source_video_id, job_id)
        if getattr(response, "stop_reason", None) == "refusal":
            detail = ""
            stop_details = getattr(response, "stop_details", None)
            if stop_details is not None:
                detail = f" ({getattr(stop_details, 'category', '')})"
            raise RefusalError(f"Análise recusada pelo modelo {kwargs['model']}{detail}")
        parsed = getattr(response, "parsed_output", None)
        if parsed is None:
            raise ValueError("Resposta do modelo sem saída estruturada válida")
        return parsed

    def _record_usage(self, response, model: str, source_video_id: str | None,
                      job_id: str | None) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
        try:
            with session() as s:
                s.add(ClaudeCall(
                    job_id=job_id, source_video_id=source_video_id, model=model,
                    input_tokens=input_tokens, output_tokens=output_tokens,
                    cache_read_tokens=cache_read, cache_creation_tokens=cache_creation,
                    cost_usd=compute_cost_usd(model, input_tokens, output_tokens,
                                              cache_read, cache_creation)))
        except Exception:  # registro de custo nunca derruba o pipeline
            log.exception("Falha ao registrar uso do Claude")
