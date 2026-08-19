from __future__ import annotations

import os
import stat


def test_health_sem_auth(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["app"] == "real-oficial-engine"


def test_rotas_exigem_token(client):
    assert client.get("/api/v1/projects").status_code == 401
    assert client.get("/api/v1/projects", headers={"Authorization": "Bearer errado"}).status_code == 401


def test_token_file_criado(client, data_dir, token):
    token_file = data_dir / "api_token"
    assert token_file.exists()
    assert token_file.read_text().strip() == token
    if os.name == "posix":
        mode = stat.S_IMODE(token_file.stat().st_mode)
        assert mode == 0o600


def test_crud_projetos(client, auth):
    r = client.post("/api/v1/projects", json={"name": "Podcast X", "description": "eps"}, headers=auth)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    r = client.get("/api/v1/projects", headers=auth)
    assert any(p["id"] == pid for p in r.json())

    r = client.patch(f"/api/v1/projects/{pid}", json={"name": "Podcast Y"}, headers=auth)
    assert r.json()["name"] == "Podcast Y"

    r = client.delete(f"/api/v1/projects/{pid}", headers=auth)
    assert r.json()["ok"] is True
    assert client.get(f"/api/v1/projects/{pid}", headers=auth).status_code == 404


def test_settings_mascara_chave(client, auth):
    r = client.get("/api/v1/settings", headers=auth)
    assert r.status_code == 200
    assert r.json()["has_anthropic_api_key"] is False
    assert r.json()["claude_model"] == "claude-opus-5"

    r = client.put("/api/v1/settings",
                   json={"anthropic_api_key": "sk-ant-teste-1234567890", "whisper_model": "tiny"},
                   headers=auth)
    body = r.json()
    assert body["has_anthropic_api_key"] is True
    assert "sk-ant-teste-1234567890" not in body["anthropic_api_key_masked"]
    assert body["whisper_model"] == "tiny"
