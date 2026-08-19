"""Registro de handlers de job: tipo → (handler, lane).

Handlers podem ser síncronos (executados via asyncio.to_thread) ou corrotinas.
Assinatura: handler(ctx: JobContext) -> dict | None (resultado gravado no job).
"""

from __future__ import annotations

from collections.abc import Callable

JOB_HANDLERS: dict[str, tuple[Callable, str]] = {}


def job_handler(job_type: str, lane: str = "pipeline"):
    def decorator(fn: Callable):
        JOB_HANDLERS[job_type] = (fn, lane)
        return fn

    return decorator


def get_handler(job_type: str) -> tuple[Callable, str]:
    if job_type not in JOB_HANDLERS:
        raise KeyError(f"Nenhum handler registrado para o tipo de job '{job_type}'")
    return JOB_HANDLERS[job_type]


def lane_for(job_type: str) -> str:
    try:
        return get_handler(job_type)[1]
    except KeyError:
        return "pipeline"
