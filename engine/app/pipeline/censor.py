"""Censura de palavrões: casa palavras da transcrição (normalizadas) contra a wordlist
PT-BR (+ adições do usuário) e produz intervalos de mute/beep com padding.
Entradas com '*' final casam por prefixo (ex.: "fod*" → "foder", "fodido").
"""

from __future__ import annotations

import unicodedata

from .. import config

PAD_S = 0.06


def _norm(word: str) -> str:
    word = unicodedata.normalize("NFD", word.lower().strip())
    word = "".join(c for c in word if unicodedata.category(c) != "Mn")
    return "".join(c for c in word if c.isalnum())


def load_wordlist(extra_words: list[str] | None = None) -> tuple[set[str], list[str]]:
    """Retorna (exatas, prefixos)."""
    exact: set[str] = set()
    prefixes: list[str] = []
    path = config.ASSETS_DIR / "censor_wordlist_ptbr.txt"
    entries: list[str] = []
    if path.exists():
        entries += [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()
                    if ln.strip() and not ln.startswith("#")]
    entries += [w for w in (extra_words or []) if w and w.strip()]
    for e in entries:
        e = e.strip().lower()
        if e.endswith("*"):
            prefixes.append(_norm(e[:-1]))
        else:
            exact.add(_norm(e))
    return exact, [p for p in prefixes if p]


def find_intervals(words: list[dict], wordlist: tuple[set[str], list[str]],
                   pad: float = PAD_S) -> list[dict]:
    """`words` com tempos relativos ao clipe → [{"start","end"}] fundidos."""
    exact, prefixes = wordlist
    hits: list[tuple[float, float]] = []
    for w in words:
        token = _norm(w["word"])
        if not token:
            continue
        if token in exact or any(token.startswith(p) for p in prefixes):
            hits.append((max(0.0, w["start_s"] - pad), w["end_s"] + pad))
    hits.sort()
    merged: list[list[float]] = []
    for s, e in hits:
        if merged and s <= merged[-1][1] + 0.05:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [{"start": round(s, 3), "end": round(e, 3)} for s, e in merged]
