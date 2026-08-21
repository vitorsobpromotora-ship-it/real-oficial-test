"""Etapa A — máquina de estados editorial, revisões e ciclo de render derivado.

O estado EDITORIAL (pending_review/approved/rejected) nunca se mistura com o
ciclo de RENDER (not_rendered/queued/rendering/rendered/render_failed), e
edit_revision > revisão do render concluído significa "Render desatualizado".
"""

from __future__ import annotations

from sqlalchemy import text

from app.db.base import session
from app.db.models import CutCandidate, Project, Render, SourceVideo


def _semeia(status: str = "pending_review") -> tuple[str, str]:
    with session() as s:
        p = Project(name="Estados")
        s.add(p)
        s.flush()
        src = SourceVideo(project_id=p.id, origin="file", file_path="/x.mp4",
                          duration_s=120.0, status="ready")
        s.add(src)
        s.flush()
        c = CutCandidate(source_video_id=src.id, project_id=p.id, start_s=10.0,
                         end_s=30.0, score=80.0, title="Corte", status=status)
        s.add(c)
        s.flush()
        return p.id, c.id


def test_novo_corte_nasce_pendente_e_flui_para_aprovados(client, auth):
    """Ponto 2: pending_review → approved sai de 'Para revisar' e entra em 'Aprovados'."""
    project_id, cut_id = _semeia()
    corte = client.get(f"/api/v1/cuts/{cut_id}", headers=auth).json()
    assert corte["status"] == "pending_review"
    assert corte["render_state"] == "not_rendered"
    assert corte["edit_revision"] == 1

    pend = client.get(f"/api/v1/projects/{project_id}/cuts?status=pending_review",
                      headers=auth).json()
    assert [c["id"] for c in pend] == [cut_id]

    r = client.patch(f"/api/v1/cuts/{cut_id}", json={"status": "approved"}, headers=auth)
    assert r.json()["status"] == "approved" and r.json()["reviewed_at"]

    pend = client.get(f"/api/v1/projects/{project_id}/cuts?status=pending_review",
                      headers=auth).json()
    assert pend == [], "aprovado deve sumir de Para revisar"
    aprov = client.get(f"/api/v1/projects/{project_id}/cuts?status=approved", headers=auth).json()
    assert [c["id"] for c in aprov] == [cut_id]


def test_rejeitar_e_restaurar_para_revisao(client, auth):
    """Ponto 2: rejeição não é definitiva — Restaurar volta a exigir decisão."""
    project_id, cut_id = _semeia()
    client.patch(f"/api/v1/cuts/{cut_id}", json={"status": "rejected"}, headers=auth)
    rej = client.get(f"/api/v1/projects/{project_id}/cuts?status=rejected", headers=auth).json()
    assert [c["id"] for c in rej] == [cut_id]

    r = client.patch(f"/api/v1/cuts/{cut_id}", json={"status": "pending_review"}, headers=auth)
    assert r.json()["status"] == "pending_review"
    assert r.json()["reviewed_at"] is None, "restaurar limpa a decisão anterior"

    # sinônimo legado "draft" continua aceito (compatibilidade de API)
    client.patch(f"/api/v1/cuts/{cut_id}", json={"status": "rejected"}, headers=auth)
    r = client.patch(f"/api/v1/cuts/{cut_id}", json={"status": "draft"}, headers=auth)
    assert r.json()["status"] == "pending_review"


def test_corte_rejeitado_nao_renderiza(client, auth):
    """Ponto 2: renderização direta de um corte rejeitado é bloqueada."""
    _, cut_id = _semeia(status="rejected")
    r = client.post("/api/v1/renders", json={"cut_id": cut_id}, headers=auth)
    assert r.status_code == 422
    assert "restaure" in r.json()["detail"].lower()
    # prévia técnica continua permitida (a tela de análise precisa do player)
    r = client.post(f"/api/v1/cuts/{cut_id}/preview", headers=auth)
    assert r.status_code == 200


def test_titulo_descricao_e_platform_metadata_persistem(client, auth):
    """Ponto 1: título/descrição são publishing metadata — persistem e reabrem."""
    _, cut_id = _semeia()
    r = client.patch(f"/api/v1/cuts/{cut_id}",
                     json={"title": "Meu título", "description": "Descrição para publicar",
                           "platform_metadata": {"tiktok": {"hashtags": ["#corte"]}}},
                     headers=auth)
    assert r.status_code == 200
    reaberto = client.get(f"/api/v1/cuts/{cut_id}", headers=auth).json()
    assert reaberto["title"] == "Meu título"
    assert reaberto["description"] == "Descrição para publicar"
    assert reaberto["platform_metadata"] == {"tiktok": {"hashtags": ["#corte"]}}


def test_edit_revision_incrementa_so_em_mudanca_visual(client, auth):
    """Ponto 37: descrição/status não mexem na revisão; edição visual sim."""
    _, cut_id = _semeia()
    rev = client.get(f"/api/v1/cuts/{cut_id}", headers=auth).json()["edit_revision"]

    r = client.patch(f"/api/v1/cuts/{cut_id}",
                     json={"description": "nova", "status": "approved"}, headers=auth)
    assert r.json()["edit_revision"] == rev, "metadados editoriais não são edição visual"

    r = client.patch(f"/api/v1/cuts/{cut_id}",
                     json={"caption_style": {"preset": "clean"}}, headers=auth)
    assert r.json()["edit_revision"] == rev + 1

    # reenviar o MESMO valor visual não é mudança
    r = client.patch(f"/api/v1/cuts/{cut_id}",
                     json={"caption_style": {"preset": "clean"}}, headers=auth)
    assert r.json()["edit_revision"] == rev + 1


