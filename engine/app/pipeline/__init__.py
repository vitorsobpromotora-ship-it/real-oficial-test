"""Pipeline de processamento. `register_all()` importa os módulos que registram jobs.

Imports ESTÁTICOS de propósito: o PyInstaller não rastreia importlib com nomes em
string — na v1.0.0 isso deixou os handlers de job fora do binário empacotado.
"""

from __future__ import annotations


def register_all() -> None:
    from . import orchestrator, render  # noqa: F401, PLC0415
