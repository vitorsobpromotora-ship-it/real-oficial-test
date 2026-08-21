"""EDL — Edit Decision List: o modelo de edição NÃO DESTRUTIVA de um corte.

O arquivo original nunca é modificado. Cada corte pode carregar uma EDL
persistida (cut.edl) descrevendo a linha do tempo de saída como uma sequência
de segmentos do vídeo-fonte, mais fades e ajustes de áudio:

    {
      "version": 1,
      "segments": [{"src_start": 12.0, "src_end": 24.5}, ...],   # ordem = saída
      "fade_in_s": 0.0, "fade_out_s": 0.0,                        # vídeo global
      "transition_s": 0.12,          # fade rápido nas junções internas (0 = corte seco)
      "audio": {"gain_db": 0.0, "mute": false,
                "fade_in_s": 0.0, "fade_out_s": 0.0}
    }

Cortes sem EDL usam a implícita [{start_s → end_s}] — 100% compatível com tudo
que já existia. A MESMA EDL alimenta prévia e render final (a única diferença
permitida entre eles é resolução/preset de encoding), e é ela que dirige o
remapeamento de legendas, censura e enquadramento para o tempo de saída.
"""

from __future__ import annotations

EDL_VERSION = 1
DEFAULT_TRANSITION_S = 0.12


def cut_edl(cut: dict) -> dict:
    """EDL efetiva do corte: a persistida (normalizada) ou a implícita."""
    edl = dict(cut.get("edl") or {})
    segs = edl.get("segments") or []
    if not segs:
        segs = [{"src_start": float(cut["start_s"]), "src_end": float(cut["end_s"])}]
    norm = []
    for s in segs:
        a, b = float(s["src_start"]), float(s["src_end"])
        if b - a > 0.04:
            norm.append({"src_start": round(a, 3), "src_end": round(b, 3)})
    if not norm:
        norm = [{"src_start": float(cut["start_s"]), "src_end": float(cut["end_s"])}]
    audio = dict(edl.get("audio") or {})
    return {
        "version": EDL_VERSION,
        "segments": norm,
        "fade_in_s": max(0.0, float(edl.get("fade_in_s") or 0.0)),
        "fade_out_s": max(0.0, float(edl.get("fade_out_s") or 0.0)),
        "transition_s": max(0.0, float(edl.get("transition_s", 0.0) or 0.0)),
        "audio": {
            "gain_db": float(audio.get("gain_db") or 0.0),
            "mute": bool(audio.get("mute") or False),
            "fade_in_s": max(0.0, float(audio.get("fade_in_s") or 0.0)),
            "fade_out_s": max(0.0, float(audio.get("fade_out_s") or 0.0)),
        },
    }


def segments_of(edl: dict) -> list[tuple[float, float]]:
    return [(s["src_start"], s["src_end"]) for s in edl["segments"]]


def envelope(edl: dict) -> tuple[float, float]:
    segs = segments_of(edl)
    return min(a for a, _ in segs), max(b for _, b in segs)


def out_duration(edl: dict) -> float:
    return round(sum(b - a for a, b in segments_of(edl)), 3)


def validate_edl(edl_in: dict, src_duration: float | None) -> list[str]:
    """Erros de uma EDL enviada pelo editor (lista vazia = ok)."""
    erros: list[str] = []
    segs = (edl_in or {}).get("segments") or []
    if not segs:
        erros.append("EDL precisa de pelo menos um segmento")
        return erros
    for i, s in enumerate(segs):
        try:
            a, b = float(s["src_start"]), float(s["src_end"])
        except (KeyError, TypeError, ValueError):
            erros.append(f"segmento {i + 1}: src_start/src_end inválidos")
            continue
        if b <= a:
            erros.append(f"segmento {i + 1}: fim deve ser maior que início")
        if a < 0:
            erros.append(f"segmento {i + 1}: início negativo")
        if src_duration and b > src_duration + 0.5:
            erros.append(f"segmento {i + 1}: fim além da duração do vídeo")
    if out_duration(cut_edl({"edl": edl_in, "start_s": 0, "end_s": 1})) < 1.0 and not erros:
        erros.append("duração total da edição menor que 1s")
    return erros


def src_to_out(edl: dict, t_src: float) -> float | None:
    """Mapeia um instante do vídeo-fonte para o tempo de saída (None se removido)."""
    acc = 0.0
    for a, b in segments_of(edl):
        if a <= t_src <= b:
            return round(acc + (t_src - a), 3)
        acc += b - a
    return None


