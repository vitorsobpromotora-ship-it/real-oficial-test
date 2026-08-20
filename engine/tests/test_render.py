from __future__ import annotations

from app.pipeline.render import _fades_de_juncao, build_filtergraph, slugify


def _graph(**kw):
    base = dict(crop_plan={"mode": "crop", "crop_w": 606, "crop_h": 1080,
                           "segments": [{"start": 0.0, "end": 10.0, "x0": 100, "x1": 100}]},
                duration=10.0, out_w=1080, out_h=1920, subs_file=None, fonts_dir=None,
                censor_intervals=[], censor_mode="beep", logo=None,
                beep_input_index=None, logo_input_index=None)
    base.update(kw)
    return build_filtergraph(**base)


def test_filtergraph_crop_estatico_simples():
    graph, v, a = _graph(subs_file="subs.ass")
    assert "crop=606:1080:100:0" in graph
    assert "scale=1080:1920:flags=lanczos" in graph
    assert "ass=subs.ass" in graph
    assert "loudnorm=I=-14:TP=-1.5:LRA=11" in graph
    assert v == "[vsub]" and a == "[aout]"
    assert "split" not in graph, "segmento único estático não precisa de split/concat"


def test_filtergraph_multisegmento_com_drift():
    plan = {"mode": "crop", "crop_w": 606, "crop_h": 1080, "segments": [
        {"start": 0.0, "end": 4.0, "x0": 100, "x1": 100},
        {"start": 4.0, "end": 10.0, "x0": 800, "x1": 900},
    ]}
    graph, v, a = _graph(crop_plan=plan)
    assert "[0:v]split=2[s0][s1]" in graph
    assert "trim=0.000:4.000,setpts=PTS-STARTPTS,crop=606:1080:100:0" in graph
    assert "crop=606:1080:800+(900-800)*(t/6.000):0" in graph
    assert "concat=n=2:v=1:a=0" in graph
    assert "," not in graph.split("crop=606:1080:800")[1].split(":0")[0], \
        "expressão de x não pode conter vírgulas (parser do filtergraph)"


def test_filtergraph_blur_pad():
    graph, v, a = _graph(crop_plan={"mode": "blur_pad", "segments": []})
    assert "force_original_aspect_ratio=increase" in graph
    assert "gblur=sigma=28" in graph
    assert "overlay=(W-w)/2:(H-h)/2" in graph


def test_filtergraph_censura_beep_e_logo():
    graph, v, a = _graph(
        censor_intervals=[{"start": 1.0, "end": 1.5}, {"start": 3.0, "end": 3.4}],
        censor_mode="beep", beep_input_index=2,
        logo={"position": "tr", "opacity": 0.8}, logo_input_index=1)
    assert "volume=enable='between(t\\,1.000\\,1.500)+between(t\\,3.000\\,3.400)':volume=0" in graph
    assert "[2:a]volume=0.35" in graph and "amix=inputs=2" in graph
    assert "[1:v]scale=194:-1,format=rgba,colorchannelmixer=aa=0.80[logo]" in graph
    assert "overlay=W-w-48:96[vlogo]" in graph
    assert v == "[vlogo]"


def test_filtergraph_censura_mute_sem_beep():
    graph, _, a = _graph(censor_intervals=[{"start": 1.0, "end": 1.5}], censor_mode="mute")
    assert "amix" not in graph
    assert "volume=enable='between(t\\,1.000\\,1.500)':volume=0[amute]" in graph
    assert a == "[aout]"


def test_filtergraph_edl_audio_por_segmentos():
    """EDL com 2 segmentos: áudio segue a MESMA seleção (asplit/atrim/concat),
    com fades de junção, antes de censura e loudnorm."""
    graph, _, a = _graph(
        audio_chunks=[{"start": 0.0, "end": 6.0, "fade_out": 0.12},
                      {"start": 10.0, "end": 16.0, "fade_in": 0.12}],
        censor_intervals=[{"start": 1.0, "end": 1.5}], censor_mode="mute", duration=12.0)
    assert "[0:a]asplit=2[aa0][aa1]" in graph
    assert "atrim=0.000:6.000,asetpts=PTS-STARTPTS,afade=t=out:st=5.880:d=0.120[ac0]" in graph
    assert "atrim=10.000:16.000,asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.120[ac1]" in graph
    assert "[ac0][ac1]concat=n=2:v=0:a=1[acat]" in graph
    assert "[acat]volume=enable=" in graph, "censura deve agir DEPOIS da seleção EDL"
    assert graph.index("concat=n=2:v=0:a=1") < graph.index("loudnorm")
    assert a == "[aout]"


def test_filtergraph_edl_video_fades_e_fx_de_audio():
    plan = {"mode": "crop", "crop_w": 606, "crop_h": 1080, "segments": [
        {"start": 0.0, "end": 6.0, "x0": 100, "x1": 100, "fade_out": 0.2},
        {"start": 10.0, "end": 16.0, "x0": 100, "x1": 100, "fade_in": 0.2},
    ]}
    graph, v, _ = _graph(crop_plan=plan, duration=12.0,
                         video_fades={"fade_in_s": 0.5, "fade_out_s": 0.8},
                         audio_fx={"gain_db": 3.0, "fade_in_s": 0.3, "fade_out_s": 0.0})
    # trims em tempo do INPUT + fades de junção por pedaço
    assert "trim=0.000:6.000,setpts=PTS-STARTPTS,crop=606:1080:100:0," \
           "fade=t=out:st=5.800:d=0.200[c0]" in graph
    assert "trim=10.000:16.000,setpts=PTS-STARTPTS,crop=606:1080:100:0," \
           "fade=t=in:st=0:d=0.200[c1]" in graph
    # fades globais aplicados por último no vídeo (composição inteira escurece)
    assert "fade=t=in:st=0:d=0.500,fade=t=out:st=11.200:d=0.800[vfade]" in graph
    assert v == "[vfade]"
    assert "volume=+3.0dB[again]" in graph
    assert "afade=t=in:st=0:d=0.300[afades]" in graph


