"""v4 FASE B — Motion Manifest: modelo, validação, persistência e paridade.

O manifest é a fonte única da verdade dos efeitos (cut.motion). Estes testes
provam: (1) o avaliador determinístico bate com o contrato compartilhado que o
preview TS também verifica; (2) o PATCH valida/normaliza/persiste sem inflar
edit_revision em reenvio; (3) bancos antigos migram (NULL = manifest vazio).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.db.base import session
from app.db.models import CutCandidate, Project, SourceVideo
from app.pipeline import motion as m

CASES = json.loads((Path(__file__).resolve().parents[2]
                    / "shared" / "motion-cases.json").read_text())


def _semeia() -> str:
    with session() as s:
        p = Project(name="Motion")
        s.add(p)
        s.flush()
        src = SourceVideo(project_id=p.id, origin="file", file_path="/x.mp4",
                          duration_s=120.0, status="ready")
        s.add(src)
        s.flush()
        c = CutCandidate(source_video_id=src.id, project_id=p.id, start_s=10.0,
                         end_s=30.0, score=80.0, title="Corte")
        s.add(c)
        s.flush()
        return c.id


# ---------------------------------------------------------------------------
# Paridade preview ↔ render (Entrega 60): o contrato é verificado AQUI e no TS
# ---------------------------------------------------------------------------

def test_easings_batem_com_o_contrato_compartilhado():
    for nome, esperados in CASES["easings"].items():
        for u, v in zip(CASES["us"], esperados):
            assert m.ease(nome, u) == pytest.approx(v, abs=1e-12), f"{nome}@{u}"
    # biblioteca fechada: todo easing do contrato existe e vice-versa
    assert sorted(m.EASINGS) == sorted(CASES["easings"])


def test_keyframes_batem_com_o_contrato_compartilhado():
    for caso in CASES["keyframes"]:
        for u, v in zip(caso["us"], caso["vals"]):
            assert m.eval_keyframes(caso["track"], u) == pytest.approx(v, abs=1e-12)


def test_ruido_deterministico_bate_com_o_contrato():
    for r in CASES["rng"]:
        assert m.rng01(r["seed"], r["i"]) == pytest.approx(r["v"], abs=0)
    sk = CASES["shake"]
    for c in sk["cases"]:
        dx, dy, rot = m.shake_offset(c["t"], c["seed"], sk["amp_x"], sk["amp_y"],
                                     sk["rot_deg"], sk["freq"])
        assert (dx, dy, rot) == pytest.approx((c["dx"], c["dy"], c["rot"]), abs=1e-12)


def test_mesma_seed_mesmo_movimento_seed_nova_movimento_novo():
    """Entregas 46–47: renderizar duas vezes = idêntico; 'Nova variação' muda."""
    a = [m.shake_offset(t / 30, 777, 18, 12, 1.2, 11) for t in range(30)]
    b = [m.shake_offset(t / 30, 777, 18, 12, 1.2, 11) for t in range(30)]
    c = [m.shake_offset(t / 30, 778, 18, 12, 1.2, 11) for t in range(30)]
    assert a == b, "mesma seed deve reproduzir exatamente o mesmo shake"
    assert a != c, "seed nova deve produzir variação"


def test_keyframes_clampam_e_nao_extrapolam():
    tr = [{"t": 0.2, "v": 1.0}, {"t": 0.8, "v": 2.0, "ease": "impacto"}]
    assert m.eval_keyframes(tr, 0.0) == 1.0  # antes do primeiro: clampa
    assert m.eval_keyframes(tr, 1.0) == 2.0  # depois do último: clampa
    # back_out passa de 1.0 no overshoot, mas o easing é clampado em u, não em v
    assert m.eval_keyframes(tr, 0.5) != 1.5  # curva não é linear


# ---------------------------------------------------------------------------
# Validação e normalização do manifest
# ---------------------------------------------------------------------------

def _efeito(**kw) -> dict:
    base = {"type": "video_fx", "preset": "punch_zoom", "start": 2.0, "end": 3.0,
            "target": {"kind": "video"}}
    base.update(kw)
    return base


def test_manifest_normaliza_defaults_e_ordena():
    man = m.validate_manifest({"effects": [
        _efeito(start=5.0, end=6.0),
        _efeito(start=1.0, end=2.5, intensity="forte", seed=42),
    ]})
    assert man["version"] == 1
    e0, e1 = man["effects"]
    assert e0["start"] == 1.0, "efeitos ordenados por início"
    assert e0["intensity"] == "forte" and e0["seed"] == 42
    assert e1["intensity"] == "normal" and e1["enabled"] is True
    assert e1["id"] and e1["seed"] == m.seed_de(e1["id"]), "seed padrão derivada do id"


def test_manifest_vazio_vira_none_e_none_passa():
    assert m.validate_manifest(None) is None
    assert m.validate_manifest({"version": 1, "effects": []}) is None


def test_manifest_preserva_chaves_desconhecidas():
    """Entrega 81: um manifest com campos futuros não é destruído."""
    man = m.validate_manifest({"effects": [_efeito(futuro_campo="x")],
                               "extensao_futura": {"a": 1}})
    assert man["extensao_futura"] == {"a": 1}
    assert man["effects"][0]["futuro_campo"] == "x"


@pytest.mark.parametrize("ruim, trecho", [
    (_efeito(type="explodir_tela"), "tipo desconhecido"),
    (_efeito(preset=""), "preset é obrigatório"),
    (_efeito(start=3.0, end=3.0), "intervalo inválido"),
    (_efeito(start=-1.0), "intervalo inválido"),
    (_efeito(target={"kind": "planeta"}), "target.kind"),
    (_efeito(intensity="apocaliptica"), "intensidade"),
    (_efeito(easing="vaivem"), "easing desconhecido"),
    (_efeito(keyframes={"scale": [{"t": 2.0, "v": 1}]}), "fora de 0..1"),
    (_efeito(keyframes={"scale": [{"t": 0.5}]}), "precisa de t e v"),
])
def test_manifest_invalido_explica_em_ptbr(ruim, trecho):
    with pytest.raises(ValueError) as exc:
        m.validate_manifest({"effects": [ruim]})
    assert trecho in str(exc.value)


def test_effects_at_respeita_janela_e_enabled():
    man = m.validate_manifest({"effects": [
        _efeito(start=1.0, end=2.0, preset="a"),
        _efeito(start=1.5, end=3.0, preset="b", enabled=False),
    ]})
    ativos = m.effects_at(man, 1.6)
    assert [e["preset"] for e in ativos] == ["a"], "desabilitado não conta (Entrega 141)"
    assert m.effects_at(man, 2.0) == []  # end é exclusivo
    assert m.effects_at(None, 1.0) == []


# ---------------------------------------------------------------------------
# Persistência via PATCH (Entregas 79–80) e migração (81)
# ---------------------------------------------------------------------------

def test_patch_persiste_manifest_e_conta_como_edicao_visual(client, auth):
    cut_id = _semeia()
    rev = client.get(f"/api/v1/cuts/{cut_id}", headers=auth).json()["edit_revision"]
    corpo = {"motion": {"version": 1, "effects": [
        _efeito(id="fx1", start=2.0, end=3.2, intensity="forte", seed=99)]}}
    r = client.patch(f"/api/v1/cuts/{cut_id}", json=corpo, headers=auth)
    assert r.status_code == 200
    assert r.json()["edit_revision"] == rev + 1, "motion é edição visual"

    reaberto = client.get(f"/api/v1/cuts/{cut_id}", headers=auth).json()
    e = reaberto["motion"]["effects"][0]
    assert (e["id"], e["seed"], e["intensity"]) == ("fx1", 99, "forte")

    # reenviar o MESMO manifest (autosave) não infla a revisão
    r2 = client.patch(f"/api/v1/cuts/{cut_id}", json=corpo, headers=auth)
    assert r2.json()["edit_revision"] == rev + 1

    # remover tudo (null explícito) é edição e limpa a coluna
    r3 = client.patch(f"/api/v1/cuts/{cut_id}", json={"motion": None}, headers=auth)
    assert r3.json()["edit_revision"] == rev + 2
    assert r3.json()["motion"] is None


def test_patch_invalido_da_422_sem_gravar(client, auth):
    cut_id = _semeia()
    r = client.patch(f"/api/v1/cuts/{cut_id}",
                     json={"motion": {"effects": [{"type": "video_fx"}]}}, headers=auth)
    assert r.status_code == 422
    assert "Motion Manifest inválido" in r.json()["detail"]
    assert client.get(f"/api/v1/cuts/{cut_id}", headers=auth).json()["motion"] is None


def test_migracao_v6_abre_cortes_antigos_sem_manifest(client, auth):
    """Banco v5 → v6: a coluna nasce NULL e o corte abre como sempre abriu."""
    from app.db.base import get_engine
    from app.db.migrate import _m6_motion

    cut_id = _semeia()
    with get_engine().connect() as conn:
        _m6_motion(conn)  # idempotente com create_all (duplicate column tolerado)
        conn.commit()
    corte = client.get(f"/api/v1/cuts/{cut_id}", headers=auth).json()
    assert corte["motion"] is None
    assert corte["status"] == "pending_review"