def map_words(words_src: list[dict], edl: dict, edits: dict | None = None) -> list[dict]:
    """Palavras (tempos da FONTE) → tempos de SAÍDA, descartando as que caem em
    trechos removidos, e aplicando a CAMADA DE LEGENDA do corte (Ponto 14):
    a transcrição original nunca muda; o corte guarda em `edits`:

      word_overrides  {"<idx>": "texto"}  — substituir (mesma janela temporal)
      word_deleted    [idx, ...]          — excluir da legenda (não da fala)
      word_inserted   [{"id","anchor_idx","placement":"before|after","text"}]
                       — inseridas ANCORADAS à palavra vizinha: aproveitam a
                         pausa disponível ou dividem a janela da âncora, sem
                         deslocar nenhuma outra palavra."""
    overrides = (edits or {}).get("word_overrides") or {}
    fonte = (edits or {}).get("caption_words") or words_src
    out: list[dict] = []
    acc = 0.0
    for a, b in segments_of(edl):
        for w in fonte:
            if w["end_s"] <= a or w["start_s"] >= b:
                continue
            texto = overrides.get(str(w.get("idx", ""))) or w["word"]
            out.append({"idx": w.get("idx"),
                        "start_s": round(acc + max(0.0, w["start_s"] - a), 3),
                        "end_s": round(acc + min(b, w["end_s"]) - a, 3),
                        "word": texto})
        acc += b - a
    return _apply_word_edits(out, edits)


def _apply_word_edits(words: list[dict], edits: dict | None) -> list[dict]:
    if not edits:
        return words
    deleted = {int(i) for i in (edits.get("word_deleted") or [])}
    if deleted:
        words = [w for w in words if w.get("idx") not in deleted]
    for ins in edits.get("word_inserted") or []:
        words = _insert_word(words, ins)
    return words


def _insert_word(words: list[dict], ins: dict) -> list[dict]:
    """Insere uma palavra antes/depois da âncora SEM deslocar as demais.

    Pausa vizinha ≥0.18s → a inserida vive na pausa; senão a janela da âncora
    é dividida visualmente (só a âncora encolhe — o resto fica intacto)."""
    texto = (ins.get("text") or "").strip()
    if not texto:
        return words
    pos = next((i for i, w in enumerate(words)
                if w.get("idx") == ins.get("anchor_idx") and w.get("idx") is not None), None)
    if pos is None:
        return words
    out = [dict(w) for w in words]
    a = out[pos]
    dur = a["end_s"] - a["start_s"]
    if ins.get("placement") == "before":
        prev_end = out[pos - 1]["end_s"] if pos > 0 else 0.0
        gap = a["start_s"] - prev_end
        if gap >= 0.18:
            s = max(prev_end, a["start_s"] - min(gap * 0.8, 0.5))
            e = a["start_s"] - 0.01
        else:
            s = a["start_s"]
            e = a["start_s"] + max(0.08, dur * 0.45)
            a["start_s"] = round(e, 3)
        novo = {"idx": None, "ins_id": ins.get("id"), "start_s": round(max(0.0, s), 3),
                "end_s": round(e, 3), "word": texto}
        out.insert(pos, novo)
    else:
        nxt_start = out[pos + 1]["start_s"] if pos + 1 < len(out) else a["end_s"] + 0.6
        gap = nxt_start - a["end_s"]
        if gap >= 0.18:
            s = a["end_s"] + 0.01
            e = min(nxt_start, a["end_s"] + min(gap * 0.8, 0.5))
        else:
            e = a["end_s"]
            s = a["end_s"] - max(0.08, dur * 0.45)
            a["end_s"] = round(s, 3)
        novo = {"idx": None, "ins_id": ins.get("id"), "start_s": round(s, 3),
                "end_s": round(e, 3), "word": texto}
        out.insert(pos + 1, novo)
    return out


def map_intervals(intervals_src: list[dict], edl: dict) -> list[dict]:
    """Intervalos de censura (tempos da FONTE) → tempos de SAÍDA, fatiados por segmento."""
    out: list[dict] = []
    acc = 0.0
    for a, b in segments_of(edl):
        for i in intervals_src:
            s, e = max(i["start"], a), min(i["end"], b)
            if e - s > 0.02:
                out.append({"start": round(acc + (s - a), 3), "end": round(acc + (e - a), 3)})
        acc += b - a
    return out


