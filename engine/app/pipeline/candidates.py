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


def dedup_by_iou(cands: list[dict], threshold: float = 0.45,
                 descartes: list[dict] | None = None) -> list[dict]:
    """Mantém o de maior score entre sobrepostos (IoU temporal > threshold)."""
    kept: list[dict] = []
    for c in sorted(cands, key=lambda x: x["score"], reverse=True):
        span = (c["start_s"], c["end_s"])
        vencedor = next((k for k in kept
                         if iou(span, (k["start_s"], k["end_s"])) > threshold), None)
        if vencedor is None:
            kept.append(c)
        elif descartes is not None:
            ov = iou(span, (vencedor["start_s"], vencedor["end_s"]))
            _descarta(descartes, c, "dedup",
                      f"sobrepõe '{vencedor.get('title', '?')[:40]}' (IoU {ov:.2f})")
    return kept


# ---------------------------------------------------------------------------
# Passagem B — refino de bordas: testa variações de entrada/saída ao redor do
# evento em vez de aceitar cegamente o primeiro timestamp escolhido pelo LLM.
# ---------------------------------------------------------------------------
_HOOK_START = ("?", "eu nunca", "o maior", "segredo", "ninguém", "você não", "a verdade",
               "descobri", "nunca mais", "primeira vez", "vou revelar", "olha", "imagina")
_NUMEROS = tuple("0123456789")


def _score_inicio(sent: dict, features: Features) -> float:
    texto = sent["text"].strip().lower()
    nota = 0.0
    if texto.endswith("?") or "?" in texto[:60]:
        nota += 1.5
    if any(h in texto[:70] for h in _HOOK_START):
        nota += 2.0
    if texto[:1] in _NUMEROS or any(ch in _NUMEROS for ch in texto[:12]):
        nota += 0.8
    pico, _ = features.peak_between(sent["start_s"], sent["start_s"] + 4.0)
    nota += float(pico) * 1.2
    return nota


def _score_fim(sent: dict, features: Features) -> float:
    texto = sent["text"].strip()
    nota = 0.0
    if texto.endswith((".", "!", "…")):
        nota += 1.0
    if texto.endswith(("!", "?")):
        nota += 0.6
    if any(p[0] - 0.2 <= sent["end_s"] <= p[0] + 1.5 for p in features.pauses):
        nota += 1.6  # seguido de pausa: fechamento natural
    antes, _ = features.peak_between(max(0.0, sent["end_s"] - 4.0), sent["end_s"])
    depois, _ = features.peak_between(sent["end_s"], sent["end_s"] + 4.0)
    if antes > depois + 0.05:
        nota += 0.8  # energia caindo após o fim: payoff entregue
    return nota


def refine_borders(c: dict, sentences: list[dict], features: Features,
                   *, min_s: float, max_s: float, duration: float) -> None:
    """Escolhe a melhor variação de início (frase forte/pergunta/pico) e de fim
    (payoff/pausa/queda de energia) ao redor do evento. Distância penaliza."""
    if not sentences:
        return
    ini0, fim0 = c["start_s"], c["end_s"]
    inicios = [s for s in sentences if ini0 - 8.0 <= s["start_s"] <= ini0 + 6.0]
    fins = [s for s in sentences if fim0 - 6.0 <= s["end_s"] <= fim0 + 10.0]
    if not inicios or not fins:
        return
    melhor, melhor_nota = (ini0, fim0), -1e9
    for si in inicios:
        nota_i = _score_inicio(si, features) - 0.35 * abs(si["start_s"] - ini0)
        for sf in fins:
            dur = sf["end_s"] - si["start_s"]
            if dur < min_s * 0.8 or dur > max_s * 1.15:
                continue
            nota = nota_i + _score_fim(sf, features) - 0.30 * abs(sf["end_s"] - fim0)
            if nota > melhor_nota:
                melhor, melhor_nota = (si["start_s"], sf["end_s"]), nota
    c["start_s"], c["end_s"] = melhor


def _descarta(descartes: list[dict], c: dict, estagio: str, motivo: str) -> None:
    if len(descartes) < 60:
        descartes.append({"title": c.get("title", "")[:60],
                          "start_s": round(c["start_s"], 1), "end_s": round(c["end_s"], 1),
                          "score": round(c.get("score", 0.0), 1),
                          "estagio": estagio, "motivo": motivo})


