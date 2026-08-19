"""Análise semântica com Claude: chunking da transcrição, prompt com anotações RHPT,
escada de fallback (modelo primário → fallback → heurística local) e modo Batches (−50%).
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor

from ..db import settings_store
from ..schemas.claude import ChunkAnalysis
from ..services.claude_client import RefusalError, SemanticClient
from .audio_features import Features
from .heuristic import analyze_heuristic

log = logging.getLogger(__name__)

CHUNK_SECONDS = 720.0  # ~12 min
CHUNK_OVERLAP = 60.0

SYSTEM_PROMPT = """Você é um editor sênior de cortes virais para TikTok, Reels e Shorts, \
especializado em conteúdo brasileiro (podcasts, entrevistas, lives e aulas).

Você receberá um trecho de transcrição com timestamps por frase no formato \
[hh:mm:ss–hh:mm:ss], seguido de SINAIS DE ÁUDIO detectados automaticamente \
(picos de energia, risadas, pausas).

Sua tarefa: identificar de 2 a 6 segmentos deste trecho com maior potencial de virar \
um corte vertical de 15 a 90 segundos.

Regras obrigatórias:
- start_s e end_s em SEGUNDOS ABSOLUTOS do vídeo original (converta dos timestamps).
- O segmento deve começar em início de frase e terminar em fim de frase, formando uma \
unidade compreensível SOZINHA: gancho → desenvolvimento → conclusão/payoff.
- Nunca comece em "Então, como eu estava dizendo" ou frases que dependem de contexto anterior.
- Prefira aberturas com gancho forte: revelação, pergunta provocativa, número, história pessoal.
- Avalie cada segmento nos 18 parâmetros (notas 0–10):
  hook_strength (força do gancho nos 3 primeiros segundos), emotional_intensity, humor, \