def _x_at(seg: dict, t: float) -> float:
    """Posição x interpolada do plano de crop no instante t (tempo da fonte)."""
    d = max(0.001, seg["end"] - seg["start"])
    f = min(1.0, max(0.0, (t - seg["start"]) / d))
    return seg["x0"] + (seg["x1"] - seg["x0"]) * f


def slice_crop_plan(crop_plan: dict, edl: dict) -> dict:
    """Fatia o plano de crop (tempos da FONTE) pelos segmentos da EDL e devolve
    um plano em TEMPOS DE SAÍDA contíguos — pronto para o filtergraph.

    Cada pedaço carrega os dois relógios: "start"/"end" no tempo de SAÍDA e
    "src_start"/"src_end" no tempo da FONTE (é com estes que o ffmpeg faz o
    trim do input). Também anota o índice do segmento EDL de origem
    ("edl_seg"), para as transições de junção saberem onde aplicar fades."""
    if crop_plan.get("mode") in ("blur_pad", "fit_pad", "two_person", "split_screen"):
        return {**crop_plan, "segments": []}  # modos sem linha do tempo de crop
    pieces: list[dict] = []
    acc = 0.0
    plan_segs = crop_plan.get("segments") or []
    for idx, (a, b) in enumerate(segments_of(edl)):
        cobertos = [p for p in plan_segs if p["end"] > a and p["start"] < b] or \
                   [{"start": a, "end": b,
                     "x0": plan_segs[0]["x0"] if plan_segs else 0,
                     "x1": plan_segs[0]["x0"] if plan_segs else 0}]
        locais: list[dict] = []
        for p in cobertos:
            s, e = max(p["start"], a), min(p["end"], b)
            if e - s <= 0.04:
                continue
            piece = {"src_start": s, "src_end": e,
                     "x0": int(round(_x_at(p, s))), "x1": int(round(_x_at(p, e))),
                     "edl_seg": idx}
            if p.get("zoom"):
                piece["zoom"] = p["zoom"]  # punch-in sobrevive ao fatiamento da EDL
            locais.append(piece)
        if not locais:
            x = int(plan_segs[0]["x0"]) if plan_segs else 0
            locais = [{"src_start": a, "src_end": b, "x0": x, "x1": x, "edl_seg": idx}]
        # cada segmento da EDL precisa ficar 100% coberto, sem buracos internos
        locais[0]["src_start"] = a
        for prev, nxt in zip(locais, locais[1:], strict=False):
            nxt["src_start"] = prev["src_end"]
        locais[-1]["src_end"] = b
        for piece in locais:
            piece["start"] = round(acc + (piece["src_start"] - a), 3)
            piece["end"] = round(acc + (piece["src_end"] - a), 3)
            piece["src_start"] = round(piece["src_start"], 3)
            piece["src_end"] = round(piece["src_end"], 3)
        pieces.extend(locais)
        acc += b - a
    # contiguidade exata na SAÍDA (arredondamentos não podem abrir buracos no concat)
    pieces[0]["start"] = 0.0
    for prev, nxt in zip(pieces, pieces[1:], strict=False):
        nxt["start"] = prev["end"]
    pieces[-1]["end"] = out_duration(edl)
    return {**crop_plan, "segments": pieces}


def edl_clamped(edl_in: dict | None, a: float, b: float) -> dict | None:
    """Ajusta uma EDL persistida a um novo envelope [a, b] (trim rápido feito
    fora do Editor): segmentos fora do intervalo caem, os das bordas são
    aparados. Devolve None se nada sobrar — o corte volta ao modo simples."""
    if not edl_in:
        return None
    segs = []
    for s in edl_in.get("segments") or []:
        s0, s1 = max(float(s["src_start"]), a), min(float(s["src_end"]), b)
        if s1 - s0 > 0.04:
            segs.append({"src_start": round(s0, 3), "src_end": round(s1, 3)})
    if not segs:
        return None
    return {**edl_in, "version": EDL_VERSION, "segments": segs}


def audio_chunks(edl: dict, offset: float) -> list[dict]:
    """Trechos de áudio (tempos RELATIVOS ao offset de input do ffmpeg)."""
    out = []
    for a, b in segments_of(edl):
        out.append({"start": round(a - offset, 3), "end": round(b - offset, 3)})
    return out
