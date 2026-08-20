"""Estágio de análise: RHPT + análise semântica (Claude/heurística) → candidatos persistidos."""

from __future__ import annotations

import logging

from sqlalchemy import select

from ..db import settings_store
from ..db.base import session
from ..db.models import SourceVideo, Transcript, TranscriptSegment, TranscriptWord
from . import candidates as cand
from .audio_features import compute_features
from .semantic import analyze_semantic

log = logging.getLogger(__name__)


def _load_transcript(source_video_id: str) -> tuple[list[dict], list[dict]]:
    with session() as s:
        t = s.execute(select(Transcript).where(Transcript.source_video_id == source_video_id)
                      .order_by(Transcript.created_at.desc())).scalars().first()
        if t is None:
            raise ValueError("Transcrição inexistente — rode o estágio de transcrição antes")
        sentences = [{"start_s": x.start_s, "end_s": x.end_s, "text": x.text}
                     for x in s.execute(select(TranscriptSegment)
                                        .where(TranscriptSegment.transcript_id == t.id)
                                        .order_by(TranscriptSegment.idx)).scalars().all()]
        words = [{"start_s": w.start_s, "end_s": w.end_s, "word": w.word}
                 for w in s.execute(select(TranscriptWord)
                                    .where(TranscriptWord.transcript_id == t.id)
                                    .order_by(TranscriptWord.idx)).scalars().all()]
    return sentences, words


def stage_analyze(ctx, source_id: str, report) -> None:
    force = bool(ctx.payload.get("options", {}).get("force_analyze"))
    if not force and cand.existing_count(source_id) > 0:
        report(1.0, "Análise já existente")
        return

    with session() as s:
        src = s.get(SourceVideo, source_id)
        if src is None or src.status != "ready":
            raise ValueError("Fonte não está pronta para análise")
        audio_path, duration, project_id = src.audio_path, src.duration_s or 0.0, src.project_id

    sentences, words = _load_transcript(source_id)
    if not sentences:
        report(1.0, "Transcrição vazia — nenhum corte gerado")
        cand.persist_candidates(source_id, project_id, [])
        return

    report(0.02, "Analisando áudio (RHPT)…")
    features = compute_features(audio_path, words,
                                progress_cb=lambda f: report(0.02 + f * 0.23, "Analisando áudio (RHPT)…"),
                                cancel_check=ctx.check_cancel)

    opts = ctx.payload.get("options", {}) or {}
    perfil = resolve_profile(opts, duration)

    raw, meta = analyze_semantic(ctx, source_id, sentences, features, duration,
                                 lambda f, m="": report(0.25 + f * 0.6, m or "Análise semântica…"),
                                 min_s=perfil["min_s"], max_s=perfil["max_s"],
                                 target_count=perfil["target"], agent=opts.get("agent"))

    report(0.87, "Consolidando candidatos…")
    final, reservas, stats = cand.finalize_candidates(
        raw, sentences, features, min_s=perfil["min_s"], max_s=perfil["max_s"],
        duration=duration, target_count=perfil["target"], score_min=perfil["score_min"],
        min_center_gap=perfil["min_gap"], allow_close=perfil["allow_close"],
        max_reserve=perfil["max_reserve"])
    n = cand.persist_candidates(source_id, project_id, final, reservas)
    stats["perfil"] = perfil["nome"]
    _persist_funnel(ctx.job_id, stats)

    msg = (f"{n} cortes sugeridos (perfil {perfil['nome']}; funil: {stats['brutos']} brutos → "
           f"{stats['validos']} válidos → {stats['apos_dedup']} após dedup → {n} finais; "
           f"{stats['reservas']} em reserva)")
    if n < perfil["target"]:
        msg = (f"Encontramos {n} cortes acima do padrão de qualidade solicitado — a meta "
               f"configurada era {perfil['target']}. Funil: {stats['brutos']} brutos → "
               f"{stats['validos']} válidos → {stats['apos_dedup']} após dedup; "
               f"{stats['reservas']} em reserva")
    report(1.0, msg + _ai_note(meta))


