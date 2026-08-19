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


class AnalysisDetail(BaseModel):
    """Análise editorial detalhada do corte, em PT-BR, citando o conteúdo real."""

    gancho: str = Field(default="", description="Avaliação dos 3 primeiros segundos, citando a fala")
    desenvolvimento: str = Field(default="", description="Como o trecho sustenta a atenção")
    conclusao: str = Field(default="", description="O trecho fecha com payoff? Qual?")
    ponto_forte: str = Field(default="", description="O maior motivo para postar este corte")
    ponto_fraco: str = Field(default="", description="O maior risco/fraqueza deste corte")
    sugestao: str = Field(default="", description="1 ajuste concreto que melhoraria o corte")
    publico: str = Field(default="", description="Para quem este corte funciona melhor")


class CandidateSegment(BaseModel):
    """Um trecho candidato a corte, em segundos absolutos do vídeo original."""

    start_s: float = Field(ge=0)
    end_s: float = Field(ge=0)
    params: Params = Field(default_factory=Params)
    verdict: str = Field(default="revisar",
                         description="postar (publicável como está) | revisar (bom, mas precisa de ajuste) | descartar (fraco)")
    analysis: AnalysisDetail = Field(default_factory=AnalysisDetail)
    hook_line: str = ""
    title: str = ""
    hashtags: list[str] = Field(default_factory=list)
    reason: str = ""


class ChunkAnalysis(BaseModel):
    """Resultado da análise de um chunk de transcrição."""

    segments: list[CandidateSegment] = Field(default_factory=list)


def _strictify(node: dict) -> None:
    """Modo estrito de saída estruturada: todo objeto fecha propriedades extras e
    exige todas as chaves (os provedores então garantem o shape exato)."""
    if not isinstance(node, dict):
        return
    if node.get("type") == "object" and "properties" in node:
        node["additionalProperties"] = False
        node["required"] = list(node["properties"].keys())
        for prop in node["properties"].values():
            _strictify(prop)
    if "items" in node:
        _strictify(node["items"])
    for sub in node.get("$defs", {}).values():
        _strictify(sub)
    for sub in node.get("anyOf", []) or []:
        _strictify(sub)


def strict_chunk_schema() -> dict:
    """JSON Schema estrito de ChunkAnalysis — usado no output_config (Claude),
    no response_format (OpenAI) e no modo Batches."""
    schema = ChunkAnalysis.model_json_schema()
    _strictify(schema)
    return schema
