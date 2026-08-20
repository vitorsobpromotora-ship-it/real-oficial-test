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
        "fontes": per_source,
    }
