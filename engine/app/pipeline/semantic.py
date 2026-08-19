"""Análise semântica com Claude: chunking da transcrição, prompt com anotações RHPT,
escada de fallback (modelo primário → fallback → heurística local) e modo Batches (−50%).
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor

from ..db import settings_store
from ..schemas.claude import ChunkAnalysis, strict_chunk_schema
from ..services.agents import AGENT_LABELS, build_client, resolve_agent
from ..services.ai_usage import friendly_ai_error
from ..services.claude_client import RefusalError, SemanticClient
from .audio_features import Features
from .heuristic import analyze_heuristic

log = logging.getLogger(__name__)

CHUNK_SECONDS = 720.0  # ~12 min
CHUNK_OVERLAP = 60.0

SYSTEM_PROMPT = """Você é um editor sênior de cortes virais para TikTok, Reels e Shorts, \
especializado em conteúdo brasileiro (podcasts, entrevistas, lives e aulas). Seu trabalho \
é encontrar cortes E entregar uma análise editorial que ajude o criador a DECIDIR o que postar.

Você receberá um trecho de transcrição com timestamps por frase no formato \
[hh:mm:ss–hh:mm:ss], seguido de SINAIS DE ÁUDIO detectados automaticamente \
(picos de energia, risadas, pausas) e da quantidade de segmentos esperada.

Regras de seleção:
- start_s e end_s em SEGUNDOS ABSOLUTOS do vídeo original (converta dos timestamps).
- Cada segmento deve durar entre 15 e 90 segundos, começar em início de frase e terminar em \
fim de frase, formando uma unidade compreensível SOZINHA: gancho → desenvolvimento → payoff.
- Nunca comece em "Então, como eu estava dizendo" ou frases que dependem de contexto anterior.
- Prefira aberturas com gancho forte: revelação, pergunta provocativa, número, opinião firme.
- Considere os SINAIS DE ÁUDIO: pico de energia ou risada dentro do segmento é bom sinal.
- Se o trecho realmente não tiver momentos bons, retorne menos segmentos — não invente.

CALIBRAÇÃO DOS 18 PARÂMETROS (notas 0–10) — seja honesto e use a régua inteira:
- 0–3 = fraco (não contribui), 4–5 = mediano, 6–7 = bom, 8–9 = excelente, 10 = raro/excepcional.
- NÃO agrupe tudo em 5–7: um corte comum de conversa técnica tem humor 1–2, controversy 2–3, \
tension 3–4. Notas diferentes entre parâmetros são esperadas e desejadas.
- Parâmetros: hook_strength (3 primeiros segundos), emotional_intensity, humor, tension, \
completeness (tem conclusão?), context_independence (funciona sem contexto?), clarity, \
information_value, storytelling, controversy, relatability, quotability, novelty, energy, \
cta_potential, loopability, title_potential, niche_fit.

VEREDITO (verdict) — a decisão que o criador precisa:
- "postar": publicável como está; gancho forte e unidade completa.
- "revisar": tem potencial, mas precisa de um ajuste específico (diga qual em analysis.sugestao).
- "descartar": fraco para short-form; explique o porquê em analysis.ponto_fraco.

ANÁLISE EDITORIAL (analysis) — específica deste trecho, em PT-BR, SEMPRE citando a fala real \
entre aspas; nada de frases genéricas que serviriam para qualquer vídeo:
- gancho: avalie os 3 primeiros segundos citando a primeira fala.
- desenvolvimento: como o trecho segura a atenção no meio (ritmo, exemplos, tensão).
- conclusao: o fechamento entrega payoff? Qual?
- ponto_forte: o maior motivo para postar ESTE corte.
- ponto_fraco: o maior risco/fraqueza dele.
- sugestao: UM ajuste concreto (ex.: "corte os 2s iniciais e comece direto em '...'").
- publico: para quem este corte performa melhor.