def test_filtergraph_edl_mute_silencia_tudo():
    graph, _, _ = _graph(audio_fx={"mute": True, "gain_db": 5.0, "fade_in_s": 1.0})
    assert "volume=0[amuteall]" in graph
    assert "again" not in graph and "afades" not in graph, "mute ignora ganho e fades"
    assert "[amuteall]loudnorm" in graph


def test_filtergraph_blur_pad_com_trims_da_edl():
    graph, _, _ = _graph(
        crop_plan={"mode": "blur_pad", "segments": []},
        video_trims=[{"start": 0.0, "end": 5.0}, {"start": 8.0, "end": 13.0}])
    assert "[0:v]split=2[bt0][bt1]" in graph
    assert "[bt0]trim=0.000:5.000,setpts=PTS-STARTPTS[bc0]" in graph
    assert "[bc0][bc1]concat=n=2:v=1:a=0[vcut]" in graph
    assert "[vcut]split=2[bgsrc][fgsrc]" in graph, "blur_pad deve compor SOBRE o corte da EDL"
    assert "gblur=sigma=28" in graph


def test_fades_de_juncao_apenas_entre_segmentos_da_edl():
    pieces = [{"start": 0.0, "end": 4.0, "edl_seg": 0},
              {"start": 4.0, "end": 6.0, "edl_seg": 0},   # emenda interna do crop: sem fade
              {"start": 6.0, "end": 6.1, "edl_seg": 1}]   # pedaço curtíssimo: fade limitado
    _fades_de_juncao(pieces, 0.25)
    assert "fade_out" not in pieces[0] and "fade_in" not in pieces[1]
    assert pieces[1]["fade_out"] == 0.25
    assert pieces[2].get("fade_in", 0) == 0.05, "fade não pode passar de metade do pedaço"
    sem = [dict(p) for p in pieces]
    _fades_de_juncao(sem, 0.0)  # transição 0 = corte seco: não marca nada novo


def test_slugify():
    assert slugify("O Maior Erro da Minha Vida!") == "o-maior-erro-da-minha-vida"
    assert slugify("Ação & Emoção — épico") == "acao-emocao-epico"
    assert slugify("") == "corte"


def test_patch_visual_invalida_previa(client, auth):
    """E4: editar legenda/kit/enquadramento derruba a prévia antiga (registro + arquivo);
    edições não-visuais (status) preservam a prévia existente."""
    from app import config
    from app.db.base import session
    from app.db.models import CutCandidate, Project, Render, SourceVideo

    with session() as s:
        p = Project(name="Prévias")
        s.add(p)
        s.flush()
        src = SourceVideo(project_id=p.id, origin="file", file_path="/x.mp4",
                          duration_s=60.0, status="ready")
        s.add(src)
        s.flush()
        c = CutCandidate(source_video_id=src.id, project_id=p.id, start_s=5.0, end_s=25.0,
                         score=80.0, title="Corte")
        s.add(c)
        s.flush()
        r = Render(cut_id=c.id, kind="preview", status="done", progress=1.0)
        s.add(r)
        s.flush()
        cut_id, render_id = c.id, r.id

    prev_file = config.data_dir() / "media" / "previews" / f"{cut_id}.mp4"
    prev_file.parent.mkdir(parents=True, exist_ok=True)
    prev_file.write_bytes(b"fake-mp4")

    resp = client.patch(f"/api/v1/cuts/{cut_id}", json={"status": "approved"}, headers=auth)
    assert resp.status_code == 200
    assert prev_file.exists(), "mudança de status não deve invalidar a prévia"

    resp = client.patch(f"/api/v1/cuts/{cut_id}",
                        json={"caption_style": {"preset": "clean"}}, headers=auth)
    assert resp.status_code == 200
    assert not prev_file.exists(), "mudança visual deve apagar o arquivo da prévia"
    with session() as s:
        assert s.get(Render, render_id) is None, "registro da prévia deve ser removido"

    resp = client.patch(f"/api/v1/cuts/{cut_id}", json={"framing": "left"}, headers=auth)
    assert resp.status_code == 200
    assert resp.json()["edits"]["framing"] == "left", "framing deve persistir em edits"
    resp = client.patch(f"/api/v1/cuts/{cut_id}", json={"framing": "auto"}, headers=auth)
    assert "framing" not in (resp.json()["edits"] or {}), "auto remove o override"

    # null explícito LIMPA o campo (selecionar "(nenhum)" no kit precisa ter efeito real)
    kit = client.post("/api/v1/brand-kits", json={"name": "Kit X"}, headers=auth).json()
    resp = client.patch(f"/api/v1/cuts/{cut_id}", json={"brand_kit_id": kit["id"]}, headers=auth)
    assert resp.json()["brand_kit_id"] == kit["id"]
    resp = client.patch(f"/api/v1/cuts/{cut_id}", json={"brand_kit_id": None}, headers=auth)
    assert resp.json()["brand_kit_id"] is None, "null explícito deve remover o kit"

    # reenviar o MESMO valor visual não derruba a prévia existente
    prev_file.write_bytes(b"fake-mp4")
    resp = client.patch(f"/api/v1/cuts/{cut_id}",
                        json={"caption_style": {"preset": "clean"}, "status": "approved"},
                        headers=auth)
    assert resp.status_code == 200
    assert prev_file.exists(), "valores visuais inalterados devem preservar a prévia"
