"""v4 FASE K — GOLDEN RENDER do Motion Engine (Entregas 128, 152–153).

A sequência de prova: um corte de ~15s carrega o manifest COMPLETO —
ênfases de texto, callout com fundo, Fatality COMPOSTA (texto+vídeo+cena),
FX de cena e b-roll da biblioteca — salvo pela API, REABERTO idêntico e
renderizado de verdade; frames em instantes-chave provam cada camada no MP4.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pytest

from app.pipeline import motion_composite
from app.schemas.claude import PARAM_KEYS
from app.services import ffmpeg

from .conftest import wait_job
from .fixtures import make_media
from .test_ingest_transcribe import _FakeWhisper

pytestmark = pytest.mark.e2e


def _frame(video: Path, t: float, tmp: Path) -> np.ndarray:
    png = tmp / f"g{int(t * 1000)}.png"
    subprocess.run([ffmpeg.find_binary("ffmpeg"), "-hide_banner", "-loglevel",
                    "error", "-y", "-ss", f"{t}", "-i", str(video),
                    "-frames:v", "1", str(png)], check=True, capture_output=True)
    from PIL import Image  # noqa: PLC0415

    return np.asarray(Image.open(png).convert("RGB"), dtype=np.int16)


def test_golden_render_motion_completo(client, auth, monkeypatch, tmp_path):
    if not make_media.have_espeak():
        pytest.skip("espeak-ng indisponível")

    video = make_media.fixture_video("fixture_90s.mp4", duration=90.0)
    monkeypatch.setattr("app.pipeline.transcribe.get_model",
                        lambda size: _FakeWhisper())
    monkeypatch.setattr(
        "app.pipeline.analyze.analyze_semantic",
        lambda ctx, sid, sentences, features, duration, report, **kw: ([
            {"start_s": 4.0, "end_s": 20.0,
             "params": dict.fromkeys(PARAM_KEYS, 8.5),
             "hook_line": "Golden", "title": "Golden Motion",
             "hashtags": [], "reason": "golden", "origin": "claude"}],
            {"agent": "local", "model": "", "chunks": 1, "ia_ok": 0, "erro": None}))

    pid = client.post("/api/v1/projects", json={"name": "Golden"},
                      headers=auth).json()["id"]
    r = client.post(f"/api/v1/projects/{pid}/sources",
                    json={"origin": "file", "file_path": str(video),
                          "auto_process": True}, headers=auth)
    assert wait_job(client, auth, r.json()["job_id"], timeout=300)["status"] == "done"
    cut = client.get(f"/api/v1/projects/{pid}/cuts?status=pending_review",
                     headers=auth).json()[0]
    cid = cut["id"]
    dur = cut["end_s"] - cut["start_s"]
    assert dur >= 14.0, "o corte de prova precisa de ~15s"

    # b-roll: imagem VERMELHA importada para a biblioteca do projeto
    png_verm = tmp_path / "verm.png"
    subprocess.run([ffmpeg.find_binary("ffmpeg"), "-hide_banner", "-loglevel",
                    "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=300x300",
                    "-frames:v", "1", str(png_verm)], check=True)
    media = client.post(f"/api/v1/projects/{pid}/media",
                        files={"file": ("verm.png", png_verm.read_bytes(),
                                        "image/png")}, headers=auth).json()

    palavras = client.get(f"/api/v1/cuts/{cid}/words?pad_s=0",
                          headers=auth).json()["words"]
    assert len(palavras) >= 6
    a0 = cut["start_s"]
    idx_enf = palavras[1]["idx"]
    idx_call = [w["idx"] for w in palavras[2:5]]
    idx_fat = palavras[5]["idx"]
    w_fat = palavras[5]

    # o manifest COMPLETO da sequência de prova (tempos de SAÍDA)
    efeitos: list[dict] = [
        {"id": "g_enf", "type": "text_emphasis", "preset": "punch",
         "target": {"kind": "words", "idx": [idx_enf]},
         "start": round(palavras[1]["start_s"] - a0, 2),
         "end": round(palavras[1]["end_s"] - a0 + 0.25, 2),
         "intensity": "forte", "enabled": True, "seed": 5},
        {"id": "g_fx", "type": "video_fx", "preset": "grayscale_hit",
         "target": {"kind": "video"}, "start": 3.4, "end": 4.2,
         "intensity": "normal", "enabled": True, "seed": 5},
        {"id": "g_call", "type": "text_callout", "preset": "battle_final",
         "target": {"kind": "words", "idx": idx_call},
         "start": 6.8, "end": 8.6, "intensity": "normal", "enabled": True,
         "seed": 5, "params": {"pos_y": 0.42}},
        {"id": "g_br", "type": "broll", "preset": "broll",
         "target": {"kind": "media", "media_id": media["id"]},
         "start": 9.4, "end": 10.6, "intensity": "normal", "enabled": True,
         "seed": 5, "params": {"mode": "overlay", "x": 0.5, "y": 0.12, "w": 0.5}},
        *motion_composite.expand_composite(
            "fatality_composta", t_hit=round(w_fat["start_s"] - a0, 2),
            dur_word=max(0.3, w_fat["end_s"] - w_fat["start_s"]),
            target={"kind": "words", "idx": [idx_fat]},
            intensity="forte", seed_base=99),
    ]
    r = client.patch(f"/api/v1/cuts/{cid}",
                     json={"motion": {"version": 1, "effects": efeitos}},
                     headers=auth)
    assert r.status_code == 200

    # REABERTURA (Entrega 152): o que foi salvo volta inteiro e normalizado
    reaberto = client.get(f"/api/v1/cuts/{cid}", headers=auth).json()
    ids = {e["id"] for e in reaberto["motion"]["effects"]}
    assert {"g_enf", "g_fx", "g_call", "g_br"} <= ids
    assert sum(1 for e in reaberto["motion"]["effects"]
               if e.get("group")) >= 5, "a composição veio em grupo"
    rev_antes = reaberto["edit_revision"]

    # RENDER real
    render = client.post("/api/v1/renders", json={"cut_id": cid},
                         headers=auth).json()
    assert wait_job(client, auth, render["job_id"], timeout=900)["status"] == "done"
    saida = Path(client.get(f"/api/v1/renders/{render['id']}",
                            headers=auth).json()["output_path"])
    assert saida.exists()
    info = ffmpeg.probe(str(saida))
    assert (info["width"], info["height"]) == (1080, 1920)
    assert abs(info["duration_s"] - dur) < 0.5

    t_fat = round(w_fat["start_s"] - a0, 2)

    # frames-prova por camada:
    calmo = _frame(saida, 2.0, tmp_path)
    # 1) FX de cena: preto e branco na janela (canais praticamente iguais)
    pb = _frame(saida, 3.8, tmp_path).astype(np.float64)
    assert np.mean(np.abs(pb[..., 0] - pb[..., 1])) < 3.0, "grayscale no MP4"
    assert np.mean(np.abs(calmo.astype(np.float64)[..., 0]
                          - calmo.astype(np.float64)[..., 1])) >= 0  # sanidade
    # 2) callout: fundo escurecido + pilha de texto no meio da tela
    call = _frame(saida, 7.6, tmp_path)
    assert call.mean() < calmo.mean() - 5, "cena escurece no takeover"
    faixa_call = call[700:900, :]
    assert int((faixa_call > 215).sum()) > 800, "texto do callout no centro-alto"
    # 3) b-roll: mancha vermelha na região do overlay
    br = _frame(saida, 10.0, tmp_path)
    reg = br[int(1920 * 0.12):int(1920 * 0.12) + 260, 300:780]
    assert float(reg[..., 0].mean()) - float(reg[..., 1].mean()) > 60, \
        "imagem vermelha da biblioteca sobre o corte"
    # 4) fatality composta: no hit a cena difere MUITO do frame calmo
    fat = _frame(saida, t_fat + 0.1, tmp_path)
    assert float(np.mean(np.abs(fat.astype(np.float64)
                                - calmo.astype(np.float64)))) > 8.0

    # ciclo de versão: renderizado na revisão atual; editar depois marca velho
    estado = client.get(f"/api/v1/cuts/{cid}", headers=auth).json()
    assert estado["render_state"] == "rendered"
    assert not estado["render_outdated"]
    client.patch(f"/api/v1/cuts/{cid}",
                 json={"motion": None}, headers=auth)
    estado = client.get(f"/api/v1/cuts/{cid}", headers=auth).json()
    assert estado["edit_revision"] == rev_antes + 1
    assert estado["render_outdated"] is True, \
        "remover o motion depois do render marca o MP4 como desatualizado"