Campos restantes:
- hook_line: a primeira frase falada do segmento, exatamente como na transcrição.
- title: título chamativo em português (máx. 60 caracteres, sem clickbait mentiroso).
- hashtags: 3 a 5, em português, começando com #.
- reason: 1 frase-resumo do potencial (aparece na listagem)."""


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


def segment_range_for(chunk: dict) -> tuple[int, int]:
    """Quantos segmentos pedir por chunk: ~1 corte a cada 2 min de conteúdo."""
    minutes = max(1.0, (chunk["end"] - chunk["start"]) / 60.0)
    lo = max(2, round(minutes / 3))
    hi = max(lo + 2, min(10, round(minutes / 1.5)))
    return lo, hi


def render_chunk_prompt(chunk: dict, features: Features | None) -> str:
    lo, hi = segment_range_for(chunk)
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
    lines += ["", f"Identifique entre {lo} e {hi} segmentos para cortes verticais, avalie os "
              "18 parâmetros com calibração honesta, dê o veredito e a análise editorial de cada um."]
    return "\n".join(lines)


def _segments_to_dicts(analysis: ChunkAnalysis, origin: str) -> list[dict]:
    out = []
    for seg in analysis.segments:
        if seg.end_s <= seg.start_s:
            continue
        verdict = seg.verdict if seg.verdict in ("postar", "revisar", "descartar") else "revisar"
        out.append({
            "start_s": float(seg.start_s), "end_s": float(seg.end_s),
            "params": seg.params.model_dump(), "hook_line": seg.hook_line,
            "title": seg.title, "hashtags": list(seg.hashtags),
            "reason": seg.reason, "verdict": verdict,
            "analysis": seg.analysis.model_dump(), "origin": origin,
        })
    return out


def _chunk_ladder(client, fallback_model: str | None, chunk: dict,
                  features: Features | None, sentences_fallback_fn, *,
                  source_video_id: str | None, job_id: str | None,
                  origin: str = "claude") -> tuple[list[dict], bool, str | None]:
    """Escada: modelo primário → modelo fallback → heurística local no chunk.

    Retorna (candidatos, ia_ok, erro): o chamador decide se degradação parcial é
    aceitável — falha TOTAL de IA nunca pode virar heurística silenciosa."""
    last_error: str | None = None
    if client is not None:
        prompt = render_chunk_prompt(chunk, features)
        for model in (None, fallback_model):
            try:
                analysis = client.analyze_chunk(SYSTEM_PROMPT, prompt, model=model,
                                                source_video_id=source_video_id, job_id=job_id)
                return _segments_to_dicts(analysis, origin), True, None
            except RefusalError as exc:
                last_error = str(exc)
                log.warning("Chunk %s–%s: %s", fmt_ts(chunk["start"]), fmt_ts(chunk["end"]), exc)
                if model == fallback_model or not fallback_model:
                    break
            except Exception as exc:  # rede/parse/rate-limit após retries do SDK
                last_error = friendly_ai_error(exc)
                log.warning("Chunk %s–%s falhou no modelo %s: %s",
                            fmt_ts(chunk["start"]), fmt_ts(chunk["end"]), model or "primário", exc)
                if model == fallback_model or not fallback_model:
                    break
    return sentences_fallback_fn(chunk), False, last_error


def analyze_semantic(ctx, source_video_id: str, sentences: list[dict], features: Features,
                     duration: float, report, *, min_s: float, max_s: float,
                     target_count: int, agent: str | None = None) -> tuple[list[dict], dict]:
    """Analisa todos os chunks com o AGENTE escolhido (claude|gpt|local).

    Retorna (candidatos brutos, meta) com meta = {agent, model, chunks, ia_ok, erro}.
    IA explicitamente escolhida que falha em TODOS os chunks interrompe o job com
    o erro real — nunca degrada silenciosamente para a heurística."""
    from ..services.agents import agent_api_key

    explicit = agent
    agent = resolve_agent(agent)
    if explicit is None and agent in ("claude", "gpt") and not agent_api_key(agent):
        agent = "local"  # job legado sem escolha explícita e sem chave → local honesto
    use_batches = bool(settings_store.get_setting("use_batches"))

    chunks = build_chunks(sentences, duration)
    meta = {"agent": agent, "model": "", "chunks": len(chunks), "ia_ok": 0, "erro": None}
    if not chunks:
        return [], meta

    def heuristic_for_chunk(chunk: dict) -> list[dict]:
        per_chunk = max(2, round(target_count * (chunk["end"] - chunk["start"]) / max(duration, 1)))
        return analyze_heuristic(chunk["sentences"], features, per_chunk, min_s, max_s, duration)

    if agent == "local":
        report(0.05, "Análise local (escolhida) — sem IA")
        out: list[dict] = []
        for i, chunk in enumerate(chunks):
            ctx.check_cancel()
            out.extend(heuristic_for_chunk(chunk))
            report((i + 1) / len(chunks), "Análise local…")
        return out, meta

    # claude | gpt: sem chave → erro claro imediato (job falha, usuário vê o motivo)
    client, fallback_model, model = build_client(agent)
    meta["model"] = model

    if agent == "claude" and use_batches and len(chunks) > 1:
        raw, ok_chunks = _analyze_batches(ctx, client, fallback_model, chunks, features,
                                          heuristic_for_chunk, source_video_id, report)
        meta["ia_ok"] = ok_chunks
        if raw and meta["ia_ok"] == 0:
            raise RuntimeError(
                f"A análise com {AGENT_LABELS[agent]} (modo econômico) falhou em todos os "
                f"trechos. Verifique a chave e os créditos em Configurações.")
        return raw, meta

    results: list[list[dict]] = [[] for _ in chunks]
    ok_flags: list[bool] = [False] * len(chunks)
    errors: list[str] = []
    done = 0
    rotulo = AGENT_LABELS[agent]

    def work(idx_chunk):
        idx, chunk = idx_chunk
        cands, ok, err = _chunk_ladder(client, fallback_model, chunk, features,
                                       heuristic_for_chunk, source_video_id=source_video_id,
                                       job_id=ctx.job_id, origin=agent)
        return idx, cands, ok, err

    with ThreadPoolExecutor(max_workers=2) as pool:
        for idx, cands, ok, err in pool.map(work, enumerate(chunks)):
            ctx.check_cancel()
            results[idx] = cands
            ok_flags[idx] = ok
            if err:
                errors.append(err)
            done += 1
            report(done / len(chunks), f"Análise com {rotulo}… trecho {done}/{len(chunks)}")

    meta["ia_ok"] = sum(ok_flags)
    meta["erro"] = errors[0] if errors else None
    if meta["ia_ok"] == 0:
        raise RuntimeError(
            f"A análise com {rotulo} falhou em todos os {len(chunks)} trechos e o "
            f"processamento foi interrompido. Causa: {meta['erro'] or 'desconhecida'}. "
            f"Use 'Testar' em Configurações para diagnosticar, ou escolha o agente "
            f"'Análise local' para processar sem IA.")
    return [c for chunk_res in results for c in chunk_res], meta


def _analyze_batches(ctx, client: SemanticClient, fallback_model: str | None, chunks: list[dict],
                     features: Features, heuristic_for_chunk, source_video_id: str,
                     report) -> tuple[list[dict], int]:
    """Modo econômico (só Claude): Message Batches API (−50%), saída validada manualmente.

    Retorna (candidatos, nº de chunks analisados com IA)."""
    schema = strict_chunk_schema()
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
            out.extend(_segments_to_dicts(analysis, "claude"))
    for i, chunk in enumerate(chunks):  # chunks que falharam no lote caem na heurística
        if i not in ok_ids:
            out.extend(heuristic_for_chunk(chunk))
    report(1.0, "Lote concluído")
    return out, len(ok_ids)
