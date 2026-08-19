from __future__ import annotations

import time

from app.jobs.registry import job_handler

from .conftest import wait_job


@job_handler("test_rapido", lane="misc")
def _rapido(ctx):
    for i in range(4):
        ctx.check_cancel()
        ctx.report(stage="executando", progress=i / 4, force=True)
        time.sleep(0.02)
    return {"resultado": 42}


@job_handler("test_longo", lane="misc")
def _longo(ctx):
    for _ in range(200):
        ctx.check_cancel()
        time.sleep(0.05)
    return {}


@job_handler("test_falha", lane="misc")
def _falha(ctx):
    raise RuntimeError("explodiu de propósito")


def test_ciclo_job_completo(client, auth):
    runner = client.app_ref.state.runner
    job_id = runner.submit("test_rapido", {"x": 1})
    final = wait_job(client, auth, job_id)
    assert final["status"] == "done"
    assert final["progress"] == 1.0
    assert final["result"] == {"resultado": 42}


def test_job_falha_registra_erro(client, auth):
    runner = client.app_ref.state.runner
    job_id = runner.submit("test_falha")
    final = wait_job(client, auth, job_id)
    assert final["status"] == "failed"
    assert "explodiu" in final["error"]


def test_cancelamento(client, auth):
    runner = client.app_ref.state.runner
    job_id = runner.submit("test_longo")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        r = client.get(f"/api/v1/jobs/{job_id}", headers=auth).json()
        if r["status"] == "running":
            break
        time.sleep(0.05)
    assert client.post(f"/api/v1/jobs/{job_id}/cancel", headers=auth).status_code == 200
    final = wait_job(client, auth, job_id)
    assert final["status"] == "canceled"


def test_resume_apos_restart(data_dir):
    """Job 'running' órfão de uma execução anterior deve voltar à fila e concluir."""
    from fastapi.testclient import TestClient

    from app import config
    from app.db.base import init_engine, session
    from app.db.migrate import migrate
    from app.db.models import Job
    from app.main import create_app

    config.ensure_dirs()
    init_engine(config.db_path())
    migrate()
    with session() as s:
        j = Job(type="test_rapido", status="running", payload={})
        s.add(j)
        s.flush()
        job_id = j.id

    application = create_app()
    with TestClient(application) as client:
        client.app_ref = application
        from app.db import settings_store

        auth = {"Authorization": f"Bearer {settings_store.get_setting('api_token')}"}
        final = wait_job(client, auth, job_id)
        assert final["status"] == "done"
