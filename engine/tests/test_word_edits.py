"""Ponto 44 — editor de palavras: substituir, excluir, inserir antes/depois.

A transcrição original é imutável; a camada de legenda do corte aplica os
overrides SEM deslocar os timestamps das demais palavras.
"""

from __future__ import annotations

from app.pipeline import edl as edl_mod

# "eu gosto muito disso" — 4 palavras coladas (sem pausas grandes)
WORDS = [
    {"idx": 0, "start_s": 10.0, "end_s": 10.3, "word": "eu"},
    {"idx": 1, "start_s": 10.3, "end_s": 10.7, "word": "gosto"},
    {"idx": 2, "start_s": 10.7, "end_s": 11.1, "word": "muito"},
    {"idx": 3, "start_s": 11.1, "end_s": 11.5, "word": "disso"},
]
EDL = {"version": 1, "segments": [{"src_start": 10.0, "src_end": 12.0}]}


def test_cenario_do_ponto_44():
    edits = {
        "word_overrides": {"1": "gostei"},
        "word_inserted": [{"id": "i1", "anchor_idx": 2, "placement": "before",
                           "text": "realmente"}],
        "word_deleted": [3],
    }
    out = edl_mod.map_words(WORDS, EDL, edits)
    assert [w["word"] for w in out] == ["eu", "gostei", "realmente", "muito"]

    # timestamps NÃO deslocados arbitrariamente: "eu" e "gostei" intactos
    assert (out[0]["start_s"], out[0]["end_s"]) == (0.0, 0.3)
    assert (out[1]["start_s"], out[1]["end_s"]) == (0.3, 0.7)
    # sem pausa antes de "muito": a inserida divide a janela DA ÂNCORA
    realmente, muito = out[2], out[3]
    assert realmente["start_s"] == 0.7
    assert realmente["end_s"] == muito["start_s"]
    assert muito["end_s"] == 1.1, "o fim da âncora não muda"
    # ordem temporal íntegra
    for a, b in zip(out, out[1:], strict=False):
        assert a["end_s"] <= b["start_s"] + 1e-6


def test_inserir_aproveita_pausa_quando_existe():
    words = [
        {"idx": 0, "start_s": 10.0, "end_s": 10.4, "word": "olha"},
        {"idx": 1, "start_s": 11.4, "end_s": 11.8, "word": "isso"},  # pausa de 1s antes
    ]
    edits = {"word_inserted": [{"id": "i1", "anchor_idx": 1, "placement": "before",
                                "text": "só"}]}
    out = edl_mod.map_words(words, EDL, edits)
    assert [w["word"] for w in out] == ["olha", "só", "isso"]
    so = out[1]
    assert so["start_s"] >= 0.4 and so["end_s"] <= 1.4, "vive dentro da pausa"
    # âncora intacta quando há pausa disponível
    assert (out[2]["start_s"], out[2]["end_s"]) == (1.4, 1.8)


def test_inserir_depois_e_excluir_inseridas_nao_quebram():
    edits = {"word_inserted": [{"id": "i1", "anchor_idx": 0, "placement": "after",
                                "text": "sim"}]}
    out = edl_mod.map_words(WORDS, EDL, edits)
    assert [w["word"] for w in out][:2] == ["eu", "sim"]
    assert out[1]["ins_id"] == "i1"
    # âncora com fim reduzido (sem pausa após "eu"), demais intactas
    assert out[0]["start_s"] == 0.0
    assert out[2]["word"] == "gosto" and out[2]["start_s"] == 0.3

    # âncora removida pela EDL → inserção é ignorada com segurança
    edl2 = {"version": 1, "segments": [{"src_start": 10.6, "src_end": 12.0}]}
    out2 = edl_mod.map_words(WORDS, edl2, edits)
    assert all(w.get("ins_id") is None for w in out2)


def test_caption_cards_refletem_edicao_de_palavras(client, auth):
    """Fechar e reabrir: o resultado persiste idêntico via caption-cards."""
    from app.db.base import session
    from app.db.models import CutCandidate, Project, SourceVideo, Transcript, TranscriptWord

    with session() as s:
        p = Project(name="P44")
        s.add(p)
        s.flush()
        src = SourceVideo(project_id=p.id, origin="file", file_path="/x.mp4",
                          duration_s=60.0, status="ready", fps=30.0)
        s.add(src)
        s.flush()
        t = Transcript(source_video_id=src.id)
        s.add(t)
        s.flush()
        for w in WORDS:
            s.add(TranscriptWord(transcript_id=t.id, idx=w["idx"], start_s=w["start_s"],
                                 end_s=w["end_s"], word=w["word"]))
        c = CutCandidate(source_video_id=src.id, project_id=p.id, start_s=10.0,
                         end_s=12.0, score=70.0, title="Corte")
        s.add(c)
        s.flush()
        cut_id = c.id

    edits = {
        "word_overrides": {"1": "gostei"},
        "word_inserted": [{"id": "i1", "anchor_idx": 2, "placement": "before",
                           "text": "realmente"}],
        "word_deleted": [3],
    }
    r = client.patch(f"/api/v1/cuts/{cut_id}", json={"edits": edits}, headers=auth)
    assert r.status_code == 200

    for _ in range(2):  # duas leituras = fechar e reabrir
        body = client.get(f"/api/v1/cuts/{cut_id}/caption-cards", headers=auth).json()
        palavras = [w["word"] for card in body["cards"] for w in card["words"]]
        assert palavras == ["eu", "gostei", "realmente", "muito"]

    # transcrição original permanece intacta no banco
    palavras_fonte = client.get(f"/api/v1/cuts/{cut_id}/words?pad_s=0", headers=auth).json()
    assert [w["word"] for w in palavras_fonte["words"]] == ["eu", "gosto", "muito", "disso"]
