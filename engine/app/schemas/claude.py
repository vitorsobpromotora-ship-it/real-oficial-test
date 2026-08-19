"""Schemas de saída estruturada da análise semântica (os 18 parâmetros do score)."""

from __future__ import annotations

from pydantic import BaseModel, Field

PARAM_KEYS = [
    "hook_strength", "emotional_intensity", "humor", "tension", "completeness",
    "context_independence", "clarity", "information_value", "storytelling", "controversy",
    "relatability", "quotability", "novelty", "energy", "cta_potential", "loopability",
    "title_potential", "niche_fit",
]

PARAM_LABELS_PTBR = {
    "hook_strength": "Força do gancho",
    "emotional_intensity": "Intensidade emocional",
    "humor": "Humor",
    "tension": "Tensão",
    "completeness": "Completude",
    "context_independence": "Independência de contexto",
    "clarity": "Clareza",
    "information_value": "Valor informativo",
    "storytelling": "Narrativa",
    "controversy": "Controvérsia",
    "relatability": "Identificação",
    "quotability": "Citabilidade",
    "novelty": "Novidade",
    "energy": "Energia",
    "cta_potential": "Potencial de CTA",
    "loopability": "Potencial de loop",
    "title_potential": "Potencial de título",
    "niche_fit": "Aderência ao nicho",
}


class Params(BaseModel):
    """Notas 0–10 para cada um dos 18 parâmetros de análise."""

    hook_strength: float = Field(default=5.0, ge=0, le=10)
    emotional_intensity: float = Field(default=5.0, ge=0, le=10)
    humor: float = Field(default=5.0, ge=0, le=10)
    tension: float = Field(default=5.0, ge=0, le=10)
    completeness: float = Field(default=5.0, ge=0, le=10)
    context_independence: float = Field(default=5.0, ge=0, le=10)
    clarity: float = Field(default=5.0, ge=0, le=10)
    information_value: float = Field(default=5.0, ge=0, le=10)
    storytelling: float = Field(default=5.0, ge=0, le=10)
    controversy: float = Field(default=5.0, ge=0, le=10)
    relatability: float = Field(default=5.0, ge=0, le=10)
    quotability: float = Field(default=5.0, ge=0, le=10)
    novelty: float = Field(default=5.0, ge=0, le=10)
    energy: float = Field(default=5.0, ge=0, le=10)
    cta_potential: float = Field(default=5.0, ge=0, le=10)
    loopability: float = Field(default=5.0, ge=0, le=10)
    title_potential: float = Field(default=5.0, ge=0, le=10)
    niche_fit: float = Field(default=5.0, ge=0, le=10)


class CandidateSegment(BaseModel):
    """Um trecho candidato a corte, em segundos absolutos do vídeo original."""

    start_s: float = Field(ge=0)
    end_s: float = Field(ge=0)
    params: Params = Field(default_factory=Params)
    hook_line: str = ""
    title: str = ""
    hashtags: list[str] = Field(default_factory=list)
    reason: str = ""


class ChunkAnalysis(BaseModel):
    """Resultado da análise de um chunk de transcrição."""

    segments: list[CandidateSegment] = Field(default_factory=list)