# Perfis de geração (spec §9): a quantidade deixa de parecer "fixa" e vira uma
# escolha clara. Nunca inventamos cortes ruins para bater meta — quando faltar,
# a mensagem final diz exatamente quantos passaram no padrão.
PROFILES: dict[str, dict] = {
    "conservador": {"per30": 8, "score_min": 68.0, "min_gap": 90.0,
                    "allow_close": False, "max_reserve": 6},
    "balanceado": {"per30": 15, "score_min": 52.0, "min_gap": 60.0,
                   "allow_close": False, "max_reserve": 8},
    "alto_volume": {"per30": 25, "score_min": 42.0, "min_gap": 30.0,
                    "allow_close": True, "max_reserve": 12},
}


def resolve_profile(opts: dict, duration: float) -> dict:
    """Perfil efetivo deste processamento: opção do job > (no modo personalizado)
    configuração salva > valores do perfil escolhido."""
    nome = str(opts.get("profile") or settings_store.get_setting("cut_profile")
               or "balanceado")
    if nome not in PROFILES and nome != "personalizado":
        nome = "balanceado"
    base = PROFILES.get(nome, PROFILES["balanceado"])
    custom = nome == "personalizado"

    def valor(opt_key: str, setting_key: str, padrao):
        v = opts.get(opt_key)
        if v is not None:
            return v
        if custom:
            sv = settings_store.get_setting(setting_key)
            if sv not in (None, ""):
                return sv
        return padrao

    per30 = int(valor("max_cuts_per_30min", "max_cuts_per_30min", base["per30"]))
    alvo = max(3, min(60, round(duration / 60.0 / 30.0 * per30))) if duration else 10
    limite = int(valor("max_total", "max_total_cuts", 0) or 0)
    if limite:
        alvo = min(alvo, limite)
    return {
        "nome": nome,
        "target": alvo,
        "min_s": float(opts.get("min_cut_seconds")
                       or settings_store.get_setting("min_cut_seconds") or 15.0),
        "max_s": float(opts.get("max_cut_seconds")
                       or settings_store.get_setting("max_cut_seconds") or 90.0),
        "score_min": float(valor("score_min", "cut_score_min", base["score_min"])),
        "min_gap": float(valor("min_gap", "cut_min_gap", base["min_gap"])),
        "allow_close": bool(opts.get("allow_close", base["allow_close"])),
        "max_reserve": int(base["max_reserve"]),
    }


def _persist_funnel(job_id: str | None, stats: dict) -> None:
    """Grava o funil instrumentado no resultado do job (visível em /jobs e Relatórios)."""
    if not job_id:
        return
    from ..db.models import Job  # noqa: PLC0415

    try:
        with session() as s:
            j = s.get(Job, job_id)
            if j is not None:
                j.result = {**(j.result or {}), "funil": stats}
    except Exception:  # instrumentação nunca derruba o pipeline
        log.exception("Falha ao gravar funil no job")


def _ai_note(meta: dict) -> str:
    """Sufixo honesto sobre o uso de IA na mensagem final do job."""
    agent, chunks, ok = meta.get("agent"), meta.get("chunks", 0), meta.get("ia_ok", 0)
    if agent == "local":
        return " · análise local (sem IA, escolhida)"
    if not chunks:
        return ""
    rotulo = {"claude": "Claude", "gpt": "GPT"}.get(agent, agent)
    modelo = f" {meta['model']}" if meta.get("model") else ""
    if ok >= chunks:
        return f" · IA {rotulo}{modelo} em {ok}/{chunks} trechos"
    causa = f" — último erro: {meta['erro']}" if meta.get("erro") else ""
    return (f" · ATENÇÃO: IA {rotulo}{modelo} funcionou em só {ok}/{chunks} trechos; "
            f"o restante usou análise local{causa}")
