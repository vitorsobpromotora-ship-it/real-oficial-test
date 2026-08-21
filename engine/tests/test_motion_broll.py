"""v4 FASE H — B-roll: biblioteca do projeto e mídia sobre o corte.

Prova com ffmpeg real: overlay aparece SÓ na janela, tela cheia cobre o
quadro mantendo o ÁUDIO PRINCIPAL bit a bit (Entrega 121), mídia ausente
não derruba o render, e a API de biblioteca copia o arquivo para o data_dir.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pytest

from app.db.base import session
from app.db.models import Project
from app.pipeline import motion_broll
from app.pipeline.render import build_filtergraph
from app.services import ffmpeg


def _fx_broll(media_id: str, start=1.0, end=2.0, **params) -> dict:
    return {"id": "br1", "type": "broll", "preset": "broll",
            "target": {"kind": "media", "media_id": media_id},
            "start": start, "end": end, "intensity": "normal",
            "enabled": True, "seed": 1, "params": params}


@pytest.fixture(scope="module")
def midia(tmp_path_factory):
    d = tmp_path_factory.mktemp("broll")
    png = d / "verm.png"
    subprocess.run([ffmpeg.find_binary("ffmpeg"), "-hide_banner", "-loglevel",
                    "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=200x200",
                    "-frames:v", "1", str(png)], check=True)
    base = d / "base.mp4"
    subprocess.run([ffmpeg.find_binary("ffmpeg"), "-hide_banner", "-loglevel",
                    "error", "-y", "-f", "lavfi",
                    "-i", "testsrc2=s=270x480:r=30:d=3",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                    "-c:a", "aac", "-pix_fmt", "yuv420p", str(base)], check=True)
    return {"png": png, "base": base, "dir": d}


def _render(midia, efeito, nome: str) -> Path:
    """Renderiza pelo MESMO build_filtergraph do produto (com ou sem b-roll)."""
    plan = {"mode": "crop", "crop_w": 270, "crop_h": 480,
            "segments": [{"start": 0.0, "end": 3.0, "x0": 0, "x1": 0}]}
    parts = []
    args: list[str] = []
    if efeito is not None:
        dur = max(0.1, efeito["end"] - efeito["start"])
        media = {"path": str(midia["png"]), "kind": "image", "filename": "verm.png"}
        args = motion_broll.input_args(efeito, media, dur)
        parts = [motion_broll.chain(efeito, 1, 0, 270, 480, 30.0)]
    graph, v, a = build_filtergraph(
        crop_plan=plan, duration=3.0, out_w=270, out_h=480, subs_file=None,
        fonts_dir=None, censor_intervals=[], censor_mode="beep", logo=None,
        beep_input_index=None, logo_input_index=None, broll_parts=parts)
    out = midia["dir"] / f"{nome}.mp4"
    subprocess.run([ffmpeg.find_binary("ffmpeg"), "-hide_banner", "-loglevel",
                    "error", "-y", "-i", str(midia["base"]), *args,
                    "-filter_complex", graph, "-map", v, "-map", a,
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                    "-c:a", "aac", "-pix_fmt", "yuv420p", str(out)], check=True)
    return out


def _frame(video: Path, t: float) -> np.ndarray:
    png = video.parent / f"fr_{video.stem}_{int(t * 1000)}.png"
    subprocess.run([ffmpeg.find_binary("ffmpeg"), "-hide_banner", "-loglevel",
                    "error", "-y", "-ss", f"{t}", "-i", str(video),
                    "-frames:v", "1", str(png)], check=True)
    from PIL import Image  # noqa: PLC0415

    return np.asarray(Image.open(png).convert("RGB"), dtype=np.int16)


def _audio_md5(video: Path) -> str:
    r = subprocess.run([ffmpeg.find_binary("ffmpeg"), "-hide_banner", "-loglevel",
                        "error", "-i", str(video), "-map", "0:a", "-f", "md5", "-"],
                       capture_output=True, text=True, check=True)
    return r.stdout.strip()


def test_overlay_de_imagem_so_na_janela(midia):
    ef = _fx_broll("m1", 1.0, 2.0, mode="overlay", x=0.5, y=0.25, w=0.6)
    out = _render(midia, ef, "ov")
    sem = _render(midia, None, "sem_ov")
    dentro = _frame(out, 1.5)
    fora = _frame(out, 0.5)
    # região do overlay (y=0.25·480=120, w=160px centrada): vermelho dominante
    reg = dentro[125:195, 60:210]
    assert float(reg[..., 0].mean()) > 180 and float(reg[..., 1].mean()) < 90, \
        "imagem vermelha visível na janela"
    assert float(np.mean(np.abs(fora.astype(float)
                                - _frame(sem, 0.5).astype(float)))) < 3.0
    assert float(np.mean(np.abs(dentro.astype(float)
                                - _frame(sem, 1.5).astype(float)))) > 10.0


def test_fullscreen_cobre_o_quadro_e_o_audio_principal_continua(midia):
    """Entrega 121: b-roll em tela cheia troca a IMAGEM; o áudio é o do corte."""
    ef = _fx_broll("m1", 1.0, 2.0, mode="fullscreen")
    out = _render(midia, ef, "full")
    sem = _render(midia, None, "sem_full")
    f = _frame(out, 1.5)
    assert float(f[..., 0].mean()) > 200 and float(f[..., 1].mean()) < 60, \
        "tela inteira vermelha na janela"
    assert _audio_md5(out) == _audio_md5(sem), \
        "áudio com b-roll = áudio sem b-roll, bit a bit (nunca entra no áudio)"


def test_midia_ausente_e_pulada_sem_derrubar(midia):
    ef = _fx_broll("nao_existe")
    assert motion_broll.resolve_media(ef, {}) is None
    assert motion_broll.resolve_media(
        ef, {"nao_existe": {"path": "/nada/x.png", "kind": "image"}}) is None
    ok = motion_broll.resolve_media(
        _fx_broll("m1"), {"m1": {"path": str(midia["png"]), "kind": "image"}})
    assert ok and ok["path"] == str(midia["png"])


def test_api_biblioteca_upload_lista_exclui(client, auth, midia):
    with session() as s:
        p = Project(name="Broll")
        s.add(p)
        s.flush()
        pid = p.id
    conteudo = midia["png"].read_bytes()
    r = client.post(f"/api/v1/projects/{pid}/media",
                    files={"file": ("meu-broll.png", conteudo, "image/png")},
                    headers=auth)
    assert r.status_code == 201, r.text
    m = r.json()
    assert m["kind"] == "image" and m["filename"] == "meu-broll.png"

    lista = client.get(f"/api/v1/projects/{pid}/media", headers=auth).json()["media"]
    assert [x["id"] for x in lista] == [m["id"]]

    arq = client.get(f"/api/v1/media/broll/{m['id']}", headers=auth)
    assert arq.status_code == 200 and arq.content == conteudo, \
        "arquivo COPIADO para o data_dir e servido por id"

    r = client.delete(f"/api/v1/projects/{pid}/media/{m['id']}", headers=auth)
    assert r.json()["ok"]
    assert client.get(f"/api/v1/projects/{pid}/media",
                      headers=auth).json()["media"] == []
    assert client.get(f"/api/v1/media/broll/{m['id']}", headers=auth).status_code == 404


def test_migracao_v7_cria_a_tabela(client, auth):
    from app.db.base import get_engine
    from app.db.migrate import _m7_project_media

    with get_engine().connect() as conn:
        _m7_project_media(conn)  # idempotente (IF NOT EXISTS)
        conn.commit()
