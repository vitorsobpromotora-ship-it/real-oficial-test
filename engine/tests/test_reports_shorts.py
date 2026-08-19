from __future__ import annotations

import io

import pytest

from app.schemas.claude import PARAM_KEYS


@pytest.fixture()
def db_semeado(client, auth):
    """Semeia projeto/fonte/cortes/custos/timings diretamente no DB para métricas previsíveis."""
    from app.db.base import session
    from app.db.models import ClaudeCall, CutCandidate, Project, SourceVideo, StageTiming

    with session() as s:
        p = Project(name="Relatórios")
        s.add(p)
        s.flush()
        src = SourceVideo(project_id=p.id, origin="file", file_path="/x.mp4", title="Pod #1",
                          duration_s=3600.0, width=1920, height=1080, status="ready")
        s.add(src)
        s.flush()
        base = dict.fromkeys(PARAM_KEYS, 7.0)
        cortes = [
            CutCandidate(source_video_id=src.id, project_id=p.id, start_s=10, end_s=40,
                         score=90.0, score_breakdown=base, rank=1, status="approved",
                         origin="claude", human_rank=2, title="A",
                         review_started_at="2026-08-19T10:00:00+00:00",
                         reviewed_at="2026-08-19T10:02:00+00:00"),
            CutCandidate(source_video_id=src.id, project_id=p.id, start_s=100, end_s=130,
                         score=80.0, score_breakdown=base, rank=2, status="approved",
                         origin="claude", human_rank=1, title="B",
                         review_started_at="2026-08-19T10:03:00+00:00",
                         reviewed_at="2026-08-19T10:04:00+00:00", edits={"trim": True}),
            CutCandidate(source_video_id=src.id, project_id=p.id, start_s=200, end_s=230,
                         score=70.0, score_breakdown=base, rank=3, status="rejected",
                         origin="claude", human_rank=3, title="C",
                         review_started_at="2026-08-19T10:05:00+00:00",
                         reviewed_at="2026-08-19T10:05:30+00:00"),
            CutCandidate(source_video_id=src.id, project_id=p.id, start_s=300, end_s=330,
                         score=60.0, score_breakdown=base, rank=4, status="draft",
                         origin="heuristic", title="D"),
        ]
        s.add_all(cortes)
        s.add(ClaudeCall(source_video_id=src.id, model="claude-opus-5",
                         input_tokens=20000, output_tokens=5000, cost_usd=0.225))
        s.add(StageTiming(source_video_id=src.id, stage="transcribe", seconds=120.0))
        s.add(StageTiming(source_video_id=src.id, stage="analyze", seconds=60.0))
        s.flush()
        return {"project_id": p.id, "source_id": src.id}


def test_relatorio_fonte_metricas(client, auth, db_semeado):
    r = client.get(f"/api/v1/reports/sources/{db_semeado['source_id']}", headers=auth)
    assert r.status_code == 200
    rep = r.json()
    assert rep["cortes"]["gerados"] == 4
    assert rep["cortes"]["aprovados"] == 2
    assert rep["cortes"]["taxa_aproveitamento"] == 0.5
    assert rep["cortes"]["origem_heuristica"] == 1
    # baseline = 60min (vídeo) + 8×2 (aprovados) = 76; revisão = 120+60+30s = 3.5min
    assert rep["tempo"]["baseline_manual_min"] == 76.0
    assert rep["tempo"]["revisao_investida_min"] == 3.5
    assert rep["tempo"]["economia_min"] == 72.5
    assert rep["intervencao"]["cortes_revisados"] == 3
    assert rep["intervencao"]["media_s"] == 70.0
    assert rep["intervencao"]["pct_editados"] == 0.25
    assert rep["custo_claude"]["total_usd"] == 0.225
    # ranks IA [1,2,3] vs humano [2,1,3] → Spearman = 0.5
    assert rep["score_quality"]["spearman_rank_ia_vs_humano"] == 0.5
    assert rep["score_quality"]["n_avaliados"] == 3
    assert {t["stage"] for t in rep["timings"]} == {"transcribe", "analyze"}


def test_relatorio_html(client, auth, db_semeado, token):
    r = client.get(f"/api/v1/reports/sources/{db_semeado['source_id']}/html?token={token}")
    assert r.status_code == 200
    html = r.text
    assert "Relatório do processamento" in html
    assert "taxa de aproveitamento" in html
    assert "50%" in html
    assert "Pod #1" in html


def test_relatorio_projeto_agregado(client, auth, db_semeado):
    r = client.get(f"/api/v1/reports/projects/{db_semeado['project_id']}", headers=auth)
    rep = r.json()
    assert rep["totais"]["fontes"] == 1
    assert rep["totais"]["cortes_gerados"] == 4
    assert rep["totais"]["taxa_aproveitamento"] == 0.5


def test_brand_kit_crud_e_logo(client, auth):
    r = client.post("/api/v1/brand-kits",
                    json={"name": "Meu Canal", "primary_color": "#FF0000",
                          "caption_preset": "clean", "is_default": True},
                    headers=auth)
    assert r.status_code == 201
    kit = r.json()
    assert kit["is_default"] is True

    # PNG mínimo (1×1)
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d49444154789c626001000000ffff03000006000557bfabd40000000049454e44ae426082")
    r = client.post(f"/api/v1/brand-kits/{kit['id']}/logo",
                    files={"file": ("logo.png", io.BytesIO(png), "image/png")}, headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["logo_path"].endswith(".png")

    r2 = client.post("/api/v1/brand-kits", json={"name": "Outro", "is_default": True}, headers=auth)
    kits = client.get("/api/v1/brand-kits", headers=auth).json()
    defaults = [k for k in kits if k["is_default"]]
    assert len(defaults) == 1 and defaults[0]["id"] == r2.json()["id"], \
        "só um kit pode ser padrão por vez"


def test_fachada_shorts(client, auth, monkeypatch, tmp_path):
    """Contrato da fachada /shorts sem processar de verdade (handler substituído)."""
    from app.jobs import registry

    def fake_process(ctx):
        return {"ok": True}

    monkeypatch.setitem(registry.JOB_HANDLERS, "process_source", (fake_process, "pipeline"))
    video = tmp_path / "v.mp4"
    video.write_bytes(b"00")

    r = client.post("/api/v1/shorts", json={"file_path": str(video)}, headers=auth)
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"short_job_id", "source_video_id", "project_id"}

    from .conftest import wait_job

    wait_job(client, auth, body["short_job_id"])
    r = client.get(f"/api/v1/shorts/{body['short_job_id']}", headers=auth)
    detail = r.json()
    assert detail["status"] == "done"
    assert detail["clips"] == []

    lista = client.get("/api/v1/shorts", headers=auth).json()
    assert any(item["id"] == body["short_job_id"] for item in lista)

    assert client.post("/api/v1/shorts", json={}, headers=auth).status_code == 422
