from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    d = tmp_path / "data"
    monkeypatch.setenv("REAL_OFICIAL_DATA_DIR", str(d))
    return d


@pytest.fixture()
def client(data_dir):
    from app.main import create_app

    application = create_app()
    with TestClient(application) as c:
        c.app_ref = application
        yield c


@pytest.fixture()
def token(client) -> str:
    from app.db import settings_store

    return settings_store.get_setting("api_token")


@pytest.fixture()
def auth(token) -> dict:
    return {"Authorization": f"Bearer {token}"}


def wait_job(client, auth, job_id: str, timeout: float = 15.0) -> dict:
    """Espera um job atingir estado terminal via API."""
    import time

    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        r = client.get(f"/api/v1/jobs/{job_id}", headers=auth)
        assert r.status_code == 200, r.text
        last = r.json()
        if last["status"] in ("done", "failed", "canceled"):
            return last
        time.sleep(0.05)
    raise AssertionError(f"Job {job_id} não terminou a tempo: {last}")
