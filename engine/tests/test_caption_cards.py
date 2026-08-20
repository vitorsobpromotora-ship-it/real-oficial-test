"""Etapa C — endpoints WYSIWYG: presets expostos e cartões resolvidos pelo motor.

O canvas do Editor desenha EXATAMENTE o que o render queima: mesmo
resolve_style, mesmo build_cards, mesma regra temporal de card_windows.
"""

from __future__ import annotations

from app.db.base import session
from app.db.models import (
    BrandKit,
    CutCandidate,
    Project,
    SourceVideo,
    Transcript,
    TranscriptWord,
)


def _semeia(kit_id: str | None = None, edl: dict | None = None) -> str:
    with session() as s:
        p = Project(name="Cards")
        s.add(p)
        s.flush()
        src = SourceVideo(project_id=p.id, origin="file", file_path="/x.mp4",
                          duration_s=120.0, status="ready", fps=25.0)
        s.add(src)
        s.flush()
        t = Transcript(source_video_id=src.id)
        s.add(t)
        s.flush()
        palavras = ["olha", "só", "o", "que", "aconteceu", "quando", "eu", "cheguei", "lá"]
        for i, w in enumerate(palavras):
            s.add(TranscriptWord(transcript_id=t.id, idx=i, start_s=10.0 + i * 0.4,
                                 end_s=10.3 + i * 0.4, word=w))
        c = CutCandidate(source_video_id=src.id, project_id=p.id, start_s=10.0, end_s=14.0,
                         score=70.0, title="Corte", brand_kit_id=kit_id, edl=edl)
        s.add(c)
        s.flush()
        return c.id


def test_presets_expostos_com_rotulos(client, auth):
    r = client.get("/api/v1/captions/presets", headers=auth)
    assert r.status_code == 200
    presets = r.json()["presets"]
    ids = {p["id"] for p in presets}
    assert {"bold_karaoke", "palavra_pop", "highlight_box"} <= ids
    assert all(p["label"] and p["font_size"] > 0 and p["anchor_top"] > 0 for p in presets)


def test_caption_cards_resolvidos_pelo_motor(client, auth):
    with session() as s:
        kit = BrandKit(name="Meu kit", secondary_color="#00FF00")
        s.add(kit)
        s.flush()
        kit_id = kit.id
    cut_id = _semeia(kit_id=kit_id)

    r = client.get(f"/api/v1/cuts/{cut_id}/caption-cards", headers=auth)
    assert r.status_code == 200
    body = r.json()
    # estilo efetivo: preset ← kit (cor destacada do kit vence a do preset)
    assert body["style"]["highlight_color"] == "#00FF00"
    assert body["fps"] == 25.0
    cards = body["cards"]
    assert cards, "corte com palavras deve ter cartões"
    # regra temporal do render vale aqui: cartões nunca coexistem
    for c1, c2 in zip(cards, cards[1:], strict=False):
        assert c1["end"] <= c2["start"]
    # tempos em TEMPO DE SAÍDA, dentro da duração do corte
    assert all(0 <= c["start"] < c["end"] <= body["out_duration"] + 0.5 for c in cards)
    assert cards[0]["words"][0]["word"] == "olha"
    assert cards[0]["words"][0]["idx"] == 0


def test_caption_cards_respeitam_edl_e_correcoes(client, auth):
    # EDL remove o meio: palavras do trecho removido não podem aparecer
    edl = {"version": 1, "segments": [{"src_start": 10.0, "src_end": 11.2},
                                      {"src_start": 12.8, "src_end": 14.0}]}
    cut_id = _semeia(edl=edl)
    with session() as s:
        c = s.get(CutCandidate, cut_id)
        c.edits = {"word_overrides": {"0": "OLHA!"}}

    r = client.get(f"/api/v1/cuts/{cut_id}/caption-cards", headers=auth)
    body = r.json()
    palavras = [w["word"] for card in body["cards"] for w in card["words"]]
    assert "OLHA!" in palavras, "correção de palavra do corte deve valer no preview"
    assert "aconteceu" not in palavras, "palavra do trecho removido pela EDL não aparece"
    assert body["out_duration"] < 3.0
