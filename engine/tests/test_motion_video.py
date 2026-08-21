"""v4 FASE F — Video FX: compilação determinística e efeito REAL nos pixels.

Cada preset compila para expressões de filtergraph com t = tempo de SAÍDA;
aqui o ffmpeg roda de verdade e os frames provam: efeito presente DENTRO da
janela, vídeo intocado FORA dela, e duas execuções idênticas frame a frame.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pytest

from app.pipeline import motion_video as mv
from app.pipeline.render import build_filtergraph
from app.services import ffmpeg


def _fx(pid: str, start: float, end: float, seed: int = 7, **kw) -> dict:
    e = {"id": f"e_{pid}", "type": "video_fx", "preset": pid,
         "target": {"kind": "video"}, "start": start, "end": end,
         "intensity": "normal", "enabled": True, "seed": seed, "params": {}}
    e.update(kw)
    return e


def _man(*effects: dict) -> dict:
    return {"version": 1, "effects": list(effects)}


@pytest.fixture(scope="module")
def base(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("vfx")
    out = d / "base.mp4"
    subprocess.run(
        [ffmpeg.find_binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "testsrc2=s=270x480:r=30:d=3",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
         "-pix_fmt", "yuv420p", str(out)], check=True)
    return out


def _aplica(base: Path, man: dict, nome: str) -> Path:
    out = base.parent / f"{nome}.mp4"
    chains = mv.compile_video_fx(man, 270, 480)
    vf = ",".join(chains)
    subprocess.run(
        [ffmpeg.find_binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(base), "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "18", "-pix_fmt", "yuv420p", str(out)], check=True)
    return out


def _frame(video: Path, t: float) -> np.ndarray:
    png = video.parent / f"f_{video.stem}_{int(t * 1000)}.png"
    subprocess.run(
        [ffmpeg.find_binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
         "-ss", f"{t}", "-i", str(video), "-frames:v", "1", str(png)], check=True)
    from PIL import Image  # noqa: PLC0415

    return np.asarray(Image.open(png).convert("RGB"), dtype=np.int16)


def _framemd5(video: Path) -> str:
    r = subprocess.run(
        [ffmpeg.find_binary("ffmpeg"), "-hide_banner", "-loglevel", "error",
         "-i", str(video), "-f", "framemd5", "-"],
        capture_output=True, text=True, check=True)
    return "\n".join(li for li in r.stdout.splitlines() if not li.startswith("#"))


def _mse(a: np.ndarray, b: np.ndarray) -> float:
    d = a.astype(np.float64) - b.astype(np.float64)  # int16² estouraria
    return float(np.mean(d * d))


def test_compilacao_e_deterministica_e_a_seed_gera_variacao():
    man = _man(_fx("shake", 1.0, 1.5, seed=7))
    a = mv.compile_video_fx(man, 1080, 1920)
    b = mv.compile_video_fx(man, 1080, 1920)
    c = mv.compile_video_fx(_man(_fx("shake", 1.0, 1.5, seed=8)), 1080, 1920)
    assert a == b, "mesma seed → mesma cadeia, caractere a caractere"
    assert a != c, "'Nova variação' troca as fases do tremor"


def test_ordem_deterministica_e_formato_final():
    man = _man(_fx("darken", 2.0, 2.5), _fx("flash", 1.0, 1.2),
               _fx("grayscale_hit", 0.5, 0.8))
    chains = mv.compile_video_fx(man, 1080, 1920)
    assert len(chains) == 3
    assert chains[-1].endswith(",format=yuv420p"), "volta ao 4:2:0 no fim"
    # a ordem é a do manifest (que o motor normaliza por start) — estável
    assert chains == mv.compile_video_fx(man, 1080, 1920)


def test_presets_desconhecidos_e_desabilitados_sao_ignorados():
    man = _man(_fx("fx_do_futuro", 1.0, 2.0),
               _fx("darken", 1.0, 2.0, enabled=False))
    assert mv.compile_video_fx(man, 1080, 1920) == []
    assert mv.compile_video_fx(None, 1080, 1920) == []


def test_fx_entram_entre_a_base_e_as_legendas_no_filtergraph():
    plan = {"mode": "crop", "crop_w": 270, "crop_h": 480,
            "segments": [{"start": 0.0, "end": 3.0, "x0": 0, "x1": 0}]}
    graph, v, _a = build_filtergraph(
        crop_plan=plan, duration=3.0, out_w=270, out_h=480,
        subs_file="subs.ass", fonts_dir=None, censor_intervals=[],
        censor_mode="beep", logo=None, beep_input_index=None,
        logo_input_index=None,
        fx_chains=mv.compile_video_fx(_man(_fx("darken", 1.0, 2.0)), 270, 480))
    assert "[vbase]eq=brightness" in graph, "FX consome a base"
    assert "[vfx0]ass=subs.ass" in graph, "legendas queimam DEPOIS do FX (texto parado)"
    assert v == "[vsub]"


def test_render_real_efeito_dentro_da_janela_e_nada_fora(base):
    man = _man(_fx("grayscale_hit", 1.0, 1.5), _fx("flash", 2.0, 2.4),
               _fx("darken", 0.4, 0.7))
    out = _aplica(base, man, "cena")
    # FORA de todas as janelas: idêntico módulo encode
    assert _mse(_frame(base, 1.8), _frame(out, 1.8)) < 12.0  # só ruído de encode
    # grayscale: canais R≈G≈B dentro da janela
    f = _frame(out, 1.2).astype(np.float64)
    assert np.mean(np.abs(f[..., 0] - f[..., 1])) < 2.5, "sem cor na janela do P&B"
    fb = _frame(base, 1.2).astype(np.float64)
    assert np.mean(np.abs(fb[..., 0] - fb[..., 1])) > 8.0, "a base é colorida"
    # flash: bem mais claro no início da janela, decaído no fim
    assert _frame(out, 2.02).mean() > _frame(base, 2.02).mean() + 25
    assert abs(float(_frame(out, 2.38).mean()) - float(_frame(base, 2.38).mean())) < 6
    # darken: mais escuro na janela
    assert _frame(out, 0.55).mean() < _frame(base, 0.55).mean() - 12


def test_render_real_punch_zoom_amplia_e_volta(base):
    man = _man(_fx("punch_zoom", 1.0, 1.6))
    out = _aplica(base, man, "zoom")
    assert _mse(_frame(base, 0.5), _frame(out, 0.5)) < 12.0, "antes: intocado"
    assert _mse(_frame(base, 1.15), _frame(out, 1.15)) > 40.0, "no pico: ampliado"
    assert _mse(_frame(base, 2.2), _frame(out, 2.2)) < 12.0, "depois: intocado"


def test_render_real_shake_desloca_e_e_reproduzivel(base):
    man = _man(_fx("impact_shake", 1.0, 1.5, seed=42))
    a = _aplica(base, man, "shk_a")
    b = _aplica(base, man, "shk_b")
    assert _framemd5(a) == _framemd5(b), "dois renders = frames idênticos"
    assert _mse(_frame(base, 1.03), _frame(a, 1.03)) > 30.0, "pancada visível"
    assert _mse(_frame(base, 2.0), _frame(a, 2.0)) < 12.0, "fora: intocado"

    c = _aplica(base, _man(_fx("impact_shake", 1.0, 1.5, seed=43)), "shk_c")
    assert _framemd5(a) != _framemd5(c), "seed nova → movimento novo"


def test_rgb_split_e_blur_renderizam_na_janela(base):
    out = _aplica(base, _man(_fx("rgb_split", 1.0, 1.4),
                             _fx("blur_pulse", 2.0, 2.4)), "grb")
    f = _frame(out, 1.2)
    fb = _frame(base, 1.2)
    assert _mse(f, fb) > 25.0, "split visível"
    # blur reduz o detalhe (gradiente médio cai)
    g_out = np.abs(np.diff(_frame(out, 2.2).mean(axis=2), axis=1)).mean()
    g_base = np.abs(np.diff(_frame(base, 2.2).mean(axis=2), axis=1)).mean()
    # sigma escala com a resolução (aqui 270px → ~2.2): o detalhe cai e a
    # diferença com a base é substancial dentro da janela
    assert g_out < g_base, (g_out, g_base)
    assert _mse(_frame(out, 2.2), _frame(base, 2.2)) > 20.0


def test_video_props_batem_com_o_contrato_compartilhado():
    """Entrega 60 para FX de vídeo: o preview TS avalia AS MESMAS fórmulas —
    se um preset mudar, o contrato precisa ser regenerado."""
    import json
    from pathlib import Path

    cases = json.loads((Path(__file__).resolve().parents[2]
                        / "shared" / "motion-cases.json").read_text())
    vp = cases["video_props"]
    for pid, preset in vp["presets"].items():
        assert mv.VIDEO_PRESETS[pid] == preset, \
            f"preset '{pid}' divergiu do contrato — regenere shared/motion-cases.json"
    for c in vp["cases"]:
        got = mv.video_props_at(c["effect"], vp["presets"][c["preset"]], c["t"])
        for prop, v in c["props"].items():
            assert got[prop] == pytest.approx(v, abs=1e-12), \
                f"{c['preset']}@{c['t']}s {prop}"
