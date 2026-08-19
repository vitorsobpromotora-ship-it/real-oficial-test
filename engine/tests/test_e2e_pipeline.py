"""E2E principal: vídeo sintético 90s → pipeline completo (transcrição e semântica fakes)
→ cortes com crop plan → render em lote → MP4 1080×1920 verificado (codec, duração,
faststart, legenda queimada por análise de pixels).
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.schemas.claude import PARAM_KEYS

from .conftest import wait_job
from .fixtures import make_media
from .test_ingest_transcribe import _FakeWhisper

pytestmark = pytest.mark.e2e


def _raw(start, end, nota, title):
    return {"start_s": start, "end_s": end, "params": dict.fromkeys(PARAM_KEYS, nota),
            "hook_line": f"Gancho de {title}", "title": title,
            "hashtags": ["#viral", "#cortes"], "reason": "teste e2e", "origin": "claude"}


def _moov_antes_de_mdat(path: Path) -> bool:
    data = path.read_bytes()[:4_000_000]
    i_moov, i_mdat = data.find(b"moov"), data.find(b"mdat")
    return i_moov != -1 and (i_mdat == -1 or i_moov < i_mdat)


def test_pipeline_completo_ate_mp4(client, auth, monkeypatch):
    if not make_media.have_espeak():
        pytest.skip("espeak-ng indisponível")
    video = make_media.fixture_video("fixture_90s.mp4", duration=90.0)

    monkeypatch.setattr("app.pipeline.transcribe.get_model", lambda size: _FakeWhisper())
    monkeypatch.setattr(
        "app.pipeline.analyze.analyze_semantic",
        lambda ctx, sid, sentences, features, duration, report, **kw: [
            _raw(2.0, 20.0, 8.0, "Primeiro corte"),
            _raw(30.0, 48.0, 7.0, "Segundo corte"),
            _raw(60.0, 80.0, 6.0, "Terceiro corte"),
        ])

    pid = client.post("/api/v1/projects", json={"name": "E2E"}, headers=auth).json()["id"]
    r = client.post(f"/api/v1/projects/{pid}/sources",
                    json={"origin": "file", "file_path": str(video), "auto_process": True},
                    headers=auth)
    final = wait_job(client, auth, r.json()["job_id"], timeout=300)
    assert final["status"] == "done", final

    cuts = client.get(f"/api/v1/projects/{pid}/cuts", headers=auth).json()
    assert len(cuts) == 3
    assert all(c["crop_plan"] is not None for c in cuts), "reframe deve ter rodado"
    assert all(c["crop_plan"]["mode"] in ("crop", "blur_pad") for c in cuts)

    client.post("/api/v1/cuts/bulk",
                json={"cut_ids": [c["id"] for c in cuts], "patch": {"status": "approved"}},
                headers=auth)

    batch = client.post("/api/v1/renders/batch",
                        json={"cut_ids": [c["id"] for c in cuts],
                              "overrides": {"video_preset": "ultrafast", "crf": 30}},
                        headers=auth).json()
    assert batch["total"] == 3

    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        b = client.get(f"/api/v1/renders/batches/{batch['id']}", headers=auth).json()
        if all(r["status"] in ("done", "failed", "canceled") for r in b["renders"]):
            break
        time.sleep(1.0)
    else:
        raise AssertionError(f"lote não terminou: {b}")

    falhas = [r for r in b["renders"] if r["status"] != "done"]
    assert not falhas, f"renders falharam: {[(r['id'], r['error']) for r in falhas]}"
    assert b["status"] == "done" and b["done"] == 3

    from app.services import ffmpeg as ff

    cuts_by_id = {c["id"]: c for c in cuts}
    for rr in b["renders"]:
        out = Path(rr["output_path"])
        assert out.exists() and out.stat().st_size > 50_000
        meta = ff.probe(out)
        assert meta["width"] == 1080 and meta["height"] == 1920
        cut = cuts_by_id[rr["cut_id"]]
        esperado = cut["end_s"] - cut["start_s"]
        assert abs(meta["duration_s"] - esperado) < 0.6, (meta["duration_s"], esperado)
        assert _moov_antes_de_mdat(out), "faststart (+moov antes de mdat) é obrigatório"

    # Legenda queimada: banda inferior central deve conter texto claro (pixels brilhantes)
    import subprocess

    import cv2
    import numpy as np

    out = Path(b["renders"][0]["output_path"])
    frame_png = out.parent / "frame_check.png"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-ss", "3", "-i", str(out), "-frames:v", "1", str(frame_png)],
                   check=True, capture_output=True)
    img = cv2.imread(str(frame_png), cv2.IMREAD_GRAYSCALE)
    assert img is not None and img.shape == (1920, 1080)
    banda_legenda = img[1300:1750, 150:930]
    assert float(np.percentile(banda_legenda, 99.5)) > 150, \
        "esperava pixels claros de texto na banda de legenda"
    frame_png.unlink(missing_ok=True)

    # download via endpoint de mídia com token em query
    token = client.get("/api/v1/settings", headers=auth).json()["api_token"]
    resp = client.get(f"/api/v1/media/{b['renders'][0]['id']}/file?token={token}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "video/mp4"
