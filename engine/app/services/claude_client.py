"""Cliente Claude para análise semântica: streaming + saída estruturada, cache de
prompt, registro de custo e detecção de recusa. A escada de fallback fica em
pipeline/semantic.py.

Streaming é obrigatório aqui: um chunk de ~12min com thinking adaptativo pode
levar vários minutos — a chamada não-streaming estourava o timeout HTTP e fazia
a análise "com chave válida" cair silenciosamente na heurística.
"""

from __future__ import annotations

import logging

from ..schemas.claude import ChunkAnalysis, strict_chunk_schema
from .ai_usage import compute_cost_usd, record_ai_usage  # noqa: F401 (re-export p/ compat)

log = logging.getLogger(__name__)


class RefusalError(RuntimeError):
    """O modelo recusou a análise (stop_reason == 'refusal')."""


def estimate_cost_per_hour_usd(model: str) -> float:
    """Estimativa pré-processamento: ~5 chunks/h; ≈22k tokens de entrada e ≈11k de saída
    (inclui thinking adaptativo) por hora de vídeo falado."""
    from .ai_usage import PRICES_PER_MTOK

    p_in, p_out = PRICES_PER_MTOK.get(model, (5.0, 25.0))
    return round((22_000 * p_in + 11_000 * p_out) / 1_000_000, 4)


class SemanticClient:
    def __init__(self, api_key: str, model: str, timeout: float = 900.0):
        import anthropic

        self._anthropic = anthropic
        self.model = model
        self.client = anthropic.Anthropic(api_key=api_key, max_retries=3, timeout=timeout)

    def request_kwargs(self, system_text: str, user_text: str, model: str | None = None) -> dict:
        """Kwargs da chamada em streaming (separado para testabilidade sem rede)."""
        return {
            "model": model or self.model,
            "max_tokens": 24000,
            "thinking": {"type": "adaptive"},
            "system": [{"type": "text", "text": system_text,
                        "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": user_text}],
            "output_config": {"format": {"type": "json_schema", "schema": strict_chunk_schema()}},
        }

    def analyze_chunk(self, system_text: str, user_text: str, *, model: str | None = None,
                      source_video_id: str | None = None, job_id: str | None = None) -> ChunkAnalysis:
        kwargs = self.request_kwargs(system_text, user_text, model)
        with self.client.messages.stream(**kwargs) as stream:
            response = stream.get_final_message()
        self._record_usage(response, kwargs["model"], source_video_id, job_id)
        if getattr(response, "stop_reason", None) == "refusal":
            detail = ""
            stop_details = getattr(response, "stop_details", None)
            if stop_details is not None:
                detail = f" ({getattr(stop_details, 'category', '')})"
            raise RefusalError(f"Análise recusada pelo modelo {kwargs['model']}{detail}")
        if getattr(response, "stop_reason", None) == "max_tokens":
            raise ValueError("Resposta truncada (max_tokens) — chunk grande demais")
        text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
        if not text.strip():
            raise ValueError("Resposta do modelo sem saída estruturada válida")
        return ChunkAnalysis.model_validate_json(text)

    def _record_usage(self, response, model: str, source_video_id: str | None,
                      job_id: str | None) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        record_ai_usage(
            model,
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            cache_read=getattr(usage, "cache_read_input_tokens", 0) or 0,
            cache_creation=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            source_video_id=source_video_id, job_id=job_id)
