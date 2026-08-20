"""F3 — Brand Studio: layout de canvas 9:16 com camadas.

Unidade (validação, migração de kit legado, máscaras, ASS de textos, grafo),
API (templates, layout efetivo, PATCH com validação, invalidação de prévias,
upload de asset) e e2e (render real de um layout com fundo colorido + vídeo em
caixa, verificado por pixels). Barra de prontidão da fase:
canvas → persistência → prévia → render final → reabertura → teste.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.pipeline import compose

# ---------------------------------------------------------------- unidade


def _lay_minimo(**kw):
    lay = {"version": 2, "canvas": {"w": 1080, "h": 1920},
           "background": {"type": "color", "color": "#101418"},
           "layers": [{"id": "src", "type": "source", "x": 0, "y": 0, "w": 1080, "h": 1920}]}
    lay.update(kw)
    return lay


def test_validate_layout_erros_e_ok():
    assert compose.validate_layout({"layers": []})
    assert any("type=source" in e for e in compose.validate_layout(
        {"layers": [{"type": "text", "text": "oi", "x": 0, "y": 0, "w": 100}]}))
    assert any("tipo desconhecido" in e for e in compose.validate_layout(
        {"layers": [{"type": "banana", "x": 0, "y": 0, "w": 10, "h": 10},
                    {"type": "source", "x": 0, "y": 0, "w": 1080, "h": 1920}]}))
    assert any("falta o arquivo" in e for e in compose.validate_layout(
        {"layers": [{"type": "image", "x": 0, "y": 0, "w": 100, "h": 100},
                    {"type": "source", "x": 0, "y": 0, "w": 1080, "h": 1920}]}))
    assert compose.validate_layout(_lay_minimo()) == []
    for t in compose.TEMPLATES:
        assert compose.validate_layout(t["layout"]) == [], f"template {t['id']} inválido"


def test_layout_from_legacy_abre_qualquer_kit():
    """Migração automática: kit antigo (logo tr) vira layout equivalente."""
    lay = compose.layout_from_legacy({"logo_path": "/x/logo.png", "logo_position": "tr",
                                      "logo_opacity": 0.8})
    assert compose.validate_layout(lay) == []
    tipos = [x["type"] for x in lay["layers"]]
    assert tipos == ["source", "image", "captions"]
    logo = lay["layers"][1]
    assert logo["x"] == 1080 - 194 - 48 and logo["opacity"] == 0.8
    src = compose.source_layer(lay)
    assert (src["w"], src["h"]) == (1080, 1920), "vídeo em tela cheia como no clássico"
    # kit sem logo também abre
    assert compose.validate_layout(compose.layout_from_legacy({})) == []
    assert compose.validate_layout(compose.layout_from_legacy(None)) == []


def test_caption_overrides_da_area_de_legenda():
    lay = _lay_minimo()
    lay["layers"].append({"id": "cap", "type": "captions", "x": 120, "y": 1500, "w": 800})
    ov = compose.caption_overrides(lay)
    assert ov == {"anchor_top": 1500, "margin_l": 120, "margin_r": 1080 - 120 - 800}
    assert compose.caption_overrides(_lay_minimo()) == {}


def test_margens_explicitas_vencem_percentual():
    from app.pipeline.captions import _margens

    ml, mr, top = _margens({"anchor_top": 1500, "margin_l": 120, "margin_r": 160}, (1080, 1920))
    assert (ml, mr, top) == (120, 160, 1500)


def test_mascaras_png_geradas(tmp_path):
    import cv2

    nome = compose.make_mask_png(tmp_path / "m.png", 200, 120, 30)
    m = cv2.imread(str(tmp_path / nome), cv2.IMREAD_GRAYSCALE)
    assert m.shape == (120, 200)
    assert m[60, 100] == 255 and m[0, 0] == 0, "centro sólido, canto recortado"

    compose.make_shape_png(tmp_path / "s.png", 100, 60, "#FF4757", 0)
    s = cv2.imread(str(tmp_path / "s.png"), cv2.IMREAD_UNCHANGED)
    assert s.shape == (60, 100, 4)
    assert tuple(s[30, 50][:3]) == (0x57, 0x47, 0xFF), "BGR da cor de preenchimento"

    _, pad = compose.make_shadow_png(tmp_path / "sh.png", 100, 60, 10, blur=12)
    sh = cv2.imread(str(tmp_path / "sh.png"), cv2.IMREAD_UNCHANGED)
    assert pad == 24 and sh.shape[0] == 60 + pad * 2

    compose.make_border_png(tmp_path / "b.png", 100, 60, 8, "#FFFFFF", 4)
    b = cv2.imread(str(tmp_path / "b.png"), cv2.IMREAD_UNCHANGED)
    assert b[30, 1][3] > 200 and b[30, 50][3] == 0, "anel opaco, miolo transparente"


def test_text_layers_ass_com_titulo_e_anim():
    lay = _lay_minimo()
    lay["layers"].append({"id": "t", "type": "text", "text": "{titulo} agora", "x": 60,
                          "y": 130, "w": 960, "font": "Montserrat", "size": 60,
                          "color": "#FFFFFF", "align": "center", "bold": True,
                          "anim": "slide_up", "start_s": 0, "end_s": None})
    ass = compose.text_layers_ass(lay, titulo="Meu corte", out_dur=20.0)
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    assert "Meu corte agora" in ass
    assert "\\an8\\pos(540,130)" in ass, "alinhamento central ancora no meio da caixa"
    assert "\\move(540,176,540,130,0,320)" in ass, "slide_up entra de baixo"
    assert "Montserrat" in ass
    assert compose.text_layers_ass(_lay_minimo(), titulo="x", out_dur=5) is None


def test_build_chains_golden_composicao(tmp_path):
    lay = {"version": 2, "canvas": {"w": 1080, "h": 1920},
           "background": {"type": "gradient", "color": "#1A2230", "color2": "#0A0D12",
                          "direction": "vertical"},
           "layers": [
               {"id": "src", "type": "source", "x": 90, "y": 300, "w": 900, "h": 1160,
                "radius": 36, "border_w": 6, "border_color": "#FFFFFF", "shadow": True},
               {"id": "sh", "type": "shape", "x": 0, "y": 96, "w": 1080, "h": 150,
                "fill": "#0A0D12B4", "radius": 0, "opacity": 1.0, "anim": "fade",
                "start_s": 1.0, "end_s": 8.0},
               {"id": "cap", "type": "captions", "x": 90, "y": 1540, "w": 900},
               {"id": "t", "type": "text", "text": "Oi", "x": 60, "y": 100, "w": 960}]}
    comp = compose.plan_composition(lay, scale=1.0, out_dur=20.0, workdir=tmp_path,
                                    titulo="T")
    keys = [f["key"] for f in comp["files"]]
    assert "L0mask" in keys and "L0shadow" in keys and "L0border" in keys and "L1" in keys
    idx = {k: 3 + i for i, k in enumerate(keys)}
    chains, v = compose.build_chains(lay, comp, scale=1.0, out_dur=20.0,
                                     base_label="vbase", bg_src_label=None, idx=idx,
                                     subs_file="subs.ass", text_ass_file="layout.ass",
                                     fonts_dir="fonts", fps=30.0)
    g = ";".join(chains)
    assert "gradients=s=1080x1920:c0=0x1A2230:c1=0x0A0D12" in g and "fps=30" in g
    assert "alphamerge" in g, "cantos arredondados via máscara"
    assert "overlay=90:300" in g, "vídeo na caixa do layout"
    # forma com timing + animação de fade
    assert "fade=t=in:st=1.000:d=0.350:alpha=1" in g
    assert ":enable='between(t\\,1.000\\,8.000)'" in g
    # legendas aplicadas NA POSIÇÃO da camada captions (antes do texto, que vem depois)
    assert g.index("ass=subs.ass") < g.index("ass=layout.ass")
    assert g.rstrip().endswith("[vcanvas]") and v == "vcanvas"


def test_build_chains_fundo_blur_usa_o_video_do_corte(tmp_path):
    lay = _lay_minimo(background={"type": "blur", "blur_sigma": 30})
    comp = compose.plan_composition(lay, scale=0.5, out_dur=10.0, workdir=tmp_path,
                                    titulo="")
    chains, _ = compose.build_chains(lay, comp, scale=0.5, out_dur=10.0,
                                     base_label="vmain", bg_src_label="vbgsrc",
                                     idx={}, subs_file=None, text_ass_file=None,
                                     fonts_dir=None, fps=30.0)
    g = ";".join(chains)
    assert "[vbgsrc]scale=540:960:force_original_aspect_ratio=increase" in g
    assert "gblur=sigma=30" in g


# ---------------------------------------------------------------- API


def test_templates_e_layout_efetivo(client, auth):
    r = client.get("/api/v1/brand-kits/templates", headers=auth)
    assert r.status_code == 200
    nomes = [t["id"] for t in r.json()["templates"]]
    assert "moldura" in nomes and "tela_cheia" in nomes

    kit = client.post("/api/v1/brand-kits", json={"name": "Legado"}, headers=auth).json()
    r = client.get(f"/api/v1/brand-kits/{kit['id']}/layout/effective", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["persisted"] is False, "kit legado → layout convertido para edição"
    assert [x["type"] for x in body["layout"]["layers"]][0] == "source"


def test_patch_layout_persiste_valida_e_reabre(client, auth):
    kit = client.post("/api/v1/brand-kits", json={"name": "Studio"}, headers=auth).json()
    lay = next(t for t in compose.TEMPLATES if t["id"] == "moldura")["layout"]
    r = client.patch(f"/api/v1/brand-kits/{kit['id']}", json={"layout": lay}, headers=auth)
    assert r.status_code == 200
    assert r.json()["layout"]["layers"][0]["type"] == "source"

    # reabertura idêntica (persistência → reabertura)
    lista = client.get("/api/v1/brand-kits", headers=auth).json()
    salvo = next(k for k in lista if k["id"] == kit["id"])
    assert salvo["layout"] == lay
    eff = client.get(f"/api/v1/brand-kits/{kit['id']}/layout/effective", headers=auth).json()
    assert eff["persisted"] is True and eff["layout"] == lay

    # inválido → 422 com mensagem PT-BR
    r = client.patch(f"/api/v1/brand-kits/{kit['id']}",
                     json={"layout": {"layers": [{"type": "banana"}]}}, headers=auth)
    assert r.status_code == 422 and "Layout inválido" in r.json()["detail"]

    # null explícito remove (volta ao clássico)
    r = client.patch(f"/api/v1/brand-kits/{kit['id']}", json={"layout": None}, headers=auth)
    assert r.status_code == 200 and r.json()["layout"] is None


def test_mudanca_de_kit_invalida_previas_dos_cortes(client, auth):
    from app import config
    from app.db.base import session
    from app.db.models import CutCandidate, Project, Render, SourceVideo

    kit = client.post("/api/v1/brand-kits", json={"name": "K"}, headers=auth).json()
    with session() as s:
        p = Project(name="P")
        s.add(p)
        s.flush()
        src = SourceVideo(project_id=p.id, origin="file", file_path="/v.mp4",
                          duration_s=60, status="ready")
        s.add(src)
        s.flush()
        c = CutCandidate(source_video_id=src.id, project_id=p.id, start_s=1, end_s=20,
                         score=70, title="C", brand_kit_id=kit["id"])
        s.add(c)
        s.flush()
        s.add(Render(cut_id=c.id, kind="preview", status="done", progress=1.0))
        cut_id = c.id
    prev = config.data_dir() / "media" / "previews" / f"{cut_id}.mp4"
    prev.parent.mkdir(parents=True, exist_ok=True)
    prev.write_bytes(b"x")

    lay = next(t for t in compose.TEMPLATES if t["id"] == "tela_cheia")["layout"]
    r = client.patch(f"/api/v1/brand-kits/{kit['id']}", json={"layout": lay}, headers=auth)
    assert r.status_code == 200
    assert not prev.exists(), "mudar o layout do kit derruba prévias dos cortes que o usam"

    # PATCH sem mudança visual (nome) não derruba
    prev.write_bytes(b"x")
    client.patch(f"/api/v1/brand-kits/{kit['id']}", json={"name": "K2"}, headers=auth)
    assert prev.exists()


def test_upload_asset_de_camada(client, auth):
    import io

    kit = client.post("/api/v1/brand-kits", json={"name": "A"}, headers=auth).json()
    png = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    r = client.post(f"/api/v1/brand-kits/{kit['id']}/assets",
                    files={"file": ("dec.png", io.BytesIO(png), "image/png")}, headers=auth)
    assert r.status_code == 200
    caminho = r.json()["path"]
    assert Path(caminho).exists() and caminho.endswith(".png")
    r = client.post(f"/api/v1/brand-kits/{kit['id']}/assets",
                    files={"file": ("x.gif", io.BytesIO(b"GIF89a"), "image/gif")},
                    headers=auth)
    assert r.status_code == 422


# ---------------------------------------------------------------- e2e render


@pytest.mark.e2e
def test_render_real_com_layout_moldura(client, auth):
    """canvas → persistência → render final → verificação por pixels.

    Fundo vermelho sólido + vídeo em caixa central: os cantos do quadro DEVEM
    ser vermelhos (fundo aparente) e o centro não."""
    from .conftest import wait_job
    from .fixtures import make_media

    if not make_media.have_espeak():
        pytest.skip("espeak-ng indisponível")
    video = make_media.fixture_video("fixture_30s.mp4", duration=30.0)

    from app.db.base import session
    from app.db.models import CutCandidate, Project, SourceVideo

    lay = {"version": 2, "canvas": {"w": 1080, "h": 1920},
           "background": {"type": "color", "color": "#C81E1E"},
           "layers": [
               {"id": "src", "type": "source", "x": 140, "y": 420, "w": 800, "h": 1000,
                "radius": 40, "border_w": 0, "shadow": False, "opacity": 1.0},
               {"id": "tit", "type": "text", "text": "{titulo}", "x": 60, "y": 150,
                "w": 960, "font": "Montserrat", "size": 64, "color": "#FFFFFF",
                "align": "center", "bold": True, "anim": "none", "start_s": 0,
                "end_s": None},
               {"id": "cap", "type": "captions", "x": 90, "y": 1560, "w": 900}]}
    kit = client.post("/api/v1/brand-kits", json={"name": "Moldura e2e", "layout": lay},
                      headers=auth).json()

    with session() as s:
        p = Project(name="F3 e2e")
        s.add(p)
        s.flush()
        src = SourceVideo(project_id=p.id, origin="file", file_path=str(video),
                          duration_s=30.0, width=1920, height=1080, fps=30.0,
                          status="ready")
        s.add(src)
        s.flush()
        c = CutCandidate(
            source_video_id=src.id, project_id=p.id, start_s=2.0, end_s=12.0, score=90.0,
            title="Corte com layout", brand_kit_id=kit["id"],
            crop_plan={"mode": "crop", "crop_w": 606, "crop_h": 1080,
                       "segments": [{"start": 2.0, "end": 12.0, "x0": 200, "x1": 200}]})
        s.add(c)
        s.flush()
        cut_id = c.id

    resp = client.post("/api/v1/renders",
                       json={"cut_id": cut_id, "kind": "final",
                             "overrides": {"video_preset": "ultrafast", "crf": 30}},
                       headers=auth)
    job = wait_job(client, auth, resp.json()["job_id"], timeout=300)
    assert job["status"] == "done", job

    import sqlalchemy as sa

    from app.db.base import session as sess
    from app.db.models import Render

    with sess() as s:
        rr = s.execute(sa.select(Render).where(Render.cut_id == cut_id)).scalars().first()
        out = Path(rr.output_path)
    assert out.exists()

    from app.services import ffmpeg as ff

    meta = ff.probe(out)
    assert meta["width"] == 1080 and meta["height"] == 1920 and meta["has_audio"]
    assert abs(meta["duration_s"] - 10.0) < 0.5

    import subprocess

    import cv2

    frame_png = out.parent / "f3_frame.png"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-ss", "4", "-i", str(out), "-frames:v", "1", str(frame_png)],
                   check=True, capture_output=True)
    img = cv2.imread(str(frame_png))  # BGR
    assert img is not None and img.shape[:2] == (1920, 1080)
    canto = img[30, 30].astype(int)
    assert canto[2] > 140 and canto[0] < 80, f"canto deve ser o fundo vermelho, veio {canto}"
    centro = img[900, 540].astype(int)
    assert not (centro[2] > 140 and centro[0] < 80 and centro[1] < 60), \
        "centro deve mostrar o vídeo, não o fundo"
    # título branco queimado na faixa superior
    topo = cv2.cvtColor(img[120:260, 100:980], cv2.COLOR_BGR2GRAY)
    assert float(np.percentile(topo, 99.5)) > 170, "texto do título deve aparecer no topo"
    frame_png.unlink(missing_ok=True)
