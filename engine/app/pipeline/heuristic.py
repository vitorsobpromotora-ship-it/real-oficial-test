"""Scorer local (fallback sem chave de API): candidatos em torno dos picos RHPT,
com notas determinísticas nos mesmos 18 parâmetros da análise semântica.
"""

from __future__ import annotations

import unicodedata

import numpy as np

from ..schemas.claude import PARAM_KEYS
from .audio_features import Features

HOOK_PATTERNS = [
    "nunca contei", "o maior erro", "segredo", "ninguem sabe", "voce nao vai acreditar",
    "a verdade e", "o que ninguem", "eu descobri", "mudou a minha vida", "aconteceu comigo",
    "nunca mais", "pela primeira vez", "vou revelar", "?",
]
CONTROVERSY_PATTERNS = ["polemic", "discordo", "mentira", "errado", "absurdo", "nao concordo"]
HUMOR_PATTERNS = ["kkk", "haha", "rsrs", "engracado", "piada", "rindo"]


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def _find_peaks(curve: np.ndarray, hop: float, min_gap_s: float = 30.0) -> list[float]:
    """Máximos locais ordenados por altura, com distância mínima entre eles."""
    if curve.size == 0:
        return []
    order = np.argsort(curve)[::-1]
    picked: list[float] = []
    min_gap = min_gap_s / hop
    for idx in order:
        if all(abs(idx - p / hop) >= min_gap for p in picked):
            picked.append(float(idx * hop))
        if len(picked) >= 200:
            break
    return picked


def analyze_heuristic(sentences: list[dict], features: Features, target_count: int,
                      min_s: float, max_s: float, duration: float) -> list[dict]:
    """`sentences`: [{"start_s","end_s","text"}]. Retorna candidatos brutos (dict)."""
    if not sentences:
        return []
    peaks = _find_peaks(features.peak_curve, features.hop)
    riso_ts = [e["t"] for e in features.events if e["type"] == "riso"]
    cands: list[dict] = []
    for t in peaks[: target_count * 4]:
        start = max(0.0, t - 20.0)
        end = min(duration, t + 25.0)
        window = [s for s in sentences if s["end_s"] > start and s["start_s"] < end]
        if not window:
            continue
        c_start, c_end = window[0]["start_s"], window[-1]["end_s"]
        if c_end - c_start < min_s or c_end - c_start > max_s * 1.5:
            # janela será re-ajustada no snap; ignora casos extremos
            if c_end - c_start < min_s * 0.5:
                continue
        text_norm = _norm(" ".join(s["text"] for s in window))
        first = window[0]["text"].strip()
        peak_max, peak_mean = features.peak_between(c_start, c_end)

        params = dict.fromkeys(PARAM_KEYS, 5.0)
        params["energy"] = round(min(10.0, 4.0 + peak_max * 6.0), 2)
        params["emotional_intensity"] = round(min(10.0, 3.5 + peak_mean * 6.5), 2)
        params["hook_strength"] = 8.0 if any(p in _norm(first) for p in HOOK_PATTERNS) else (
            6.5 if any(p in text_norm for p in HOOK_PATTERNS) else 5.0)
        params["humor"] = 8.0 if any(c_start <= t_ <= c_end for t_ in riso_ts) else (
            6.5 if any(p in text_norm for p in HUMOR_PATTERNS) else 4.0)
        params["controversy"] = 7.0 if any(p in text_norm for p in CONTROVERSY_PATTERNS) else 4.0
        params["completeness"] = 7.0
        params["context_independence"] = 6.0
        params["quotability"] = params["hook_strength"] - 1.0
        params["title_potential"] = params["hook_strength"]

        cands.append({
            "start_s": round(c_start, 3), "end_s": round(c_end, 3), "params": params,
            "hook_line": first[:200],
            "title": (first[:57] + "…") if len(first) > 58 else first,
            "hashtags": ["#cortes", "#podcast", "#viral"],
            "reason": "Pico de intensidade de áudio detectado (análise local, sem IA)",
            "verdict": "revisar",
            "analysis": {
                "gancho": f"Abertura detectada: “{first[:120]}”. Sem avaliação editorial de IA.",
                "desenvolvimento": "Trecho selecionado por picos de energia/ritmo no áudio.",
                "conclusao": "Alinhado ao fim de frase mais próximo — confira se há payoff.",
                "ponto_forte": "Momento de maior intensidade sonora do trecho.",
                "ponto_fraco": "Análise local não avalia conteúdo/contexto — revisão manual é essencial.",
                "sugestao": "Configure a chave de API em Configurações para análise editorial completa.",
                "publico": "",
            },
            "origin": "heuristic",
        })
        if len(cands) >= target_count * 3:
            break
    return cands
