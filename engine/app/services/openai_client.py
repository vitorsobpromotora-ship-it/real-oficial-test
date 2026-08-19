"""Cliente OpenAI (GPT) para análise semântica — mesma interface do SemanticClient.

Usa a Chat Completions API via httpx (sem SDK extra no binário) com
`response_format: json_schema` estrito, garantindo o MESMO shape de saída
(ChunkAnalysis) dos demais provedores. `max_completion_tokens` é o parâmetro
atual (modelos gpt-5.x rejeitam `max_tokens`); temperature é omitida (modelos
de raciocínio aceitam apenas o padrão).
"""

from __future__ import annotations

import logging
import time

import httpx

from ..schemas.claude import ChunkAnalysis, strict_chunk_schema
from .ai_usage import record_ai_usage
from .claude_client import RefusalError

log = logging.getLogger(__name__)

OPENAI_BASE_URL = "https://api.openai.com/v1"
RETRY_STATUS = {429, 500, 502, 503, 504}


class OpenAIClient:
    def __init__(self, api_key: str, model: str, timeout: float = 900.0):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def request_body(self, system_text: str, user_text: str, model: str | None = None) -> dict:
        """Corpo da requisição (separado para testabilidade sem rede)."""
        return {
            "model": model or self.model,
            "max_completion_tokens": 24000,
            "messages": [
                {"role": "system", "content": system_text},
                {"role": "user", "content": user_text},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "chunk_analysis", "strict": True,
                                "schema": strict_chunk_schema()},
            },
        }

    def analyze_chunk(self, system_text: str, user_text: str, *, model: str | None = None,
                      source_video_id: str | None = None, job_id: str | None = None) -> ChunkAnalysis:
        body = self.request_body(system_text, user_text, model)
        data = self._post_with_retry("/chat/completions", body)

        usage = data.get("usage") or {}
        record_ai_usage(body["model"],
                        input_tokens=int(usage.get("prompt_tokens") or 0),
                        output_tokens=int(usage.get("completion_tokens") or 0),
                        source_video_id=source_video_id, job_id=job_id)

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        if message.get("refusal"):
            raise RefusalError(f"Análise recusada pelo modelo {body['model']}: {message['refusal'][:200]}")
        if choice.get("finish_reason") == "length":
            raise ValueError("Resposta truncada (max_completion_tokens) — chunk grande demais")
        content = message.get("content") or ""
        if not content.strip():
            raise ValueError("Resposta do modelo sem saída estruturada válida")
        return ChunkAnalysis.model_validate_json(content)

    def _post_with_retry(self, path: str, body: dict, attempts: int = 3) -> dict:
        last_exc: Exception | None = None
        for attempt in range(attempts):
            try:
                resp = httpx.post(
                    f"{OPENAI_BASE_URL}{path}", json=body, timeout=self.timeout,
                    headers={"Authorization": f"Bearer {self.api_key}",
                             "Content-Type": "application/json"})
                if resp.status_code in RETRY_STATUS and attempt < attempts - 1:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                if resp.status_code >= 400:
                    try:
                        detail = resp.json().get("error", {}).get("message", resp.text)
                    except Exception:
                        detail = resp.text
                    raise RuntimeError(f"OpenAI HTTP {resp.status_code}: {detail[:300]}")
                return resp.json()
            except httpx.HTTPError as exc:  # rede/timeout — retry
                last_exc = exc
                if attempt < attempts - 1:
                    time.sleep(2.0 * (attempt + 1))
        raise RuntimeError(f"Falha de conexão com a OpenAI: {last_exc}")