def diversify(cands: list[dict], target: int, min_center_gap: float = 60.0,
              allow_close: bool = False, duration: float = 0.0,
              descartes: list[dict] | None = None) -> tuple[list[dict], list[dict]]:
    """Passagem D. Greedy por score com distância mínima entre centros; completa
    com os melhores 'próximos' até o alvo (bons cortes vizinhos NÃO somem — no
    máximo perdem prioridade). Guarda de concentração: evita todos os cortes
    amontoados no início do vídeo. Retorna (escolhidos, excedente ordenado)."""
    centro = lambda c: (c["start_s"] + c["end_s"]) / 2  # noqa: E731
    ordenados = sorted(cands, key=lambda x: x["score"], reverse=True)
    picked: list[dict] = []
    skipped: list[dict] = []
    for c in ordenados:
        if len(picked) < target and (
                allow_close
                or all(abs(centro(c) - centro(p)) >= min_center_gap for p in picked)):
            picked.append(c)
        else:
            skipped.append(c)
    for c in list(skipped):
        if len(picked) >= target:
            break
        picked.append(c)
        skipped.remove(c)

    # Guarda de concentração: >60% no primeiro terço com alternativa melhor à frente
    if duration > 240 and len(picked) >= 4:
        limite = duration * 0.30
        cedo = [c for c in picked if centro(c) < limite]
        tarde_reserva = [c for c in skipped if centro(c) >= limite]
        while len(cedo) / len(picked) > 0.6 and tarde_reserva:
            pior_cedo = min(cedo, key=lambda c: c["score"])
            melhor_tarde = max(tarde_reserva, key=lambda c: c["score"])
            if melhor_tarde["score"] < pior_cedo["score"] - 8:
                break  # não trocar qualidade real por distribuição
            picked.remove(pior_cedo)
            cedo.remove(pior_cedo)
            skipped.append(pior_cedo)
            picked.append(melhor_tarde)
            tarde_reserva.remove(melhor_tarde)
            skipped.remove(melhor_tarde)
            if descartes is not None:
                _descarta(descartes, pior_cedo, "diversidade",
                          "trocado por corte equivalente fora do início do vídeo")
    skipped.sort(key=lambda x: x["score"], reverse=True)
    return picked, skipped


def finalize_candidates(raw: list[dict], sentences: list[dict], features: Features,
                        *, min_s: float, max_s: float, duration: float,
                        target_count: int, score_min: float = 0.0,
                        min_center_gap: float = 60.0, allow_close: bool = False,
                        max_reserve: int = 8) -> tuple[list[dict], list[dict], dict]:
    """Funil completo, instrumentado com motivo de cada descarte.

    Retorna (finais, reservas, stats). `stats["descartes"]` registra o motivo
    técnico de cada candidato perdido; `reservas` são os melhores excedentes,
    persistíveis para "Mostrar mais oportunidades" sem reanalisar o vídeo."""
    descartes: list[dict] = []

    for c in raw:  # Passagem B: refinar bordas ANTES do snap fino
        refine_borders(c, sentences, features, min_s=min_s, max_s=max_s, duration=duration)
        c["start_s"], c["end_s"] = snap_to_sentences(c["start_s"], c["end_s"], sentences,
                                                     min_s, max_s, duration)
        c["semantic_score"] = semantic_score(c["params"])
        c["rhpt_score"] = rhpt_score(c["start_s"], c["end_s"], features)
        c["score"] = final_score(c["semantic_score"], c["rhpt_score"])

    valid: list[dict] = []
    for c in raw:
        dur = c["end_s"] - c["start_s"]
        if dur < min_s * 0.8:
            _descarta(descartes, c, "duracao", f"curto demais após ajuste ({dur:.1f}s)")
        elif score_min and c["score"] < score_min:
            _descarta(descartes, c, "qualidade",
                      f"score {c['score']:.0f} abaixo do padrão {score_min:.0f}")
        else:
            valid.append(c)

    deduped = dedup_by_iou(valid, descartes=descartes)
    final, excedente = diversify(deduped, target_count, min_center_gap=min_center_gap,
                                 allow_close=allow_close, duration=duration,
                                 descartes=descartes)
    final.sort(key=lambda x: x["score"], reverse=True)
    reservas = excedente[:max_reserve]
    stats = {"brutos": len(raw), "validos": len(valid), "apos_dedup": len(deduped),
             "finais": len(final), "alvo": target_count, "reservas": len(reservas),
             "score_min": score_min, "descartes": descartes}
    return final, reservas, stats


def persist_candidates(source_video_id: str, project_id: str, cands: list[dict],
                       reservas: list[dict] | None = None) -> int:
    """Substitui os candidatos da fonte (re-análise idempotente), ranqueados por score.

    Reservas entram com status='reserve' (sem rank): não aparecem na galeria até
    o usuário pedir "Mostrar mais oportunidades" — sem reanalisar o vídeo."""
    def _row(c: dict, *, rank: int | None, status: str) -> CutCandidate:
        return CutCandidate(
            source_video_id=source_video_id, project_id=project_id,
            start_s=c["start_s"], end_s=c["end_s"], score=c["score"],
            score_breakdown=c["params"], rhpt_score=c["rhpt_score"],
            semantic_score=c["semantic_score"], hook_text=c.get("hook_line", ""),
            title=c.get("title", ""), hashtags=c.get("hashtags", []),
            reason=c.get("reason", ""), verdict=c.get("verdict", "revisar"),
            analysis=c.get("analysis"), origin=c.get("origin", "claude"),
            rank=rank, status=status)

    with session() as s:
        s.execute(delete(CutCandidate).where(CutCandidate.source_video_id == source_video_id))
        for rank, c in enumerate(cands, start=1):
            s.add(_row(c, rank=rank, status="draft"))
        for c in reservas or []:
            s.add(_row(c, rank=None, status="reserve"))
    return len(cands)


def existing_count(source_video_id: str) -> int:
    with session() as s:
        rows = s.execute(select(CutCandidate.id)
                         .where(CutCandidate.source_video_id == source_video_id)).scalars().all()
        return len(rows)
