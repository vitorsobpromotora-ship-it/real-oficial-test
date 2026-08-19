from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from .conftest import wait_job
from .fixtures import make_media


@pytest.fixture(scope="session")
def video_30s() -> Path:
    if not make_media.have_espeak():
        pytest.skip("espeak-ng indisponível para gerar áudio de teste")
    return make_media.fixture_video("fixture_30s.mp4", duration=30.0)


def test_probe_e_extracao_audio(video_30s, tmp_path):
    from app.services import ffmpeg

    meta = ffmpeg.probe(video_30s)
    assert meta["width"] == 1920 and meta["height"] == 1080
    assert 29.0 <= meta["duration_s"] <= 31.5
    assert meta["has_audio"] is True

    from app.pipeline.ingest import extract_audio_wav16k

    wav = extract_audio_wav16k(video_30s, tmp_path / "audio.wav", duration=meta["duration_s"])
    wmeta = ffmpeg.probe(wav)
    assert 29.0 <= wmeta["duration_s"] <= 31.5


class _FakeWhisper:
    """Transcritor determinístico: distribui as palavras do texto do fixture pela duração."""

    def transcribe(self, audio_path, **kwargs):
        from app.services import ffmpeg

        duration = ffmpeg.probe(audio_path)["duration_s"] or 30.0
        palavras = make_media.TEXTO_PADRAO.replace(".", " .").split()
        n = len(palavras)
        passo = duration / (n + 1)
        segs = []
        por_frase: list[list] = [[]]
        t = 0.0
        for w in palavras:
            if w == ".":
                if por_frase[-1]:
                    por_frase.append([])
                continue
            por_frase[-1].append(SimpleNamespace(start=t, end=t + passo * 0.9, word=" " + w,
                                                 probability=0.98))
            t += passo
        idx = 0
        for frase in por_frase:
            if not frase:
                continue
            segs.append(SimpleNamespace(
                start=frase[0].start, end=frase[-1].end,
                text=" ".join(w.word.strip() for w in frase) + ".", words=frase, id=idx))
            idx += 1
        info = SimpleNamespace(language="pt", duration=duration)
        return iter(segs), info


@pytest.fixture()
def fake_whisper(monkeypatch):
    monkeypatch.setattr("app.pipeline.transcribe.get_model", lambda size: _FakeWhisper())


def test_pipeline_arquivo_ate_transcricao(client, auth, video_30s, fake_whisper):
    """Fluxo completo via API: projeto → fonte (arquivo) → process → transcript."""
    pid = client.post("/api/v1/projects", json={"name": "Teste B"}, headers=auth).json()["id"]
    r = client.post(f"/api/v1/projects/{pid}/sources",
                    json={"origin": "file", "file_path": str(video_30s), "auto_process": True},
                    headers=auth)
    assert r.status_code == 201, r.text
    body = r.json()
    source_id, job_id = body["source"]["id"], body["job_id"]
    assert job_id

    final = wait_job(client, auth, job_id, timeout=120)
    assert final["status"] == "done", final

    src = client.get(f"/api/v1/sources/{source_id}", headers=auth).json()
    assert src["status"] == "ready"
    assert src["width"] == 1920 and src["height"] == 1080
    assert Path(src["file_path"]).exists() and Path(src["audio_path"] or "") is not None

    t = client.get(f"/api/v1/sources/{source_id}/transcript?include_words=true", headers=auth).json()
    assert t["language"] == "pt"
    assert len(t["segments"]) >= 2
    words = t["words"]
    assert len(words) > 10
    starts = [w["start_s"] for w in words]
    assert starts == sorted(starts), "timestamps de palavras devem ser monotônicos"
    assert all(w["end_s"] >= w["start_s"] for w in words)


def test_ingest_url_mockada(client, auth, video_30s, fake_whisper, monkeypatch):
    """Caminho origin=url sem rede: download_url substituído por cópia local."""

    def fake_download(url, dest_dir, progress_cb=None, cancel_check=None):
        dest = Path(dest_dir) / "video_baixado.mp4"
        shutil.copy2(video_30s, dest)
        if progress_cb:
            progress_cb(1.0)
        return dest, "Vídeo de Teste (URL)"

    monkeypatch.setattr("app.pipeline.ingest.download_url", fake_download)
    pid = client.post("/api/v1/projects", json={"name": "Teste URL"}, headers=auth).json()["id"]
    r = client.post(f"/api/v1/projects/{pid}/sources",
                    json={"origin": "url", "url": "https://youtube.com/watch?v=xyz",
                          "auto_process": True},
                    headers=auth)
    body = r.json()
    final = wait_job(client, auth, body["job_id"], timeout=120)
    assert final["status"] == "done", final
    src = client.get(f"/api/v1/sources/{body['source']['id']}", headers=auth).json()
    assert src["status"] == "ready"
    assert src["title"] == "Vídeo de Teste (URL)"


def _whisper_tiny_disponivel() -> bool:
    try:
        from faster_whisper import WhisperModel

        from app import config

        WhisperModel("tiny", device="cpu", compute_type="int8",
                     download_root=str(config.data_dir() / "models"), local_files_only=True)
        return True
    except Exception:
        return False


@pytest.mark.skipif(not make_media.have_espeak(), reason="espeak-ng indisponível")
def test_transcricao_real_whisper_tiny(data_dir, tmp_path):
    """Transcrição real com faster-whisper tiny — roda quando o modelo está no cache local (CI)."""
    import os

    os.environ.setdefault("HF_HUB_OFFLINE", "0")
    if not _whisper_tiny_disponivel() and not os.environ.get("REAL_OFICIAL_TEST_WHISPER_DOWNLOAD"):
        pytest.skip("modelo whisper tiny não disponível offline (baixado no CI)")

    from app import config
    from app.pipeline import transcribe as tr

    config.ensure_dirs()
    wav = make_media.espeak_wav(tmp_path / "fala.wav")
    model = tr.get_model("tiny")
    segments, info = model.transcribe(str(wav), language="pt", word_timestamps=True, vad_filter=True)
    words = [w for seg in segments for w in (seg.words or [])]
    assert len(words) >= 5
    starts = [w.start for w in words]
    assert starts == sorted(starts)
