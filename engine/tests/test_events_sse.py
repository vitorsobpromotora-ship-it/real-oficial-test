from __future__ import annotations

import json

from .conftest import wait_job


def test_sse_replay_com_last_event_id(client, auth, token):
    """Após um job rodar, conectar com last_event_id=0 deve reproduzir o histórico."""
    runner = client.app_ref.state.runner
    job_id = runner.submit("test_rapido")
    wait_job(client, auth, job_id)

    eventos = []
    with client.stream("GET", f"/api/v1/events?token={token}&last_event_id=0&max_events=3") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        atual = {}
        for linha in resp.iter_lines():
            if linha.startswith("event:"):
                atual["event"] = linha.split(":", 1)[1].strip()
            elif linha.startswith("data:"):
                atual["data"] = json.loads(linha.split(":", 1)[1].strip())
            elif linha == "" and atual:
                eventos.append(atual)
                atual = {}

    tipos = [e["event"] for e in eventos]
    assert "job.updated" in tipos
    jobs_vistos = {e["data"].get("job_id") for e in eventos if e["event"] == "job.updated"}
    assert job_id in jobs_vistos


def test_sse_exige_token(client):
    r = client.get("/api/v1/events")
    assert r.status_code == 401
