"""Pós-processamento dos candidatos: snap a fronteiras de frase, dedup por IoU,
diversidade temporal e persistência ranqueada.
"""

from __future__ import annotations

from sqlalchemy import delete, select

from ..db.base import session
from ..db.models import CutCandidate
from .audio_features import Features
from .fusion import final_score, rhpt_score, semantic_score


def snap_to_sentences(start: float, end: float, sentences: list[dict],
                      min_s: float, max_s: float, duration: float) -> tuple[float, float]:
    """Alinha início ao começo da frase que contém/precede `start` e fim ao término
    da frase que contém `end`, respeitando limites de duração."""
    if not sentences:
        return max(0.0, start), min(duration, max(end, start + min_s))

    new_start = start
    for s in sentences:
        if s["start_s"] <= start < s["end_s"] or s["start_s"] >= start:
            if s["start_s"] >= start - 4.0:
                new_start = s["start_s"]
            break

    new_end = end
    candidates_end = [s["end_s"] for s in sentences if s["end_s"] >= end - 0.2]
    if candidates_end:
        first = candidates_end[0]
        if first <= end + 4.0:
            new_end = first

    # Garante duração mínima estendendo até fins de frases seguintes.
    if new_end - new_start < min_s:
        for s in sentences:
            if s["end_s"] > new_end:
                new_end = s["end_s"]
                if new_end - new_start >= min_s:
                    break
    # Trunca ao último fim de frase dentro do máximo.
    if new_end - new_start > max_s:
        fits = [s["end_s"] for s in sentences
                if new_start < s["end_s"] <= new_start + max_s]
        new_end = fits[-1] if fits else new_start + max_s

    new_start = max(0.0, new_start)
    new_end = min(duration if duration > 0 else new_end, new_end)
    if new_end <= new_start:
        new_end = min(duration or (new_start + min_s), new_start + min_s)
    return round(new_start, 3), round(new_end, 3)


def iou(a: tuple[float, float], b: tuple[float, float]) -> float:
    inter = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    union = max(a[1], b[1]) - min(a[0], b[0])
    return inter / union if union > 0 else 0.0


def dedup_by_iou(cands: list[dict], threshold: float = 0.45) -> list[dict]:
    """Mantém o de maior score entre sobrepostos (IoU temporal > threshold)."""
    kept: list[dict] = []
    for c in sorted(cands, key=lambda x: x["score"], reverse=True):
        span = (c["start_s"], c["end_s"])
        if all(iou(span, (k["start_s"], k["end_s"])) <= threshold for k in kept):
            kept.append(c)
    return kept


def diversify(cands: list[dict], target: int, min_center_gap: float = 60.0) -> list[dict]:
    """Greedy por score com distância mínima entre centros; completa com os melhores restantes."""
    picked: list[dict] = []
    skipped: list[dict] = []
    for c in sorted(cands, key=lambda x: x["score"], reverse=True):
        center = (c["start_s"] + c["end_s"]) / 2
        if all(abs(center - (p["start_s"] + p["end_s"]) / 2) >= min_center_gap for p in picked):
            picked.append(c)
        else:
            skipped.append(c)
        if len(picked) >= target:
            return picked
    for c in skipped:
        if len(picked) >= target:
            break
        picked.append(c)
    return picked


def finalize_candidates(raw: list[dict], sentences: list[dict], features: Features,
                        *, min_s: float, max_s: float, duration: float,
                        target_count: int) -> list[dict]:
    for c in raw:
        c["start_s"], c["end_s"] = snap_to_sentences(c["start_s"], c["end_s"], sentences,
                                                     min_s, max_s, duration)
        c["semantic_score"] = semantic_score(c["params"])
        c["rhpt_score"] = rhpt_score(c["start_s"], c["end_s"], features)
        c["score"] = final_score(c["semantic_score"], c["rhpt_score"])
    valid = [c for c in raw if c["end_s"] - c["start_s"] >= min_s * 0.8]
    deduped = dedup_by_iou(valid)
    final = diversify(deduped, target_count)
    final.sort(key=lambda x: x["score"], reverse=True)
    return final


def persist_candidates(source_video_id: str, project_id: str, cands: list[dict]) -> int:
    """Substitui os candidatos da fonte (re-análise idempotente), ranqueados por score."""
    with session() as s:
        s.execute(delete(CutCandidate).where(CutCandidate.source_video_id == source_video_id))
        for rank, c in enumerate(cands, start=1):
            s.add(CutCandidate(
                source_video_id=source_video_id, project_id=project_id,
                start_s=c["start_s"], end_s=c["end_s"], score=c["score"],
                score_breakdown=c["params"], rhpt_score=c["rhpt_score"],
                semantic_score=c["semantic_score"], hook_text=c.get("hook_line", ""),
                title=c.get("title", ""), hashtags=c.get("hashtags", []),
                reason=c.get("reason", ""), origin=c.get("origin", "claude"), rank=rank))
    return len(cands)


def existing_count(source_video_id: str) -> int:
    with session() as s:
        rows = s.execute(select(CutCandidate.id)
                         .where(CutCandidate.source_video_id == source_video_id)).scalars().all()
        return len(rows)
