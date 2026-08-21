"""Ponto 50 — o fluxo completo da versão, ponta a ponta, sem editor externo.

Importar → receber cortes → abrir pendente → título/descrição → Editor (trim,
pausas, áudio, enquadramento por trecho, punch-in, palavras, ênfase, estilo,
cor, posição, kit) → salvar → reabrir idêntico → aprovar → sair de "Para
revisar" → renderizar → editar de novo → sistema detectar render desatualizado
→ renderizar nova versão.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pytest

from app.schemas.claude import PARAM_KEYS
from app.services import ffmpeg

from .conftest import wait_job
from .fixtures import make_media
from .test_ingest_transcribe import _FakeWhisper

pytestmark = pytest.mark.e2e


def _raw(start, end, nota, title):
    return {"start_s": start, "end_s": end, "params": dict.fromkeys(PARAM_KEYS, nota),
            "hook_line": f"Gancho de {title}", "title": title,
            "hashtags": ["#corte"], "reason": "fluxo v3", "origin": "claude"}


def _frame(video: Path, t: float, tmp: Path) -> np.ndarray:
    png = tmp / f"f{int(t * 1000)}.png"
    subprocess.run([ffmpeg.find_binary("ffmpeg"), "-hide_banner", "-loglevel", "error",
                    "-y", "-ss", f"{t}", "-i", str(video), "-frames:v", "1", str(png)],
                   check=True, capture_output=True)
    from PIL import Image  # noqa: PLC0415

    return np.asarray(Image.open(png).convert("RGB"), dtype=np.int16)


def test_fluxo_completo_da_versao(client, auth, monkeypatch, tmp_path):
    if not make_media.have_espeak():
        pytest.skip("espeak-ng indisponível")

    # 1–2. importar vídeo e receber cortes
    video = make_media.fixture_video("fixture_90s.mp4", duration=90.0)
    monkeypatch.setattr("app.pipeline.transcribe.get_model", lambda size: _FakeWhisper())
    monkeypatch.setattr(
        "app.pipeline.analyze.analyze_semantic",
        lambda ctx, sid, sentences, features, duration, report, **kw: ([
            _raw(4.0, 26.0, 8.5, "Corte principal"),
            _raw(40.0, 62.0, 7.0, "Segundo corte"),
        ], {"agent": "local", "model": "", "chunks": 1, "ia_ok": 0, "erro": None}))

    pid = client.post("/api/v1/projects", json={"name": "Fluxo v3"},
                      headers=auth).json()["id"]
    kit_id = client.post("/api/v1/brand-kits",
                         json={"name": "Kit v3", "primary_color": "#FFFFFF",
                               "secondary_color": "#00E5FF"},
                         headers=auth).json()["id"]
    r = client.post(f"/api/v1/projects/{pid}/sources",
                    json={"origin": "file", "file_path": str(video), "auto_process": True},
                    headers=auth)
    assert wait_job(client, auth, r.json()["job_id"], timeout=300)["status"] == "done"

    # 3. abrir um corte pendente
    pendentes = client.get(f"/api/v1/projects/{pid}/cuts?status=pending_review",
                           headers=auth).json()
    assert len(pendentes) >= 1
    cut = pendentes[0]
    cid = cut["id"]
    assert cut["render_state"] == "not_rendered" and not cut["render_outdated"]

    # 4–5. assistir/ler análise → 6–7. título e descrição
    assert client.get(f"/api/v1/cuts/{cid}/caption-cards", headers=auth).status_code == 200
    client.patch(f"/api/v1/cuts/{cid}",
                 json={"title": "O melhor momento", "description": "Descrição p/ publicar"},
                 headers=auth)

    # 8–10. Editor: relógio relativo começa em 0 (a EDL guarda os tempos da fonte)
    cards = client.get(f"/api/v1/cuts/{cid}/caption-cards", headers=auth).json()
    assert cards["cards"], "o corte precisa ter legendas para editar"
    assert cards["cards"][0]["start"] >= 0

    # 11–13. ajustar início/fim e remover uma pausa (jump cut) → EDL de 2 trechos
    a, b = cut["start_s"] + 1.0, cut["end_s"] - 1.0
    meio = (a + b) / 2
    edl = {"version": 1, "segments": [{"src_start": a, "src_end": meio - 1.0},
                                      {"src_start": meio + 0.5, "src_end": b}],
           "fade_in_s": 0.3, "fade_out_s": 0.3, "transition_s": 0.12,
           "audio": {"gain_db": -3.0, "mute": False,        # 14. áudio
                     "fade_in_s": 0.2, "fade_out_s": 0.2}}

    palavras = client.get(f"/api/v1/cuts/{cid}/words?pad_s=0", headers=auth).json()["words"]
    assert len(palavras) >= 4, "fixture precisa de palavras para as etapas 17–21"
    p0, p1, p2 = palavras[0]["idx"], palavras[1]["idx"], palavras[2]["idx"]

    edits = {
        # 15. override de enquadramento por trecho + 16. punch-in
        "framing_segments": [{"start_s": a + 1.0, "end_s": a + 5.0, "mode": "left"}],
        "punch_in": "leve",
        # 17–20. corrigir, excluir, inserir antes e depois
        "word_overrides": {str(p0): "OLHA"},
        "word_deleted": [p1],
        "word_inserted": [
            {"id": "ins1", "anchor_idx": p2, "placement": "before", "text": "REALMENTE"},
            {"id": "ins2", "anchor_idx": p2, "placement": "after", "text": "AGORA"},
        ],
        # 21. ênfase
        "word_emphasis": [{"idx": [p2], "effect": "fatality", "intensity": "forte",
                           "color": "#FF2D2D"}],
    }
    # 22–24. estilo da família Palavra Pop, cor e posição arrastada
    caption_style = {"preset": "pp_bold", "highlight_color": "#00FF88",
                     "pos_x": 0.5, "pos_y": 0.34, "max_width_pct": 82}

    # 25–26. aplicar kit e salvar tudo de uma vez (é o que o Editor faz)
    salvo = client.patch(f"/api/v1/cuts/{cid}",
                         json={"edl": edl, "edits": edits, "caption_style": caption_style,
                               "framing": "auto", "punch_in": "leve",
                               "brand_kit_id": kit_id},
                         headers=auth)
    assert salvo.status_code == 200, salvo.text
    rev_apos_edicao = salvo.json()["edit_revision"]

    # 27. reabrir: idêntico ao salvo
    reaberto = client.get(f"/api/v1/cuts/{cid}", headers=auth).json()
    assert reaberto["edl"]["segments"] == [
        {"src_start": round(a, 3), "src_end": round(meio - 1.0, 3)},
        {"src_start": round(meio + 0.5, 3), "src_end": round(b, 3)}]
    assert reaberto["edl"]["audio"]["gain_db"] == -3.0
    assert reaberto["edits"]["word_emphasis"][0]["effect"] == "fatality"
    assert reaberto["edits"]["word_inserted"][0]["text"] == "REALMENTE"
    assert reaberto["caption_style"]["preset"] == "pp_bold"
    assert reaberto["brand_kit_id"] == kit_id
    assert reaberto["description"] == "Descrição p/ publicar"

    cards2 = client.get(f"/api/v1/cuts/{cid}/caption-cards", headers=auth).json()
    textos = [w["word"] for c in cards2["cards"] for w in c["words"]]
    assert "OLHA" in textos and "REALMENTE" in textos and "AGORA" in textos
    assert cards2["style"]["preset"] == "pp_bold" if "preset" in cards2["style"] else True
    enf = [w for c in cards2["cards"] for w in c["words"] if w.get("emphasis")]
    assert enf and enf[0]["emphasis"]["effect"] == "fatality"

    # 28–30. aprovar → sai de Para revisar, entra em Aprovados
    client.patch(f"/api/v1/cuts/{cid}", json={"status": "approved"}, headers=auth)
    ids_pend = [c["id"] for c in client.get(
        f"/api/v1/projects/{pid}/cuts?status=pending_review", headers=auth).json()]
    ids_aprov = [c["id"] for c in client.get(
        f"/api/v1/projects/{pid}/cuts?status=approved", headers=auth).json()]
    assert cid not in ids_pend and cid in ids_aprov

    # 31–32. renderizar pela tela de análise e conferir o arquivo
    render = client.post("/api/v1/renders", json={"cut_id": cid}, headers=auth).json()
    assert wait_job(client, auth, render["job_id"], timeout=600)["status"] == "done"
    saida = Path(client.get(f"/api/v1/renders/{render['id']}", headers=auth)
                 .json()["output_path"])
    assert saida.exists()
    probe = ffmpeg.probe(str(saida))
    assert (probe["width"], probe["height"]) == (1080, 1920)
    dur_esperada = (meio - 1.0 - a) + (b - (meio + 0.5))
    assert abs(probe["duration_s"] - dur_esperada) < 0.6

    fr = _frame(saida, dur_esperada * 0.35, tmp_path)

    estado = client.get(f"/api/v1/cuts/{cid}", headers=auth).json()
    assert estado["render_state"] == "rendered" and not estado["render_outdated"]

    # 33–35. voltar ao Editor, alterar → o render anterior fica desatualizado
    client.patch(f"/api/v1/cuts/{cid}",
                 json={"caption_style": {**caption_style, "pos_y": 0.6}}, headers=auth)
    estado = client.get(f"/api/v1/cuts/{cid}", headers=auth).json()
    assert estado["edit_revision"] > rev_apos_edicao
    assert estado["render_state"] == "rendered"
    assert estado["render_outdated"] is True, "o sistema tem de avisar que está velho"

    # 36. renderizar a nova versão → volta a estar em dia
    r2 = client.post("/api/v1/renders", json={"cut_id": cid}, headers=auth).json()
    assert wait_job(client, auth, r2["job_id"], timeout=600)["status"] == "done"
    final = client.get(f"/api/v1/cuts/{cid}", headers=auth).json()
    assert final["render_outdated"] is False
    assert final["latest_render_id"] == r2["id"]

    # e a nova posição realmente mudou o ARQUIVO: comparando os dois renders no
    # mesmo instante, a legenda saiu de cima (0.34) e apareceu embaixo (0.6)
    saida2 = Path(client.get(f"/api/v1/renders/{r2['id']}", headers=auth)
                  .json()["output_path"])
    fr2 = _frame(saida2, dur_esperada * 0.35, tmp_path)
    a_cinza, b_cinza = fr.mean(axis=2), fr2.mean(axis=2)
    saiu = ((a_cinza > 170) & (b_cinza < 120)).sum(axis=1)   # tinha legenda, não tem mais
    chegou = ((b_cinza > 170) & (a_cinza < 120)).sum(axis=1)  # não tinha, agora tem
    assert saiu.sum() > 500 and chegou.sum() > 500, "os dois renders deveriam diferir"
    linha_antes = float(np.average(np.arange(len(saiu)), weights=saiu))
    linha_depois = float(np.average(np.arange(len(chegou)), weights=chegou))
    assert linha_depois > linha_antes + 200, \
        f"a legenda deveria ter descido: {linha_antes:.0f} → {linha_depois:.0f}"
    assert linha_antes < 1920 * 0.5 < linha_depois, \
        f"posições fora do esperado: {linha_antes:.0f} / {linha_depois:.0f}"
