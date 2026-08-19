"""Aplicação FastAPI do motor Real Oficial + entrypoint do sidecar.

Uso dev:   uvicorn app.main:app --port 8756   (ou: python -m app.main --port 8756)
Uso prod:  real-oficial-engine.exe --port N --parent-pid P   (PyInstaller)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .db import settings_store
from .db.base import init_engine
from .db.migrate import migrate
from .jobs.bus import EventBus
from .jobs.runner import JobRunner

log = logging.getLogger("real-oficial")


def _load_job_handlers() -> None:
    """Importa módulos que registram handlers de job (efeito colateral do decorator)."""
    from .pipeline import register_all  # noqa: PLC0415

    register_all()


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.ensure_dirs()
    init_engine(config.db_path())
    migrate()
    app.state.api_token = settings_store.bootstrap_settings()

    bus = EventBus()
    bus.bind_loop(asyncio.get_running_loop())
    runner = JobRunner(bus)
    app.state.bus = bus
    app.state.runner = runner
    _load_job_handlers()
    await runner.start()
    log.info("Motor Real Oficial pronto (dados em %s)", config.data_dir())
    try:
        yield
    finally:
        await runner.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="Real Oficial Engine", version=config.VERSION, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "null"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from .api import (  # noqa: PLC0415
        routes_events,
        routes_jobs,
        routes_projects,
        routes_settings,
        routes_system,
    )

    app.include_router(routes_system.router)  # /health e /system/* na raiz
    for r in (routes_projects, routes_jobs, routes_events, routes_settings):
        app.include_router(r.router, prefix=config.API_PREFIX)

    _include_optional_routers(app)
    return app


def _include_optional_routers(app: FastAPI) -> None:
    """Rotas adicionadas em fases posteriores; import tolerante para desenvolvimento incremental."""
    import importlib  # noqa: PLC0415

    for name in ("routes_sources", "routes_cuts", "routes_renders", "routes_media",
                 "routes_brand_kits", "routes_reports", "routes_shorts"):
        try:
            mod = importlib.import_module(f".api.{name}", package=__package__)
        except ModuleNotFoundError:
            continue
        app.include_router(mod.router, prefix=config.API_PREFIX)


app = create_app()


async def _serve(server, parent_pid: int | None) -> None:
    tasks = [asyncio.create_task(server.serve())]

    async def watch_parent():
        import psutil  # noqa: PLC0415

        while True:
            await asyncio.sleep(5)
            if parent_pid and not psutil.pid_exists(parent_pid):
                log.warning("Processo pai %s encerrou — desligando o motor", parent_pid)
                server.should_exit = True
                return

    if parent_pid:
        tasks.append(asyncio.create_task(watch_parent()))
    await tasks[0]
    for t in tasks[1:]:
        t.cancel()


def run(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Motor Real Oficial")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8756)
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--parent-pid", type=int, default=None)
    args = parser.parse_args(argv)

    if args.data_dir:
        os.environ["REAL_OFICIAL_DATA_DIR"] = args.data_dir

    config.ensure_dirs()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(config.data_dir() / "logs" / "engine.log", encoding="utf-8"),
        ],
    )

    import uvicorn  # noqa: PLC0415

    uv_config = uvicorn.Config(app, host=args.host, port=args.port, log_level="info")
    server = uvicorn.Server(uv_config)
    app.state.server = server
    asyncio.run(_serve(server, args.parent_pid))


if __name__ == "__main__":
    run()
