from __future__ import annotations

import numpy as np
import pytest

from app.pipeline import candidates as cand
from app.pipeline import semantic
from app.pipeline.audio_features import Features, compute_features
from app.pipeline.heuristic import analyze_heuristic
from app.schemas.claude import PARAM_KEYS, CandidateSegment, ChunkAnalysis, Params
from app.services.claude_client import RefusalError, SemanticClient, compute_cost_usd


@pytest.fixture()
def wav_sintetico(tmp_path):
    """30s: silêncio(0–10) + tom forte 440Hz(10–12) + silêncio(12–20) + ruído de fala(20–30)."""
    import soundfile as sf

    sr = 16000
    t = np.linspace(0, 1, sr, endpoint=False)
    silence = np.zeros(sr)
    tone = 0.8 * np.sin(2 * np.pi * 440 * t)
    rng = np.random.default_rng(42)
    speech = 0.25 * rng.standard_normal(sr)
    audio = np.concatenate([np.tile(silence, 10), np.tile(tone, 2), np.tile(silence, 8),
                            np.tile(speech, 10)]).astype(np.float32)
    path = tmp_path / "sintetico.wav"
    sf.write(path, audio, sr)
    return path


def test_audio_features_detecta_pico_e_pausas(wav_sintetico):
    words = [{"start_s": 20 + i * 0.5, "end_s": 20 + i * 0.5 + 0.4, "word": f"p{i}"}
             for i in range(20)]
    f = compute_features(str(wav_sintetico), words)
    assert len(f.peak_curve) >= 29
    assert f.peak_curve[10:13].max() > f.peak_curve[3:9].max(), \
        "o tom forte deve elevar a curva frente ao silêncio"
    assert any(p[0] <= 12 and p[1] >= 19 for p in f.pauses), f"pausa (…→20s) esperada: {f.pauses}"
    assert any(e["type"] == "pico_energia" and 9 <= e["t"] <= 13 for e in f.events)


def test_heuristica_deterministica(wav_sintetico):
    sentences = [{"start_s": i * 5.0, "end_s": i * 5.0 + 5.0, "text": f"Frase número {i}."}
                 for i in range(6)]
    f = compute_features(str(wav_sintetico), [])
    a = analyze_heuristic(sentences, f, target_count=4, min_s=10, max_s=60, duration=30)
    b = analyze_heuristic(sentences, f, target_count=4, min_s=10, max_s=60, duration=30)
    assert a == b
    assert all(set(c["params"].keys()) == set(PARAM_KEYS) for c in a)


def test_chunking_com_overlap():
    sentences = [{"start_s": i * 10.0, "end_s": i * 10.0 + 9.5, "text": f"s{i}"} for i in range(100)]
    chunks = semantic.build_chunks(sentences, duration=1000.0)
    assert len(chunks) >= 2
    assert chunks[0]["start"] == 0.0
    assert chunks[-1]["end"] == sentences[-1]["end_s"]
    for prev, nxt in zip(chunks, chunks[1:], strict=False):
        assert nxt["start"] <= prev["end"] - 30.0, "chunks devem ter overlap"


