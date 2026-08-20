"""Remoção de pausas e hesitações (§5): gera uma EDL NÃO destrutiva.

A partir dos gaps entre palavras da transcrição, monta segmentos que pulam as
pausas — jump cuts que aparecem na timeline do Editor e só valem quando o
usuário salva. Pausas dramáticas (depois de "!", "?" ou reticências) são
PRESERVADAS nos níveis leve e normal: pausa depois de frase de impacto é
recurso narrativo, não defeito.

Níveis (gap mínimo para cortar):
  leve 1.2s · normal 0.8s · agressivo 0.55s (agressivo também corta as dramáticas)
"""

from __future__ import annotations

NIVEIS = {"leve": 1.2, "normal": 0.8, "agressivo": 0.55}
KEEP_BEFORE = 0.18   # respiro mantido antes da primeira palavra de cada trecho
KEEP_AFTER = 0.14    # respiro mantido depois da última palavra
DRAMATIC_END = ("!", "?", "…", "...")
MIN_SEG_S = 0.35     # trecho menor que isto funde com o vizinho
MAX_SEGMENTS = 60    # teto de segurança (60 jump cuts já é muito)


def _sem_pausas_no_trecho(words: list[dict], a: float, b: float,
                          nivel: str) -> tuple[list[dict], int]:
    thr = NIVEIS.get(nivel, NIVEIS["normal"])
    ws = [w for w in words if w["end_s"] > a and w["start_s"] < b]
    if not ws:
        return [{"src_start": round(a, 3), "src_end": round(b, 3)}], 0
    segs: list[dict] = []
    removidas = 0
    # pausa ANTES da primeira palavra
    cur_a = a
    if ws[0]["start_s"] - a > thr:
        cur_a = max(a, ws[0]["start_s"] - KEEP_BEFORE)
        removidas += 1
    prev = ws[0]
    for w in ws[1:]:
        gap = w["start_s"] - prev["end_s"]
        dramatica = prev["word"].strip().endswith(DRAMATIC_END)
        if gap > thr and not (dramatica and nivel != "agressivo") \
                and len(segs) < MAX_SEGMENTS - 1:
            segs.append({"src_start": round(cur_a, 3),
                         "src_end": round(min(b, prev["end_s"] + KEEP_AFTER), 3)})
            cur_a = max(a, w["start_s"] - KEEP_BEFORE)
            removidas += 1
        prev = w
    # pausa DEPOIS da última palavra
    fim = b
    if b - prev["end_s"] > thr:
        fim = min(b, prev["end_s"] + KEEP_AFTER)
        removidas += 1
    segs.append({"src_start": round(cur_a, 3), "src_end": round(fim, 3)})
    # funde trechos minúsculos no vizinho anterior
    limpos: list[dict] = []
    for s in segs:
        if limpos and s["src_end"] - s["src_start"] < MIN_SEG_S:
            limpos[-1]["src_end"] = s["src_end"]
        elif not limpos and s["src_end"] - s["src_start"] < MIN_SEG_S and len(segs) > 1:
            continue
        else:
            limpos.append(dict(s))
    return (limpos or segs), removidas


def edl_sem_pausas(words: list[dict], segmentos_atuais: list[tuple[float, float]],
                   nivel: str) -> tuple[dict, dict]:
    """EDL sem pausas, respeitando a edição existente: cada segmento atual da
    EDL é processado por dentro (trechos já removidos continuam removidos)."""
    novos: list[dict] = []
    removidas = 0
    for a, b in segmentos_atuais:
        segs, n = _sem_pausas_no_trecho(words, a, b, nivel)
        novos.extend(segs)
        removidas += n
    dur_antes = sum(b - a for a, b in segmentos_atuais)
    dur_depois = sum(s["src_end"] - s["src_start"] for s in novos)
    edl = {"version": 1, "segments": novos, "transition_s": 0.0}
    stats = {"removidas": removidas,
             "tempo_removido_s": round(max(0.0, dur_antes - dur_depois), 2),
             "nivel": nivel}
    return edl, stats
