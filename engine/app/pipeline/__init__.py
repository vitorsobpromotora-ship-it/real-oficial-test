"""Pipeline de processamento. `register_all()` importa os módulos que registram jobs."""

from __future__ import annotations

import importlib

# Módulos com @job_handler; adicionados conforme as fases do desenvolvimento.
_JOB_MODULES = ["orchestrator", "render"]


def register_all() -> None:
    for name in _JOB_MODULES:
        try:
            importlib.import_module(f".{name}", package=__package__)
        except ModuleNotFoundError:
            continue
