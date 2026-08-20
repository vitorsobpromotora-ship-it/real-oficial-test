"""F5 — Reenquadramento avançado: modos fit/duas pessoas/split, overrides por
trecho, punch-in e os grafos correspondentes. Barra de prontidão:
detecção → crop plan → prévia → override manual → render → teste.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.pipeline.reframe import (
    apply_framing_override,
    apply_punch_in,
    apply_segment_overrides,
)
from app.pipeline.render import _video_base_chains

PLAN = {"mode": "crop", "crop_w": 606, "crop_h": 1080, "face_hit_rate": 0.9,
        "clusters": [420.0, 1460.0],
        "segments": [{"start": 0.0, "end": 30.0, "x0": 120, "x1": 120}]}


def test_override_fit_e_blur():
    fit = apply_framing_override(dict(PLAN), "fit", 1920, 1080, 0, 30)
    assert fit["mode"] == "fit_pad" and fit["segments"] == []
    blur = apply_framing_override(dict(PLAN), "blur", 1920, 1080, 0, 30)
    assert blur["mode"] == "blur_pad"


def test_override_duas_pessoas_e_split():
    two = apply_framing_override(dict(PLAN), "two", 1920, 1080, 0, 30)
    assert two["mode"] == "two_person"
    assert two["crop_w"] == 1214, "painel 1080×960 → corte 9:8 da fonte 1080p"
    xa, xb = two["panels"][0]["x"], two["panels"][1]["x"]
    assert xa < xb, "painel de cima = rosto da esquerda, de baixo = da direita"
    assert xa == 0 and xb == 706, (xa, xb)

    sp = apply_framing_override(dict(PLAN), "split", 1920, 1080, 0, 30)
    assert sp["mode"] == "split_screen" and sp["crop_w"] == 302
    assert sp["panels"][0]["x"] == 420 - 151

    # sem dois rostos: posições padrão esquerda/direita (não falha)
    sem = apply_framing_override({**PLAN, "clusters": []}, "two", 1920, 1080, 0, 30)
    assert sem["mode"] == "two_person" and sem["panels"][0]["x"] < sem["panels"][1]["x"]


def test_overrides_por_trecho_fatiam_o_plano():
    """"00:10–00:20 → foco esquerda": só aquele trecho muda; o resto segue auto."""
    plan = apply_segment_overrides(
        dict(PLAN), [{"start_s": 10.0, "end_s": 20.0, "mode": "left"}], 1920)
    segs = plan["segments"]
    assert [(s["start"], s["end"]) for s in segs] == [(0.0, 10.0), (10.0, 20.0), (20.0, 30.0)]
    x_esq = int(max(0, 420 - 606 / 2))
    assert segs[1]["x0"] == x_esq and segs[0]["x0"] == 120 and segs[2]["x0"] == 120

    # override cobrindo tudo substitui inteiro; modo inválido é ignorado
    todo = apply_segment_overrides(
        dict(PLAN), [{"start_s": 0, "end_s": 30, "mode": "center"},
                     {"start_s": 5, "end_s": 8, "mode": "banana"}], 1920)
    assert len(todo["segments"]) == 1
    assert todo["segments"][0]["x0"] == int(1920 / 2 - 303)
    # planos sem modo crop não são tocados
    intocado = apply_segment_overrides({"mode": "blur_pad", "segments": []},
                                       [{"start_s": 0, "end_s": 9, "mode": "left"}], 1920)
    assert intocado["segments"] == []


def test_punch_in_leve_e_dinamico():
    plan = {"mode": "crop", "crop_w": 606, "crop_h": 1080, "segments": [
        {"start": 0.0, "end": 10.0, "x0": 100, "x1": 100},
        {"start": 10.0, "end": 20.0, "x0": 800, "x1": 800},
        {"start": 20.0, "end": 30.0, "x0": 100, "x1": 100}]}
    leve = apply_punch_in(plan, "leve")
    assert all(s["zoom"] == 1.05 for s in leve["segments"])
    dyn = apply_punch_in(plan, "dinamico")
    assert "zoom" not in dyn["segments"][0] and dyn["segments"][1]["zoom"] == 1.10
    assert "zoom" not in dyn["segments"][2]
    assert apply_punch_in(plan, "off") == plan
    assert apply_punch_in({"mode": "blur_pad"}, "leve") == {"mode": "blur_pad"}


def test_grafo_fit_pad_com_e_sem_edl():
    chains, v = _video_base_chains(
        crop_plan={"mode": "fit_pad", "segments": []}, video_trims=None,
        out_w=1080, out_h=1920)
    g = ";".join(chains)
    assert "force_original_aspect_ratio=decrease" in g and "pad=1080:1920" in g
    assert v == "vbase"
    chains, _ = _video_base_chains(
        crop_plan={"mode": "fit_pad", "segments": []},
        video_trims=[{"start": 0.0, "end": 5.0}, {"start": 8.0, "end": 12.0}],
        out_w=1080, out_h=1920)
    g = ";".join(chains)
    assert "concat=n=2:v=1:a=0[vcut]" in g and "[vcut]scale=" in g


def test_grafo_duas_pessoas_e_split():
    plan = {"mode": "two_person", "crop_w": 1214, "crop_h": 1080,
            "panels": [{"x": 0}, {"x": 706}], "segments": []}
    chains, _ = _video_base_chains(crop_plan=plan, video_trims=None, out_w=1080, out_h=1920)
    g = ";".join(chains)
    assert "[0:v]split=2[p0][p1]" in g
    assert "crop=1214:1080:0:0,scale=1080:960" in g
    assert "crop=1214:1080:706:0,scale=1080:960" in g
    assert "[pp0][pp1]vstack[vbase]" in g

    plan = {"mode": "split_screen", "crop_w": 302, "crop_h": 1080,
            "panels": [{"x": 269}, {"x": 1309}], "segments": []}
    chains, _ = _video_base_chains(crop_plan=plan, video_trims=None, out_w=540, out_h=960)
    g = ";".join(chains)
    assert "scale=270:960" in g and "hstack[vbase]" in g


def test_grafo_punch_in_zoom():
    plan = {"mode": "crop", "crop_w": 606, "crop_h": 1080, "segments": [
        {"start": 0.0, "end": 5.0, "x0": 100, "x1": 100},
        {"start": 5.0, "end": 10.0, "x0": 800, "x1": 800, "zoom": 1.10}]}
    chains, _ = _video_base_chains(crop_plan=plan, video_trims=None, out_w=1080, out_h=1920)
    g = ";".join(chains)
    # 606/1.1=550→550 par; 1080/1.1=981→980; dx=(606-550)/2=28; dy=(1080-980)/2=50
    assert "crop=550:980:828:50" in g, "zoom central: janela menor deslocada p/ o centro"
    assert "crop=550:980:828:50,scale=606:1080" in g, "pedaço com zoom volta ao tamanho comum"
    assert "crop=606:1080:100:0" in g


def test_patch_framing_e_punch_in(client, auth):
    from app.db.base import session
    from app.db.models import CutCandidate, Project, SourceVideo

    with session() as s:
        p = Project(name="F5")
        s.add(p)
        s.flush()
        src = SourceVideo(project_id=p.id, origin="file", file_path="/v.mp4",
                          duration_s=60, status="ready")
        s.add(src)
        s.flush()
        c = CutCandidate(source_video_id=src.id, project_id=p.id, start_s=1, end_s=20,
                         score=70, title="C")
        s.add(c)
        s.flush()
        cut_id = c.id

    r = client.patch(f"/api/v1/cuts/{cut_id}", json={"framing": "two"}, headers=auth)
    assert r.status_code == 200 and r.json()["edits"]["framing"] == "two"
    r = client.patch(f"/api/v1/cuts/{cut_id}", json={"punch_in": "leve"}, headers=auth)
    assert r.json()["edits"]["punch_in"] == "leve"
    r = client.patch(f"/api/v1/cuts/{cut_id}", json={"punch_in": "off"}, headers=auth)
    assert "punch_in" not in (r.json()["edits"] or {})
    r = client.patch(f"/api/v1/cuts/{cut_id}", json={"framing": "banana"}, headers=auth)
    assert r.status_code == 422

    # overrides por trecho viajam em edits (o Editor grava a lista completa)
    r = client.patch(f"/api/v1/cuts/{cut_id}",
                     json={"edits": {"framing": "two",
                                     "framing_segments": [
                                         {"start_s": 18.0, "end_s": 24.0, "mode": "left"}]}},
                     headers=auth)
    assert r.status_code == 200
    assert r.json()["edits"]["framing_segments"][0]["mode"] == "left"


@pytest.mark.e2e
def test_render_real_duas_pessoas_e_fit(client, auth):
    """Renderiza o MESMO corte em 'two' (empilhado) e 'fit' (com barras) e
    verifica geometria por pixels: painéis distintos no primeiro, barras
    pretas no segundo."""
    from .conftest import wait_job
    from .fixtures import make_media

    if not make_media.have_espeak():
        pytest.skip("espeak-ng indisponível")
    video = make_media.fixture_video("fixture_30s.mp4", duration=30.0)

    from app.db.base import session
    from app.db.models import CutCandidate, Project, SourceVideo

    with session() as s:
        p = Project(name="F5 e2e")
        s.add(p)
        s.flush()
        src = SourceVideo(project_id=p.id, origin="file", file_path=str(video),
                          duration_s=30.0, width=1920, height=1080, fps=30.0,
                          status="ready")
        s.add(src)
        s.flush()
        c = CutCandidate(
            source_video_id=src.id, project_id=p.id, start_s=2.0, end_s=10.0, score=90.0,
            title="Dois painéis",
            crop_plan={"mode": "crop", "crop_w": 606, "crop_h": 1080,
                       "clusters": [480.0, 1440.0],
                       "segments": [{"start": 2.0, "end": 10.0, "x0": 200, "x1": 200}]})
        s.add(c)
        s.flush()
        cut_id = c.id

    import subprocess

    import cv2
    import numpy as np
    import sqlalchemy as sa

    from app.db.models import Render
    from app.services import ffmpeg as ff

    def render_e_frame(nome: str):
        resp = client.post("/api/v1/renders",
                           json={"cut_id": cut_id, "kind": "final",
                                 "overrides": {"video_preset": "ultrafast", "crf": 30}},
                           headers=auth)
        job = wait_job(client, auth, resp.json()["job_id"], timeout=300)
        assert job["status"] == "done", job
        with session() as s:
            rr = s.execute(sa.select(Render).where(Render.cut_id == cut_id)
                           .order_by(Render.created_at.desc())).scalars().first()
            out = Path(rr.output_path)
        meta = ff.probe(out)
        assert meta["width"] == 1080 and meta["height"] == 1920
        png = out.parent / f"{nome}.png"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-ss", "2", "-i", str(out), "-frames:v", "1", str(png)],
                       check=True, capture_output=True)
        img = cv2.imread(str(png))
        png.unlink(missing_ok=True)
        return img

    client.patch(f"/api/v1/cuts/{cut_id}", json={"framing": "two"}, headers=auth)
    img = render_e_frame("two")
    topo = img[200:800, :].astype(np.float32)
    base = img[1120:1720, :].astype(np.float32)
    assert float(np.mean(np.abs(topo - base))) > 6.0, \
        "painéis de cima e de baixo devem mostrar recortes diferentes"

    client.patch(f"/api/v1/cuts/{cut_id}", json={"framing": "fit"}, headers=auth)
    img = render_e_frame("fit")
    barra_topo = img[:200, :].astype(np.float32)
    meio = img[900:1000, :].astype(np.float32)
    assert float(barra_topo.mean()) < 22, "modo fit tem barras pretas em cima"
    assert float(meio.mean()) > 30, "faixa central mostra o vídeo inteiro"
