"""F1 — Editor de Corte: modelo EDL não destrutivo.

Unidade (mapeamentos/validação/fatiamento), API (PATCH edl, reabertura idêntica,
invalidação de prévia, waveform) e e2e (render real de EDL com 2 segmentos +
fades, verificado por ffprobe). A regra de ouro: a MESMA EDL alimenta prévia e
render final, e reabrir um corte devolve exatamente o que foi salvo.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.pipeline import edl as edl_mod

# ---------------------------------------------------------------- unidade


def test_cut_edl_implicita_e_normalizacao():
    # sem EDL persistida: implícita [start_s → end_s]
    eff = edl_mod.cut_edl({"edl": None, "start_s": 10.0, "end_s": 40.0})
    assert eff["segments"] == [{"src_start": 10.0, "src_end": 40.0}]
    assert eff["audio"] == {"gain_db": 0.0, "mute": False, "fade_in_s": 0.0, "fade_out_s": 0.0}
    assert edl_mod.out_duration(eff) == 30.0
    assert edl_mod.envelope(eff) == (10.0, 40.0)

    # segmentos minúsculos caem; fades negativos são zerados
    eff = edl_mod.cut_edl({"edl": {"segments": [
        {"src_start": 5.0, "src_end": 5.01},
        {"src_start": 8.0, "src_end": 12.0}], "fade_in_s": -1}, "start_s": 0, "end_s": 1})
    assert eff["segments"] == [{"src_start": 8.0, "src_end": 12.0}]
    assert eff["fade_in_s"] == 0.0


def test_validate_edl_erros():
    assert edl_mod.validate_edl({"segments": []}, 60.0)
    assert any("maior que início" in e
               for e in edl_mod.validate_edl({"segments": [{"src_start": 9, "src_end": 4}]}, 60))
    assert any("negativo" in e
               for e in edl_mod.validate_edl({"segments": [{"src_start": -2, "src_end": 4}]}, 60))
    assert any("além da duração" in e
               for e in edl_mod.validate_edl({"segments": [{"src_start": 10, "src_end": 90}]}, 60))
    assert any("menor que 1s" in e
               for e in edl_mod.validate_edl({"segments": [{"src_start": 2, "src_end": 2.5}]}, 60))
    assert edl_mod.validate_edl({"segments": [{"src_start": 2, "src_end": 20}]}, 60.0) == []


def test_src_to_out_e_map_words():
    edl = edl_mod.cut_edl({"edl": {"segments": [
        {"src_start": 10.0, "src_end": 16.0},
        {"src_start": 20.0, "src_end": 26.0}]}, "start_s": 0, "end_s": 1})
    assert edl_mod.src_to_out(edl, 12.0) == 2.0
    assert edl_mod.src_to_out(edl, 18.0) is None, "instante removido não existe na saída"
    assert edl_mod.src_to_out(edl, 21.0) == 7.0

    words = [{"idx": 1, "start_s": 11.0, "end_s": 11.5, "word": "olá"},
             {"idx": 2, "start_s": 17.0, "end_s": 18.0, "word": "removida"},
             {"idx": 3, "start_s": 20.5, "end_s": 21.0, "word": "volta"}]
    out = edl_mod.map_words(words, edl, {"word_overrides": {"3": "voltou"}})
    assert [w["word"] for w in out] == ["olá", "voltou"], \
        "palavra do trecho removido cai; override de texto vale no corte"
    assert out[0]["start_s"] == 1.0 and out[1]["start_s"] == 6.5


def test_map_intervals_fatiado_pela_edl():
    edl = edl_mod.cut_edl({"edl": {"segments": [
        {"src_start": 0.0, "src_end": 5.0},
        {"src_start": 10.0, "src_end": 15.0}]}, "start_s": 0, "end_s": 1})
    # intervalo atravessa o buraco: vira dois pedaços contíguos na saída
    out = edl_mod.map_intervals([{"start": 4.0, "end": 11.0}], edl)
    assert out == [{"start": 4.0, "end": 5.0}, {"start": 5.0, "end": 6.0}]


def test_slice_crop_plan_dois_relogios_e_interpolacao():
    plan = {"mode": "crop", "crop_w": 606, "crop_h": 1080, "segments": [
        {"start": 0.0, "end": 10.0, "x0": 0, "x1": 100},     # x anda 10px/s
        {"start": 10.0, "end": 30.0, "x0": 500, "x1": 500}]}
    edl = edl_mod.cut_edl({"edl": {"segments": [
        {"src_start": 4.0, "src_end": 12.0},
        {"src_start": 20.0, "src_end": 26.0}]}, "start_s": 0, "end_s": 1})
    sliced = edl_mod.slice_crop_plan(plan, edl)
    segs = sliced["segments"]
    # SAÍDA contígua 0..14; FONTE cobre exatamente cada segmento da EDL
    assert segs[0]["start"] == 0.0 and segs[-1]["end"] == 14.0
    for prev, nxt in zip(segs, segs[1:], strict=False):
        assert prev["end"] == nxt["start"]
    assert (segs[0]["src_start"], segs[0]["src_end"]) == (4.0, 10.0)
    assert (segs[1]["src_start"], segs[1]["src_end"]) == (10.0, 12.0)
    assert (segs[2]["src_start"], segs[2]["src_end"]) == (20.0, 26.0)
    assert [s["edl_seg"] for s in segs] == [0, 0, 1]
    assert segs[0]["x0"] == 40, "x interpolado no ponto do fatiamento (t=4 → 40)"
    assert segs[0]["x1"] == 100 and segs[1]["x0"] == 500


def test_edl_clamped_apara_e_descarta():
    edl = {"version": 1, "segments": [{"src_start": 5.0, "src_end": 10.0},
                                      {"src_start": 14.0, "src_end": 20.0}]}
    apertada = edl_mod.edl_clamped(edl, 7.0, 16.0)
    assert apertada["segments"] == [{"src_start": 7.0, "src_end": 10.0},
                                    {"src_start": 14.0, "src_end": 16.0}]
    assert edl_mod.edl_clamped(edl, 30.0, 40.0) is None, "nada sobrando → corte simples"
    assert edl_mod.edl_clamped(None, 0, 10) is None


# ---------------------------------------------------------------- API


def _seed_cut(start=10.0, end=40.0, duration=120.0):
    from app.db.base import session
    from app.db.models import CutCandidate, Project, SourceVideo

    with session() as s:
        p = Project(name="Editor")
        s.add(p)
        s.flush()
        src = SourceVideo(project_id=p.id, origin="file", file_path="/video.mp4",
                          duration_s=duration, status="ready")
        s.add(src)
        s.flush()
        c = CutCandidate(source_video_id=src.id, project_id=p.id, start_s=start, end_s=end,
                         score=80.0, title="Corte editável",
                         crop_plan={"mode": "crop", "crop_w": 606, "crop_h": 1080,
                                    "segments": [{"start": start, "end": end,
                                                  "x0": 50, "x1": 50}]})
        s.add(c)
        s.flush()
        return c.id, src.id, p.id


def test_patch_edl_persiste_e_reabre_identico(client, auth):
    from app import config

    cut_id, _, _ = _seed_cut()
    prev = config.data_dir() / "media" / "previews" / f"{cut_id}.mp4"
    prev.parent.mkdir(parents=True, exist_ok=True)
    prev.write_bytes(b"fake")

    edl = {"segments": [{"src_start": 12.0, "src_end": 20.0},
                        {"src_start": 24.0, "src_end": 36.0}],
           "fade_in_s": 0.5, "transition_s": 0.12,
           "audio": {"gain_db": -2.0, "fade_out_s": 0.3}}
    r = client.patch(f"/api/v1/cuts/{cut_id}", json={"edl": edl}, headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    # envelope dirige start/end; enquadramento será recalculado; prévia caiu
    assert (body["start_s"], body["end_s"]) == (12.0, 36.0)
    assert body["crop_plan"] is None
    assert not prev.exists(), "edição visual invalida a prévia antiga"
    assert body["edl"]["segments"] == [{"src_start": 12.0, "src_end": 20.0},
                                       {"src_start": 24.0, "src_end": 36.0}]
    assert body["edl"]["fade_in_s"] == 0.5
    assert body["edl"]["audio"]["gain_db"] == -2.0

    # reabrir = idêntico ao salvo (critério de aceitação: salvar → fechar → reabrir)
    again = client.get(f"/api/v1/cuts/{cut_id}", headers=auth).json()
    assert again["edl"] == body["edl"]
    assert (again["start_s"], again["end_s"]) == (12.0, 36.0)

    # limpar com null volta ao corte simples
    r = client.patch(f"/api/v1/cuts/{cut_id}", json={"edl": None}, headers=auth)
    assert r.json()["edl"] is None


def test_patch_edl_invalida_da_422(client, auth):
    cut_id, _, _ = _seed_cut(duration=60.0)
    r = client.patch(f"/api/v1/cuts/{cut_id}",
                     json={"edl": {"segments": [{"src_start": 9, "src_end": 4}]}}, headers=auth)
    assert r.status_code == 422 and "EDL inválida" in r.json()["detail"]
    r = client.patch(f"/api/v1/cuts/{cut_id}",
                     json={"edl": {"segments": [{"src_start": 10, "src_end": 300}]}},
                     headers=auth)
    assert r.status_code == 422 and "além da duração" in r.json()["detail"]
    r = client.patch(f"/api/v1/cuts/{cut_id}", json={"edl": {"segments": []}}, headers=auth)
    assert r.status_code == 422


def test_patch_edl_trivial_nao_persiste(client, auth):
    """Salvar do Editor sem mudar nada não deve marcar o corte como editado."""
    cut_id, _, _ = _seed_cut(start=10.0, end=40.0)
    r = client.patch(f"/api/v1/cuts/{cut_id}",
                     json={"edl": {"segments": [{"src_start": 10.0, "src_end": 40.0}]}},
                     headers=auth)
    assert r.status_code == 200
    assert r.json()["edl"] is None
    assert r.json()["crop_plan"] is not None, "sem mudança de envelope, plano permanece"


def test_trim_rapido_apara_edl_existente(client, auth):
    cut_id, _, _ = _seed_cut()
    client.patch(f"/api/v1/cuts/{cut_id}",
                 json={"edl": {"segments": [{"src_start": 12.0, "src_end": 20.0},
                                            {"src_start": 24.0, "src_end": 36.0}]}},
                 headers=auth)
    r = client.patch(f"/api/v1/cuts/{cut_id}", json={"start_s": 15.0, "end_s": 30.0},
                     headers=auth)
    body = r.json()
    assert body["edl"]["segments"] == [{"src_start": 15.0, "src_end": 20.0},
                                       {"src_start": 24.0, "src_end": 30.0}]
    # trim que engole a edição inteira volta ao corte simples
    r = client.patch(f"/api/v1/cuts/{cut_id}", json={"start_s": 20.5, "end_s": 23.5},
                     headers=auth)
    assert r.json()["edl"] is None


def test_waveform_da_janela_do_corte(client, auth):
    import numpy as np
    import soundfile as sf

    from app.db.base import session
    from app.db.models import SourceVideo

    cut_id, src_id, _ = _seed_cut(start=2.0, end=6.0, duration=10.0)
    from app import config
    wav_path = config.data_dir() / "tmp" / "fonte.wav"
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    sr = 16000
    t = np.linspace(0, 10.0, sr * 10, endpoint=False)
    sf.write(wav_path, (0.5 * np.sin(2 * np.pi * 220 * t)).astype("float32"), sr)
    with session() as s:
        s.get(SourceVideo, src_id).audio_path = str(wav_path)

    r = client.get(f"/api/v1/cuts/{cut_id}/waveform?pps=40&pad_s=15", headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["start_s"] == 0.0 and body["end_s"] <= 10.0
    assert body["pps"] == 40.0
    assert len(body["peaks"]) == pytest.approx(10 * 40, abs=2)
    assert max(body["peaks"]) > 0.4, "picos devem refletir a amplitude real do áudio"


# ---------------------------------------------------------------- e2e render


@pytest.mark.e2e
def test_render_real_com_edl_de_dois_segmentos(client, auth):
    """Prévia e final saem da MESMA EDL: renderiza um corte com trecho do meio
    removido + fades e confere duração/dimensões/áudio no arquivo final."""
    from .conftest import wait_job
    from .fixtures import make_media

    if not make_media.have_espeak():
        pytest.skip("espeak-ng indisponível")
    video = make_media.fixture_video("fixture_30s.mp4", duration=30.0)

    from app.db.base import session
    from app.db.models import CutCandidate, Project, SourceVideo

    with session() as s:
        p = Project(name="EDL e2e")
        s.add(p)
        s.flush()
        src = SourceVideo(project_id=p.id, origin="file", file_path=str(video),
                          duration_s=30.0, width=1920, height=1080, fps=30.0, status="ready")
        s.add(src)
        s.flush()
        c = CutCandidate(
            source_video_id=src.id, project_id=p.id, start_s=2.0, end_s=18.0, score=90.0,
            title="Corte com EDL",
            crop_plan={"mode": "crop", "crop_w": 606, "crop_h": 1080,
                       "segments": [{"start": 2.0, "end": 18.0, "x0": 200, "x1": 200}]})
        s.add(c)
        s.flush()
        cut_id = c.id

    edl = {"segments": [{"src_start": 2.0, "src_end": 8.0},
                        {"src_start": 12.0, "src_end": 18.0}],
           "fade_in_s": 0.4, "fade_out_s": 0.4, "transition_s": 0.15,
           "audio": {"gain_db": 2.0}}
    r = client.patch(f"/api/v1/cuts/{cut_id}", json={"edl": edl}, headers=auth)
    assert r.status_code == 200, r.text
    assert (r.json()["start_s"], r.json()["end_s"]) == (2.0, 18.0)

    resp = client.post("/api/v1/renders",
                       json={"cut_id": cut_id, "kind": "final",
                             "overrides": {"video_preset": "ultrafast", "crf": 30}},
                       headers=auth)
    assert resp.status_code in (200, 201), resp.text
    job = wait_job(client, auth, resp.json()["job_id"], timeout=300)
    assert job["status"] == "done", job

    from app.db.base import session as sess
    from app.db.models import Render

    with sess() as s:
        rr = s.execute(__import__("sqlalchemy").select(Render)
                       .where(Render.cut_id == cut_id)).scalars().first()
        out = Path(rr.output_path)
    assert out.exists() and out.stat().st_size > 30_000

    from app.services import ffmpeg as ff

    meta = ff.probe(out)
    assert meta["width"] == 1080 and meta["height"] == 1920
    assert meta["has_audio"]
    assert abs(meta["duration_s"] - 12.0) < 0.5, \
        f"duração de saída deve ser a da EDL (12s), veio {meta['duration_s']}"
