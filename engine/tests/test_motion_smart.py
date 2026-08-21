"""v4 FASE J — Smart Motion: semântica de verso/rima, cooldown e estilos.

A automação nunca inventa: escolhe do catálogo controlado, explica cada
sugestão em PT-BR (reason) e NÃO grava nada — quem aplica é o Editor,
como efeitos comuns e desfazíveis.
"""

from __future__ import annotations

from app.db.base import session
from app.db.models import CutCandidate, Project, SourceVideo, Transcript, TranscriptWord
from app.pipeline import motion_callout, motion_composite, motion_smart, motion_text, motion_video

# BATALHA sintética: 3 versos, rima "-ou", fecho com palavra de impacto.
# (pausas de 0.5s fecham os versos; a última tem respiro de 1s = reação)
FRASES = [
    ["hoje", "o", "meu", "flow", "chegou"],       # verso 1 — termina "chegou"
    ["sua", "rima", "fraca", "acabou"],           # verso 2 — rima + impacto
    ["e", "essa", "aqui", "te", "matou"],         # verso 3 — fatality
    ["depois", "eu", "sigo", "tranquilo"],        # verso pós-reação
]


def _words() -> list[dict]:
    out = []
    t = 0.5
    idx = 0
    for vi, verso in enumerate(FRASES):
        for w in verso:
            out.append({"idx": idx, "start_s": round(t, 2),
                        "end_s": round(t + 0.28, 2), "word": w})
            idx += 1
            t += 0.34
        t += 1.0 if vi == 2 else 0.5  # respiro maior após o 3º verso
    return out


def test_classificacao_acha_punchlines_pela_rima_e_impacto():
    cands = {c["word"]: c for c in motion_smart.classify(_words())
             if c["role"] != "reaction"}
    assert cands["acabou"]["role"] in ("punchline", "fatality")
    assert "rima" in cands["acabou"]["reason"]
    assert cands["matou"]["role"] == "fatality", cands["matou"]
    assert cands["matou"]["score"] > cands["chegou"]["score"]
    reacoes = [c for c in motion_smart.classify(_words()) if c["role"] == "reaction"]
    assert reacoes and "respiro" in reacoes[0]["reason"], \
        "pausa longa pós-punchline vira janela de reação (Entrega 74)"


def test_sugestoes_respeitam_catalogo_cooldown_e_ordem():
    sug = motion_smart.suggest(_words(), style="batalha", seed=5)
    assert sug, "batalha sintética tem que render sugestões"
    catalogo = (set(motion_text.TEXT_PRESETS) | set(motion_video.VIDEO_PRESETS)
                | set(motion_callout.CALLOUT_PRESETS)
                | set(motion_composite.COMPOSITE_PRESETS))
    for x in sug:
        assert x["suggested_preset"] in catalogo, "só o catálogo controlado"
        assert x["reason"] and "“" in x["reason"], "reason em PT-BR com a palavra"
        assert x["semantic_role"] in ("setup", "build", "punchline",
                                      "fatality", "reaction")
    starts = [x["start"] for x in sug]
    assert starts == sorted(starts)
    dens = motion_smart.DENSITIES["balanceada"]
    for a, b in zip(sug, sug[1:], strict=False):
        assert b["start"] - a["start"] >= dens["min_gap_s"] - 1e-6, \
            "cooldown entre efeitos (Entrega 23)"


def test_fatality_do_estilo_batalha_e_composicao():
    sug = motion_smart.suggest(_words(), style="batalha", seed=5)
    fat = [x for x in sug if x["semantic_role"] == "fatality"]
    assert fat and fat[0]["suggested_preset"] == "fatality_composta"
    assert fat[0]["kind"] == "composite"


def test_estilos_editam_o_comportamento_sem_hardcode_de_nicho():
    limpa = motion_smart.suggest(_words(), style="limpa", seed=5)
    agressiva = motion_smart.suggest(_words(), style="agressiva", seed=5)
    assert len(limpa) <= len(agressiva)
    assert all(x["intensity"] == "suave" for x in limpa)
    assert all(x["intensity"] == "forte" for x in agressiva)
    # os perfis são DADOS — todo estilo declara papéis e densidade
    for perfil in motion_smart.EDITORIAL_STYLES.values():
        assert perfil["densidade"] in motion_smart.DENSITIES
        assert "punchline" in perfil["roles"]


def test_densidades_e_desativado():
    baixa = motion_smart.suggest(_words(), style="batalha", density="baixa", seed=5)
    alta = motion_smart.suggest(_words(), style="batalha", density="alta", seed=5)
    assert len(baixa) <= len(alta)
    assert motion_smart.suggest(_words(), style="batalha",
                                density="desativado", seed=5) == []


def test_determinismo_mesma_seed_mesmas_sugestoes():
    a = motion_smart.suggest(_words(), style="batalha", seed=9)
    b = motion_smart.suggest(_words(), style="batalha", seed=9)
    assert a == b


def test_endpoint_sugere_sem_gravar(client, auth):
    with session() as s:
        p = Project(name="Smart")
        s.add(p)
        s.flush()
        src = SourceVideo(project_id=p.id, origin="file", file_path="/x.mp4",
                          duration_s=60.0, status="ready")
        s.add(src)
        s.flush()
        t = Transcript(source_video_id=src.id, language="pt")
        s.add(t)
        s.flush()
        for w in _words():
            s.add(TranscriptWord(transcript_id=t.id, idx=w["idx"],
                                 start_s=w["start_s"] + 10.0,
                                 end_s=w["end_s"] + 10.0, word=w["word"]))
        c = CutCandidate(source_video_id=src.id, project_id=p.id, start_s=10.0,
                         end_s=20.0, score=80.0, title="Batalha")
        s.add(c)
        s.flush()
        cut_id = c.id

    r = client.post(f"/api/v1/cuts/{cut_id}/motion/suggest",
                    json={"style": "batalha", "seed": 5}, headers=auth)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["suggestions"], "sugestões para a batalha"
    assert {s2["id"] for s2 in corpo["styles"]} == set(motion_smart.EDITORIAL_STYLES)
    # tempos em TEMPO DE SAÍDA (corte começa em 10s da fonte → 0s na saída)
    assert all(0 <= x["start"] < 12 for x in corpo["suggestions"])
    # nada foi gravado: o manifest do corte segue vazio
    assert client.get(f"/api/v1/cuts/{cut_id}",
                      headers=auth).json()["motion"] is None
    # validações de entrada
    assert client.post(f"/api/v1/cuts/{cut_id}/motion/suggest",
                       json={"style": "trapstar"}, headers=auth).status_code == 422