def test_ciclo_de_render_derivado_e_render_desatualizado(client, auth):
    """Ponto 3: estado de render vem dos registros de Render; edição posterior
    ao render concluído marca render_outdated (Render desatualizado)."""
    _, cut_id = _semeia(status="approved")

    with session() as s:  # render final concluído na revisão atual (1)
        s.add(Render(cut_id=cut_id, kind="final", status="done", progress=1.0,
                     output_path="/out/a.mp4", edit_revision=1))
    corte = client.get(f"/api/v1/cuts/{cut_id}", headers=auth).json()
    assert corte["render_state"] == "rendered"
    assert corte["render_outdated"] is False
    assert corte["latest_render_id"]

    # usuário volta ao Editor e altera algo visual → revisão 2 > render 1
    client.patch(f"/api/v1/cuts/{cut_id}", json={"framing": "left"}, headers=auth)
    corte = client.get(f"/api/v1/cuts/{cut_id}", headers=auth).json()
    assert corte["edit_revision"] == 2
    assert corte["render_state"] == "rendered"
    assert corte["render_outdated"] is True, "render antigo deve aparecer como desatualizado"

    # nova versão renderizada na revisão 2 → volta a estar em dia
    with session() as s:
        s.add(Render(cut_id=cut_id, kind="final", status="done", progress=1.0,
                     output_path="/out/b.mp4", edit_revision=2))
    corte = client.get(f"/api/v1/cuts/{cut_id}", headers=auth).json()
    assert corte["render_outdated"] is False

    # falha posterior aparece como render_failed (o mais recente prevalece)
    with session() as s:
        s.add(Render(cut_id=cut_id, kind="final", status="failed", edit_revision=2))
    corte = client.get(f"/api/v1/cuts/{cut_id}", headers=auth).json()
    assert corte["render_state"] == "render_failed"


def test_render_novo_carimba_revisao_atual(client, auth):
    """POST /renders guarda a revisão do corte no momento da criação."""
    _, cut_id = _semeia(status="approved")
    client.patch(f"/api/v1/cuts/{cut_id}", json={"framing": "left"}, headers=auth)  # rev 2
    r = client.post("/api/v1/renders", json={"cut_id": cut_id}, headers=auth)
    assert r.status_code == 201
    with session() as s:
        row = s.get(Render, r.json()["id"])
        assert row.edit_revision == 2


def test_migracao_v5_converte_draft_em_pending_review(client, auth):
    """Bancos v2 com cortes 'draft' migram para o estado editorial explícito."""
    from app.db.base import get_engine
    from app.db.migrate import _m5_estado_editorial

    _, cut_id = _semeia()
    with session() as s:  # simula linha antiga
        s.execute(text("UPDATE cut_candidates SET status = 'draft' WHERE id = :i"),
                  {"i": cut_id})
    with get_engine().connect() as conn:
        _m5_estado_editorial(conn)
        conn.commit()
    corte = client.get(f"/api/v1/cuts/{cut_id}", headers=auth).json()
    assert corte["status"] == "pending_review"


def test_autosave_repetido_nao_infla_a_revisao(client, auth):
    """O Editor salva o Draft inteiro a cada alteração e manda framing/punch_in
    FORA de edits. Reenviar o mesmo conteúdo não pode contar como edição nova —
    senão todo autosave marcaria o render como desatualizado."""
    _, cut_id = _semeia()
    corpo = {  # exatamente o que patchFromDraft (app) envia
        "edl": {"segments": [{"src_start": 10.0, "src_end": 30.0}], "fade_in_s": 0.0,
                "fade_out_s": 0.0, "transition_s": 0.0,
                "audio": {"gain_db": 0.0, "mute": False,
                          "fade_in_s": 0.0, "fade_out_s": 0.0}},
        "title": "Corte", "framing": "left", "punch_in": "leve",
        "caption_style": None, "brand_kit_id": None,
        "edits": {"word_overrides": {"3": "olá"}},
    }
    revs = [client.patch(f"/api/v1/cuts/{cut_id}", json=corpo,
                         headers=auth).json()["edit_revision"] for _ in range(3)]
    assert revs[0] == revs[1] == revs[2], f"revisão inflou sem edição: {revs}"

    guardado = client.get(f"/api/v1/cuts/{cut_id}", headers=auth).json()
    assert guardado["edits"]["framing"] == "left"
    assert guardado["edits"]["punch_in"] == "leve"
    assert guardado["edits"]["word_overrides"] == {"3": "olá"}

    # uma mudança de verdade continua contando
    corpo2 = {**corpo, "edits": {"word_overrides": {"3": "oi"}}}
    nova = client.patch(f"/api/v1/cuts/{cut_id}", json=corpo2,
                        headers=auth).json()["edit_revision"]
    assert nova == revs[0] + 1