tension, completeness (tem conclusão?), context_independence (funciona sem contexto?), \
clarity, information_value, storytelling, controversy, relatability, quotability, novelty, \
energy, cta_potential, loopability, title_potential, niche_fit.
- hook_line: a primeira frase falada do segmento, exatamente como na transcrição.
- title: título chamativo em português (máx. 60 caracteres, sem clickbait mentiroso).
- hashtags: 3 a 5, em português, começando com #.
- reason: 1 frase explicando por que esse trecho tem potencial.
- Se o trecho não tiver nenhum momento bom, retorne segments vazio — não invente.
- Considere os SINAIS DE ÁUDIO: um pico de energia ou risada dentro do segmento é bom sinal."""


def fmt_ts(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def build_chunks(sentences: list[dict], duration: float,
                 chunk_s: float = CHUNK_SECONDS, overlap_s: float = CHUNK_OVERLAP) -> list[dict]:
    """Agrupa frases em janelas de ~chunk_s com overlap. [{"start","end","sentences"}]"""
    if not sentences:
        return []
    chunks: list[dict] = []
    i = 0
    n = len(sentences)
    while i < n:
        start_t = sentences[i]["start_s"]
        j = i
        while j < n and sentences[j]["end_s"] - start_t <= chunk_s:
            j += 1
        j = max(j, i + 1)
        chunk_sents = sentences[i:j]
        chunks.append({"start": start_t, "end": chunk_sents[-1]["end_s"], "sentences": chunk_sents})
        if j >= n:
            break
        # próximo chunk recua para garantir overlap
        back = j
        while back > i + 1 and sentences[back - 1]["start_s"] > chunk_sents[-1]["end_s"] - overlap_s:
            back -= 1
        i = max(back, i + 1)
    return chunks


def render_chunk_prompt(chunk: dict, features: Features | None) -> str:
    lines = [f"TRECHO DA TRANSCRIÇÃO ({fmt_ts(chunk['start'])} a {fmt_ts(chunk['end'])}):", ""]
    for s in chunk["sentences"]:
        lines.append(f"[{fmt_ts(s['start_s'])}–{fmt_ts(s['end_s'])}] {s['text']}")
    if features is not None:
        evs = [e for e in features.events if chunk["start"] <= e["t"] <= chunk["end"]]
        if evs:
            lines += ["", "SINAIS DE ÁUDIO:"]
            for e in evs[:40]:
                lines.append(f"- t={fmt_ts(e['t'])} tipo={e['type']} intensidade={e['intensity']:.2f}")
        pauses = [p for p in features.pauses if chunk["start"] <= p[0] <= chunk["end"]]
        if pauses:
            lines.append(f"- pausas longas em: {', '.join(fmt_ts(p[0]) for p in pauses[:20])}")
    lines += ["", "Identifique os melhores segmentos para cortes verticais e avalie os 18 parâmetros."]
    return "\n".join(lines)


def _chunk_ladder(client: SemanticClient | None, fallback_model: str | None, chunk: dict,
                  features: Features | None, sentences_fallback_fn, *,
                  source_video_id: str | None, job_id: str | None) -> list[dict]:
    """Escada: modelo primário → modelo fallback → heurística local no chunk."""
    if client is not None:
        prompt = render_chunk_prompt(chunk, features)
        for model in (None, fallback_model):
            try:
                analysis = client.analyze_chunk(SYSTEM_PROMPT, prompt, model=model,
                                                source_video_id=source_video_id, job_id=job_id)
                out = []
                for seg in analysis.segments:
                    if seg.end_s <= seg.start_s:
                        continue
                    out.append({
                        "start_s": float(seg.start_s), "end_s": float(seg.end_s),
                        "params": seg.params.model_dump(), "hook_line": seg.hook_line,
                        "title": seg.title, "hashtags": list(seg.hashtags),
                        "reason": seg.reason, "origin": "claude",
                    })
                return out
            except RefusalError as exc:
                log.warning("Chunk %s–%s: %s", fmt_ts(chunk["start"]), fmt_ts(chunk["end"]), exc)
                if model == fallback_model or not fallback_model:
                    break
            except Exception as exc:  # rede/parse/rate-limit após retries do SDK
                log.warning("Chunk %s–%s falhou no modelo %s: %s",
                            fmt_ts(chunk["start"]), fmt_ts(chunk["end"]), model or "primário", exc)
                if model == fallback_model or not fallback_model:
                    break
    return sentences_fallback_fn(chunk)


def analyze_semantic(ctx, source_video_id: str, sentences: list[dict], features: Features,
                     duration: float, report, *, min_s: float, max_s: float,
                     target_count: int) -> list[dict]:
    """Retorna candidatos brutos de todos os chunks (Claude quando possível, senão heurística)."""
    api_key = settings_store.get_setting("anthropic_api_key") or ""
    model = settings_store.get_setting("claude_model") or "claude-opus-5"
    fallback_model = settings_store.get_setting("claude_fallback_model") or "claude-sonnet-5"
    use_batches = bool(settings_store.get_setting("use_batches"))

    chunks = build_chunks(sentences, duration)
    if not chunks:
        return []

    def heuristic_for_chunk(chunk: dict) -> list[dict]:
        per_chunk = max(2, round(target_count * (chunk["end"] - chunk["start"]) / max(duration, 1)))
        return analyze_heuristic(chunk["sentences"], features, per_chunk, min_s, max_s, duration)

    if not api_key:
        report(0.5, "Sem chave de API — usando análise local (heurística)")
        out: list[dict] = []
        for i, chunk in enumerate(chunks):
            ctx.check_cancel()
            out.extend(heuristic_for_chunk(chunk))
            report((i + 1) / len(chunks), "Análise local…")
        return out

    client = SemanticClient(api_key, model)
    if use_batches and len(chunks) > 1:
        return _analyze_batches(ctx, client, fallback_model, chunks, features,
                                heuristic_for_chunk, source_video_id, report)

    results: list[list[dict]] = [[] for _ in chunks]
    done = 0

    def work(idx_chunk):
        idx, chunk = idx_chunk
        return idx, _chunk_ladder(client, fallback_model, chunk, features, heuristic_for_chunk,
                                  source_video_id=source_video_id, job_id=ctx.job_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        for idx, res in pool.map(work, enumerate(chunks)):
            ctx.check_cancel()
            results[idx] = res
            done += 1
            report(done / len(chunks), f"Análise com IA… chunk {done}/{len(chunks)}")
    return [c for chunk_res in results for c in chunk_res]


def _analyze_batches(ctx, client: SemanticClient, fallback_model: str | None, chunks: list[dict],
                     features: Features, heuristic_for_chunk, source_video_id: str,
                     report) -> list[dict]:
    """Modo econômico: Message Batches API (−50%), saída estruturada validada manualmente."""
    schema = ChunkAnalysis.model_json_schema()
    requests = []
    for i, chunk in enumerate(chunks):
        requests.append({
            "custom_id": str(i),
            "params": {
                "model": client.model,
                "max_tokens": 16000,
                "system": [{"type": "text", "text": SYSTEM_PROMPT,
                            "cache_control": {"type": "ephemeral"}}],
                "messages": [{"role": "user", "content": render_chunk_prompt(chunk, features)}],
                "output_config": {"format": {"type": "json_schema", "schema": schema}},
            },
        })
    report(0.05, f"Enviando lote de {len(chunks)} chunks (modo econômico)…")
    batch = client.client.messages.batches.create(requests=requests)
    while True:
        ctx.check_cancel()
        time.sleep(20)
        batch = client.client.messages.batches.retrieve(batch.id)
        counts = batch.request_counts
        total = len(chunks)
        finished = (counts.succeeded or 0) + (counts.errored or 0) + \
                   (counts.canceled or 0) + (counts.expired or 0)
        report(0.05 + 0.85 * finished / total, f"Lote processando… {finished}/{total}")
        if batch.processing_status == "ended":
            break
    out: list[dict] = []
    ok_ids: set[int] = set()
    for result in client.client.messages.batches.results(batch.id):
        idx = int(result.custom_id)
        if result.result.type == "succeeded":
            msg = result.result.message
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            try:
                analysis = ChunkAnalysis.model_validate_json(text)
            except Exception:
                continue
            ok_ids.add(idx)
            for seg in analysis.segments:
                if seg.end_s > seg.start_s:
                    out.append({"start_s": float(seg.start_s), "end_s": float(seg.end_s),
                                "params": seg.params.model_dump(), "hook_line": seg.hook_line,
                                "title": seg.title, "hashtags": list(seg.hashtags),
                                "reason": seg.reason, "origin": "claude"})
    for i, chunk in enumerate(chunks):  # chunks que falharam no lote caem na heurística
        if i not in ok_ids:
            out.extend(heuristic_for_chunk(chunk))
    report(1.0, "Lote concluído")
    return out
