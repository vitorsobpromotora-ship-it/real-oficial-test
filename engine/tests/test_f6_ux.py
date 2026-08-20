"""F6/§5 — remoção de pausas (EDL não destrutiva), métricas de edição e
perfil editorial transparente."""

from __future__ import annotations

from app.pipeline import pauses
from app.reports.metrics import editorial_profile


def _w(a, b, txt="palavra"):
    return {"start_s": a, "end_s": b, "word": txt}


def test_pausas_niveis_e_dramatica():
    words = [_w(0.5, 1.0), _w(1.2, 1.8, "impacto!"),   # pausa DRAMÁTICA depois (2.0s)
             _w(3.8, 4.3), _w(5.4, 5.9),               # gap 1.1s (só leve não corta)
             _w(6.0, 6.5)]
    # normal: corta o gap de 1.1s mas PRESERVA a pausa dramática
    edl, stats = pauses.edl_sem_pausas(words, [(0.0, 8.0)], "normal")
    segs = edl["segments"]
    assert stats["removidas"] >= 2  # gap 1.1s + silêncio final (6.5→8.0)
    assert any(abs(s["src_end"] - 4.44) < 0.01 for s in segs), \
        f"corte no fim de 4.3+0.14: {segs}"
    assert not any(abs(s["src_end"] - 1.94) < 0.01 for s in segs), \
        "pausa dramática (depois de '!') deve ser PRESERVADA no nível normal"
    # agressivo corta também a dramática
    edl_ag, _ = pauses.edl_sem_pausas(words, [(0.0, 8.0)], "agressivo")
    assert len(edl_ag["segments"]) > len(segs)
    # leve não corta o gap de 1.1s
    edl_lv, _ = pauses.edl_sem_pausas(words, [(0.0, 8.0)], "leve")
    assert not any(abs(s["src_end"] - 4.44) < 0.01 for s in edl_lv["segments"])
    assert stats["tempo_removido_s"] > 1.0


def test_pausas_respeitam_edicao_existente():
    """Trechos já removidos pelo Editor continuam fora; só corta POR DENTRO."""
    words = [_w(1.0, 2.0), _w(4.0, 5.0), _w(11.0, 12.0), _w(14.5, 15.5)]
    edl, _ = pauses.edl_sem_pausas(words, [(0.0, 6.0), (10.0, 16.0)], "normal")
    for s in edl["segments"]:
        assert s["src_end"] <= 6.0 or s["src_start"] >= 10.0, \
            "nenhum segmento pode voltar a incluir o trecho removido (6–10s)"


def test_pauses_preview_endpoint(client, auth):
    from app.db.base import session
    from app.db.models import CutCandidate, Project, SourceVideo, Transcript, TranscriptWord

    with session() as s:
        p = Project(name="Pausas")
        s.add(p)
        s.flush()
        src = SourceVideo(project_id=p.id, origin="file", file_path="/v.mp4",
                          duration_s=60, status="ready")
        s.add(src)
        s.flush()
        t = Transcript(source_video_id=src.id, full_text="…")
        s.add(t)
        s.flush()
        for i, (a, b) in enumerate([(2.0, 2.5), (2.6, 3.1), (5.5, 6.0), (6.1, 6.6)]):
            s.add(TranscriptWord(transcript_id=t.id, idx=i, start_s=a, end_s=b, word=f"w{i}"))
        c = CutCandidate(source_video_id=src.id, project_id=p.id, start_s=2.0, end_s=8.0,
                         score=70, title="C",
                         edl={"segments": [{"src_start": 2.0, "src_end": 8.0}],
                              "fade_in_s": 0.3, "audio": {"gain_db": -1.0}})
        s.add(c)
        s.flush()
        cut_id = c.id

    r = client.post(f"/api/v1/cuts/{cut_id}/pauses-preview", json={"nivel": "normal"},
                    headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["removidas"] >= 1 and len(body["edl"]["segments"]) >= 2
    assert body["edl"]["fade_in_s"] == 0.3, "fades/áudio da edição atual são preservados"
    assert body["edl"]["audio"]["gain_db"] == -1.0
    # nada foi aplicado sem salvar
    cut = client.get(f"/api/v1/cuts/{cut_id}", headers=auth).json()
    assert len(cut["edl"]["segments"]) == 1

    r = client.post(f"/api/v1/cuts/{cut_id}/pauses-preview", json={"nivel": "banana"},
                    headers=auth)
    assert r.status_code == 422


def test_perfil_editorial_transparente():
    def det(score, status, dur=40.0):
        return {"id": "x", "rank": 1, "score": score, "status": status, "title": "",
                "start_s": 0.0, "end_s": dur, "origin": "claude", "human_rank": None}

    poucos = [{"cortes_detalhe": [det(80, "approved")]}]
    assert editorial_profile(poucos)["pronto"] is False

    fontes = [{"cortes_detalhe": [
        det(85, "approved", 42), det(88, "approved", 38), det(82, "approved", 45),
        det(70, "approved", 51), det(45, "rejected"), det(48, "rejected"),
        det(42, "rejected"), det(60, "rejected"),
    ]}]
    p = editorial_profile(fontes)
    assert p["pronto"] and p["amostra"] == 8
    faixa80 = next(f for f in p["taxa_por_faixa_score"] if f["faixa"] == "80–100")
    assert faixa80["taxa"] == 1.0
    assert any("score" in s.lower() for s in p["sugestoes"]), \
        "faixa fraca (0–50 toda rejeitada) deve virar sugestão de score mínimo"
    assert "decisões" in p["nota"], "transparência: a nota explica a origem do perfil"


def test_metricas_de_edicao_no_relatorio(client, auth):
    from app.db.base import session
    from app.db.models import CutCandidate, Project, SourceVideo

    with session() as s:
        p = Project(name="Rel")
        s.add(p)
        s.flush()
        src = SourceVideo(project_id=p.id, origin="file", file_path="/v.mp4",
                          duration_s=120, status="ready")
        s.add(src)
        s.flush()
        s.add(CutCandidate(source_video_id=src.id, project_id=p.id, start_s=1, end_s=20,
                           score=80, title="A", status="approved",
                           edl={"segments": [{"src_start": 1, "src_end": 18}]},
                           edits={"word_overrides": {"3": "corrigida", "7": "tb"},
                                  "framing": "left"}))
        s.add(CutCandidate(source_video_id=src.id, project_id=p.id, start_s=30, end_s=50,
                           score=60, title="B", status="rejected"))
        src_id, proj_id = src.id, p.id

    rep = client.get(f"/api/v1/reports/sources/{src_id}", headers=auth).json()
    assert rep["edicao"] == {"cortes_com_edicao_no_editor": 1,
                             "palavras_corrigidas": 2, "enquadramento_manual": 1}
    proj = client.get(f"/api/v1/reports/projects/{proj_id}", headers=auth).json()
    assert "perfil_editorial" in proj
