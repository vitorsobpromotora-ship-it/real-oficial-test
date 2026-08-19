"""Fusão de scores: semântico (18 parâmetros ponderados) × RHPT (picos de áudio) → 0–100."""

from __future__ import annotations

from ..schemas.claude import PARAM_KEYS
from .audio_features import Features

SEMANTIC_WEIGHTS: dict[str, float] = {
    "hook_strength": 1.6,
    "completeness": 1.3,
    "context_independence": 1.2,
    "emotional_intensity": 1.2,
    "quotability": 1.1,
    "storytelling": 1.1,
    "clarity": 1.05,
    "title_potential": 1.05,
}
FINAL_SEMANTIC_WEIGHT = 0.65
FINAL_RHPT_WEIGHT = 0.35


def semantic_score(params: dict) -> float:
    total = 0.0
    weight_sum = 0.0
    for key in PARAM_KEYS:
        w = SEMANTIC_WEIGHTS.get(key, 1.0)
        total += float(params.get(key, 5.0)) * w
        weight_sum += w
    return round(10.0 * total / weight_sum, 2)  # 0–100


def rhpt_score(start_s: float, end_s: float, features: Features) -> float:
    peak_max, peak_mean = features.peak_between(start_s, end_s)
    return round(100.0 * (0.6 * peak_max + 0.4 * peak_mean), 2)


def final_score(sem: float, rhpt: float) -> float:
    return round(FINAL_SEMANTIC_WEIGHT * sem + FINAL_RHPT_WEIGHT * rhpt, 2)
