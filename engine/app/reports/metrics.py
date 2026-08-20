"""Métricas editoriais e operacionais dos relatórios.

Definições (documentadas no relatório):
- taxa de aproveitamento = aprovados / gerados
- tempo economizado = baseline manual − tempo investido em revisão, onde
  baseline = duração do vídeo (assistir 1×) + 8 min por corte aprovado (edição manual)
- intervenção por corte = tempo de revisão (reviewed_at − review_started_at, teto 30 min)
- qualidade do score = correlação de Spearman entre rank da IA e human_rank
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
from sqlalchemy import select

from ..db.base import session
from ..db.models import (
    ClaudeCall,
    CutCandidate,
    Project,
    Render,
    SourceVideo,
    StageTiming,
    utcnow,
)

MANUAL_MIN_PER_CUT = 8.0
REVIEW_CAP_S = 30 * 60.0


def spearman(a: list[float], b: list[float]) -> float | None:
    if len(a) != len(b) or len(a) < 3:
        return None
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    if ra.std() == 0 or rb.std() == 0:
        return None
    return round(float(np.corrcoef(ra, rb)[0, 1]), 3)


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def _review_seconds(cut: CutCandidate) -> float | None:
    t0, t1 = _parse_iso(cut.review_started_at), _parse_iso(cut.reviewed_at)
    if t0 is None or t1 is None or t1 <= t0:
        return None
    return min(REVIEW_CAP_S, (t1 - t0).total_seconds())


def source_report(source_id: str) -> dict:
    with session() as s:
        src = s.get(SourceVideo, source_id)
        if src is None:
            raise ValueError("Fonte não encontrada")
        cuts = s.execute(select(CutCandidate).where(CutCandidate.source_video_id == source_id,
                               CutCandidate.status != "reserve")
                         .order_by(CutCandidate.rank)).scalars().all()
        calls = s.execute(select(ClaudeCall).where(ClaudeCall.source_video_id == source_id)
                          ).scalars().all()
        timings = s.execute(select(StageTiming).where(StageTiming.source_video_id == source_id)
                            .order_by(StageTiming.created_at)).scalars().all()
        cut_ids = [c.id for c in cuts]
        renders = s.execute(select(Render).where(Render.cut_id.in_(cut_ids))).scalars().all() \
            if cut_ids else []

        gerados = len(cuts)
        aprovados = sum(1 for c in cuts if c.status == "approved")
        rejeitados = sum(1 for c in cuts if c.status == "rejected")
        revisados = [c for c in cuts if _review_seconds(c) is not None]
        review_secs = [_review_seconds(c) for c in revisados]
        editados = sum(1 for c in cuts if c.edits)
        com_edl = sum(1 for c in cuts if c.edl)
        palavras_corrigidas = sum(len((c.edits or {}).get("word_overrides") or {})
                                  for c in cuts)
        enquadramento_manual = sum(
            1 for c in cuts
            if (c.edits or {}).get("framing") or (c.edits or {}).get("framing_segments"))

        duracao_min = (src.duration_s or 0.0) / 60.0
        baseline_min = duracao_min + MANUAL_MIN_PER_CUT * aprovados
        investido_min = sum(review_secs) / 60.0 if review_secs else 0.0
        economia_min = max(0.0, baseline_min - investido_min) if gerados else 0.0

        com_rank = [c for c in cuts if c.human_rank is not None and c.rank is not None]
        corr = spearman([float(c.rank) for c in com_rank],
                        [float(c.human_rank) for c in com_rank])

        origem_claude = sum(1 for c in cuts if c.origin == "claude")

        return {
            "generated_at": utcnow(),
            "source": {"id": src.id, "title": src.title, "duration_s": src.duration_s,
                       "status": src.status, "origin": src.origin,
                       "width": src.width, "height": src.height},
            "cortes": {
                "gerados": gerados, "aprovados": aprovados, "rejeitados": rejeitados,
                "pendentes": gerados - aprovados - rejeitados,
                "taxa_aproveitamento": round(aprovados / gerados, 3) if gerados else None,
                "origem_claude": origem_claude, "origem_heuristica": gerados - origem_claude,
                "score_medio": round(float(np.mean([c.score for c in cuts])), 2) if cuts else None,
                "score_maximo": round(max((c.score for c in cuts), default=0.0), 2) if cuts else None,
            },
            "tempo": {
                "baseline_manual_min": round(baseline_min, 1),
                "revisao_investida_min": round(investido_min, 1),
                "economia_min": round(economia_min, 1),
                "formula": "duração do vídeo + 8 min × aprovados − tempo de revisão",
            },
            "intervencao": {
                "cortes_revisados": len(revisados),
                "media_s": round(float(np.mean(review_secs)), 1) if review_secs else None,
                "mediana_s": round(float(np.median(review_secs)), 1) if review_secs else None,
                "pct_editados": round(editados / gerados, 3) if gerados else None,
            },
            "edicao": {
                "cortes_com_edicao_no_editor": com_edl,
                "palavras_corrigidas": palavras_corrigidas,
                "enquadramento_manual": enquadramento_manual,
            },
            "score_quality": {"spearman_rank_ia_vs_humano": corr, "n_avaliados": len(com_rank)},
            "custo_claude": {
                "chamadas": len(calls),
                "input_tokens": sum(c.input_tokens for c in calls),
                "output_tokens": sum(c.output_tokens for c in calls),
                "cache_read_tokens": sum(c.cache_read_tokens for c in calls),
                "total_usd": round(sum(c.cost_usd for c in calls), 4),
            },
            "timings": [{"stage": t.stage, "seconds": t.seconds} for t in timings],
            "renders": {
                "total": len(renders),
                "concluidos": sum(1 for r in renders if r.status == "done"),
                "falhos": sum(1 for r in renders if r.status == "failed"),
            },
            "cortes_detalhe": [{
                "id": c.id, "rank": c.rank, "score": c.score, "status": c.status,
                "title": c.title, "start_s": c.start_s, "end_s": c.end_s,
                "origin": c.origin, "human_rank": c.human_rank,
            } for c in cuts],
        }


def editorial_profile(per_source: list[dict]) -> dict:
    """Perfil editorial LOCAL e transparente, aprendido das decisões do usuário.

    Nada é alterado automaticamente: o perfil descreve padrões (duração
    preferida, taxa de aprovação por faixa de score) e sugere ajustes que o
    usuário aplica — ou não — nas Configurações."""
    detalhes = [c for r in per_source for c in r["cortes_detalhe"]]
    decididos = [c for c in detalhes if c["status"] in ("approved", "rejected")]
    if len(decididos) < 5:
        return {"pronto": False, "amostra": len(decididos),
                "nota": "Aprove ou rejeite pelo menos 5 cortes para o perfil aparecer."}
    aprov = [c for c in decididos if c["status"] == "approved"]
    faixas = []
    for lo, hi in ((0, 50), (50, 65), (65, 80), (80, 101)):
        band = [c for c in decididos if lo <= c["score"] < hi]
        if band:
            ap = sum(1 for c in band if c["status"] == "approved")
            faixas.append({"faixa": f"{lo}–{min(hi - 1, 100)}", "aprovados": ap,
                           "total": len(band), "taxa": round(ap / len(band), 2)})
    sugestoes: list[str] = []
    dur = [c["end_s"] - c["start_s"] for c in aprov]
    faixa_dur = None
    if len(dur) >= 3:
        p25, p75 = int(np.percentile(dur, 25)), int(np.percentile(dur, 75))
        faixa_dur = [p25, p75]
        sugestoes.append(f"Você aprova mais cortes entre {p25}s e {p75}s — se quiser, "
                         f"ajuste a duração mín/máx em Configurações → Cortes.")
    fracas = [f for f in faixas if f["taxa"] <= 0.25 and f["total"] >= 3]
    if fracas:
        topo = fracas[-1]["faixa"].split("–")[1]
        sugestoes.append(f"Cortes com score até {topo} raramente passam na sua revisão — "
                         f"o perfil Personalizado permite subir o score mínimo.")
    return {"pronto": True, "amostra": len(decididos),
            "duracao_mediana_aprovados_s": round(float(np.median(dur)), 1) if dur else None,
            "faixa_duracao_preferida_s": faixa_dur,
            "taxa_por_faixa_score": faixas, "sugestoes": sugestoes,
            "nota": "Calculado localmente a partir das SUAS decisões. Nada muda sozinho — "
                    "as sugestões só valem se você aplicá-las nas Configurações."}


def project_report(project_id: str) -> dict:
    with session() as s:
        proj = s.get(Project, project_id)
        if proj is None:
            raise ValueError("Projeto não encontrado")
        sources = s.execute(select(SourceVideo.id)
                            .where(SourceVideo.project_id == project_id)).scalars().all()
    per_source = [source_report(sid) for sid in sources]
    gerados = sum(r["cortes"]["gerados"] for r in per_source)
    aprovados = sum(r["cortes"]["aprovados"] for r in per_source)
    return {
        "generated_at": utcnow(),
        "project": {"id": project_id, "name": proj.name},
        "totais": {
            "fontes": len(per_source),
            "cortes_gerados": gerados,
            "cortes_aprovados": aprovados,
            "taxa_aproveitamento": round(aprovados / gerados, 3) if gerados else None,
            "economia_min": round(sum(r["tempo"]["economia_min"] for r in per_source), 1),
            "custo_claude_usd": round(sum(r["custo_claude"]["total_usd"] for r in per_source), 4),
        },
        "perfil_editorial": editorial_profile(per_source),
        "fontes": per_source,
    }