def test_request_kwargs_formato_atual_da_api():
    client = SemanticClient(api_key="sk-teste", model="claude-opus-5")
    kwargs = client.request_kwargs("SYSTEM", "USER")
    assert kwargs["model"] == "claude-opus-5"
    assert kwargs["thinking"] == {"type": "adaptive"}
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    fmt = kwargs["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["schema"]["additionalProperties"] is False
    assert kwargs["max_tokens"] == 24000
    assert "budget_tokens" not in str(kwargs)


def test_schema_estrito_para_saida_estruturada():
    from app.schemas.claude import strict_chunk_schema

    schema = strict_chunk_schema()
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["segments"]
    seg = schema["$defs"]["CandidateSegment"]
    assert seg["additionalProperties"] is False
    assert set(seg["required"]) == set(seg["properties"].keys())
    params = schema["$defs"]["Params"]
    assert set(params["required"]) == set(PARAM_KEYS)


def test_openai_request_body_formato_atual():
    from app.services.openai_client import OpenAIClient

    client = OpenAIClient(api_key="sk-teste", model="gpt-5.1")
    body = client.request_body("SYSTEM", "USER")
    assert body["model"] == "gpt-5.1"
    assert body["max_completion_tokens"] == 24000
    assert "max_tokens" not in body and "temperature" not in body
    rf = body["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["strict"] is True
    assert rf["json_schema"]["schema"]["additionalProperties"] is False
    assert body["messages"][0]["role"] == "system"


def test_custo_computado():
    custo = compute_cost_usd("claude-opus-5", 100_000, 10_000, cache_read=50_000)
    assert custo == pytest.approx((100_000 * 5 + 10_000 * 25 + 50_000 * 0.5) / 1e6)


class _FakeClient:
    """Simula SemanticClient: recusa no primário, funciona no fallback."""

    def __init__(self, fail_primary=True, fail_fallback=False):
        self.fail_primary = fail_primary
        self.fail_fallback = fail_fallback
        self.calls: list = []

    def analyze_chunk(self, system, user, *, model=None, source_video_id=None, job_id=None):
        self.calls.append(model)
        if model is None and self.fail_primary:
            raise RefusalError("recusado")
        if model is not None and self.fail_fallback:
            raise RuntimeError("falhou também")
        return ChunkAnalysis(segments=[
            CandidateSegment(start_s=10.0, end_s=40.0, params=Params(),
                             hook_line="Olá", title="Título")
        ])


def _chunk_exemplo():
    return {"start": 0.0, "end": 60.0,
            "sentences": [{"start_s": 0.0, "end_s": 60.0, "text": "Uma frase longa de teste."}]}


def test_escada_fallback_para_modelo_secundario():
    fake = _FakeClient(fail_primary=True, fail_fallback=False)
    out, ok, err = semantic._chunk_ladder(fake, "claude-sonnet-5", _chunk_exemplo(), None,
                                          lambda c: [{"origin": "heuristic"}],
                                          source_video_id=None, job_id=None)
    assert fake.calls == [None, "claude-sonnet-5"]
    assert ok is True and err is None
    assert out and out[0]["origin"] == "claude"


def test_escada_cai_na_heuristica_com_erro_registrado():
    fake = _FakeClient(fail_primary=True, fail_fallback=True)
    out, ok, err = semantic._chunk_ladder(fake, "claude-sonnet-5", _chunk_exemplo(), None,
                                          lambda c: [{"origin": "heuristic", "marcador": True}],
                                          source_video_id=None, job_id=None)
    assert out == [{"origin": "heuristic", "marcador": True}]
    assert ok is False and err, "a queda para heurística deve carregar o motivo"


def test_origem_gpt_marcada_no_candidato():
    fake = _FakeClient(fail_primary=False)
    out, ok, _ = semantic._chunk_ladder(fake, None, _chunk_exemplo(), None,
                                        lambda c: [], source_video_id=None, job_id=None,
                                        origin="gpt")
    assert ok and out[0]["origin"] == "gpt"


def test_snap_dedup_diversify():
    sentences = [{"start_s": i * 5.0, "end_s": (i + 1) * 5.0, "text": f"f{i}"} for i in range(12)]
    s, e = cand.snap_to_sentences(7.0, 26.0, sentences, min_s=15, max_s=90, duration=60)
    assert s == 5.0 and e == 30.0

    feats = Features(hop=1.0, times=np.arange(60), rms=np.zeros(60),
                     peak_curve=np.full(60, 0.5))
    raw = [
        {"start_s": 0, "end_s": 16, "params": dict.fromkeys(PARAM_KEYS, 8.0),
         "title": "A", "origin": "claude"},
        {"start_s": 1, "end_s": 17, "params": dict.fromkeys(PARAM_KEYS, 6.0),
         "title": "B", "origin": "claude"},
        {"start_s": 40, "end_s": 56, "params": dict.fromkeys(PARAM_KEYS, 7.0),
         "title": "C", "origin": "claude"},
    ]
    final, stats = cand.finalize_candidates(raw, sentences, feats, min_s=15, max_s=90,
                                            duration=60, target_count=5)
    assert stats["brutos"] == 3 and stats["finais"] == len(final) and stats["alvo"] == 5
    titles = [c["title"] for c in final]
    assert "B" not in titles, "sobreposto de score menor deve ser removido (IoU)"
    assert set(titles) == {"A", "C"}
    assert final[0]["score"] >= final[-1]["score"]
    assert all("semantic_score" in c and "rhpt_score" in c for c in final)


def _raw(start, end, nota, title):
    return {"start_s": start, "end_s": end, "params": dict.fromkeys(PARAM_KEYS, nota),
            "hook_line": f"Gancho {title}", "title": title,
            "hashtags": ["#x"], "reason": "teste", "origin": "claude"}


def test_stage_analyze_via_api(client, auth, monkeypatch):
    """Pipeline completo com transcrição e semântica fakes → cortes ranqueados na API."""
    from pathlib import Path

    from .fixtures import make_media
    from .test_ingest_transcribe import _FakeWhisper

    if not make_media.have_espeak():
        pytest.skip("espeak-ng indisponível")
    video = make_media.fixture_video("fixture_30s.mp4", duration=30.0)
    monkeypatch.setattr("app.pipeline.transcribe.get_model", lambda size: _FakeWhisper())
    monkeypatch.setattr(
        "app.pipeline.analyze.analyze_semantic",
        lambda ctx, sid, sentences, features, duration, report, **kw: ([
            _raw(0, 16, 8.0, "Melhor corte"),
            _raw(1, 17, 6.0, "Duplicado"),
            _raw(14, 29.5, 7.0, "Segundo corte"),
        ], {"agent": kw.get("agent") or "local", "model": "", "chunks": 1, "ia_ok": 1,
            "erro": None}))

    pid = client.post("/api/v1/projects", json={"name": "Fase C"}, headers=auth).json()["id"]
    r = client.post(f"/api/v1/projects/{pid}/sources",
                    json={"origin": "file", "file_path": str(Path(video)), "auto_process": True},
                    headers=auth)
    from .conftest import wait_job

    final = wait_job(client, auth, r.json()["job_id"], timeout=180)
    assert final["status"] == "done", final

    cuts = client.get(f"/api/v1/projects/{pid}/cuts", headers=auth).json()
    assert len(cuts) == 2, [c["title"] for c in cuts]
    assert cuts[0]["title"] == "Melhor corte"
    assert cuts[0]["rank"] == 1 and cuts[1]["rank"] == 2
    assert set(cuts[0]["score_breakdown"].keys()) == set(PARAM_KEYS)
    assert cuts[0]["score"] > cuts[1]["score"] > 0
    assert all(c["status"] == "draft" for c in cuts)

    cut_id = cuts[0]["id"]
    r = client.patch(f"/api/v1/cuts/{cut_id}", json={"review_started": True}, headers=auth)
    assert r.json()["review_started_at"] is not None
    r = client.patch(f"/api/v1/cuts/{cut_id}", json={"status": "approved"}, headers=auth)
    assert r.json()["status"] == "approved" and r.json()["reviewed_at"] is not None

    r = client.post("/api/v1/cuts/bulk",
                    json={"cut_ids": [c["id"] for c in cuts],
                          "patch": {"caption_style": {"preset": "bold_karaoke"}}},
                    headers=auth)
    assert r.json()["ok"] is True
    cuts2 = client.get(f"/api/v1/projects/{pid}/cuts", headers=auth).json()
    assert all(c["caption_style"] == {"preset": "bold_karaoke"} for c in cuts2)


class _CtxFake:
    job_id = "job-teste"
    payload: dict = {"options": {}}

    def check_cancel(self):
        return None


def _sentencas_60s():
    return [{"start_s": i * 5.0, "end_s": (i + 1) * 5.0, "text": f"Frase {i} de teste."}
            for i in range(12)]


def _features_60s():
    from app.pipeline.audio_features import Features

    return Features(hop=1.0, times=np.arange(60), rms=np.zeros(60),
                    peak_curve=np.full(60, 0.5))


def test_agente_ia_falha_total_interrompe_o_job(client, monkeypatch):
    """Chave presente + IA falhando em todos os trechos → erro real, nunca heurística muda."""
    from app.db import settings_store

    settings_store.set_setting("anthropic_api_key", "sk-ant-qualquer")

    class _SempreFalha:
        model = "claude-opus-5"

        def analyze_chunk(self, *a, **kw):
            raise RuntimeError("SSL: CERTIFICATE_VERIFY_FAILED simulada")

    monkeypatch.setattr("app.pipeline.semantic.build_client",
                        lambda agent: (_SempreFalha(), None, "claude-opus-5"))
    with pytest.raises(RuntimeError) as exc:
        semantic.analyze_semantic(_CtxFake(), "src-x", _sentencas_60s(), _features_60s(), 60.0,
                                  lambda f, m="": None, min_s=15, max_s=90, target_count=5,
                                  agent="claude")
    msg = str(exc.value)
    assert "falhou em todos" in msg
    assert "certificado" in msg.lower() or "TLS" in msg, \
        "a causa raiz traduzida deve aparecer na mensagem do job"


def test_agente_local_explicito_nao_exige_chave(client):
    raw, meta = semantic.analyze_semantic(_CtxFake(), "src-x", _sentencas_60s(), _features_60s(),
                                          60.0, lambda f, m="": None, min_s=15, max_s=90,
                                          target_count=5, agent="local")
    assert meta["agent"] == "local" and meta["ia_ok"] == 0
    assert all(c["origin"] == "heuristic" for c in raw)


def test_agente_explicito_sem_chave_retorna_422(client, auth, tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"00")
    pid = client.post("/api/v1/projects", json={"name": "Agente"}, headers=auth).json()["id"]
    r = client.post(f"/api/v1/projects/{pid}/sources",
                    json={"origin": "file", "file_path": str(video), "auto_process": True,
                          "agent": "gpt"},
                    headers=auth)
    assert r.status_code == 422
    assert "OpenAI" in r.json()["detail"]

    # sem escolha explícita e sem chave → aceita e roda como local (honesto)
    r = client.post(f"/api/v1/projects/{pid}/sources",
                    json={"origin": "file", "file_path": str(video), "auto_process": False},
                    headers=auth)
    assert r.status_code == 201


def test_test_ai_endpoint_reporta_erro_amigavel(client, auth, monkeypatch):
    r = client.post("/api/v1/settings/test-ai", json={"provider": "gpt"}, headers=auth)
    assert r.json()["ok"] is False and "OpenAI" in r.json()["detail"]

    class _FalhaAuth:
        def __init__(self, *a, **kw):
            pass

        def analyze_chunk(self, *a, **kw):
            raise RuntimeError("HTTP 401: authentication_error — API key is invalid")

    monkeypatch.setattr("app.services.openai_client.OpenAIClient", _FalhaAuth)
    r = client.post("/api/v1/settings/test-ai",
                    json={"provider": "gpt", "api_key": "sk-falsa"}, headers=auth)
    body = r.json()
    assert body["ok"] is False
    assert "Chave de API inválida" in body["detail"]
