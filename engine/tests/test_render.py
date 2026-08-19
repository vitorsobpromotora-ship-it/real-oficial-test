from __future__ import annotations

from app.pipeline.render import _shift_plan, build_filtergraph, slugify


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


def test_shift_plan_cobre_o_clipe_inteiro():
    plan = {"mode": "crop", "crop_w": 606, "crop_h": 1080, "segments": [
        {"start": 10.0, "end": 14.0, "x0": 50, "x1": 50},
        {"start": 14.0, "end": 21.5, "x0": 700, "x1": 700},
    ]}
    rel = _shift_plan(plan, 10.0, 21.5)
    assert rel["segments"][0]["start"] == 0.0
    assert rel["segments"][-1]["end"] == 11.5
    for prev, nxt in zip(rel["segments"], rel["segments"][1:], strict=False):
        assert prev["end"] == nxt["start"], "segmentos devem ser contíguos"


def test_slugify():
    assert slugify("O Maior Erro da Minha Vida!") == "o-maior-erro-da-minha-vida"
    assert slugify("Ação & Emoção — épico") == "acao-emocao-epico"
    assert slugify("") == "corte"
