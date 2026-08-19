"""Rotas de sistema: health (sem auth) e shutdown."""

from __future__ import annotations

import asyncio
import signal

from fastapi import APIRouter, Depends, Request

from .. import config
from ..schemas.api import OkOut
from .deps import require_token

router = APIRouter()


@router.get("/health")
def health(request: Request):
    return {
        "status": "ok",
        "app": "real-oficial-engine",
        "version": config.VERSION,
        "data_dir": str(config.data_dir()),
    }


@router.post("/system/shutdown", response_model=OkOut, dependencies=[Depends(require_token)])
async def shutdown(request: Request):
    server = getattr(request.app.state, "server", None)

    def _stop():
        if server is not None:
            server.should_exit = True
        else:
            signal.raise_signal(signal.SIGTERM)

    asyncio.get_running_loop().call_later(0.3, _stop)
    return OkOut(ok=True, detail="Encerrando o motor")
