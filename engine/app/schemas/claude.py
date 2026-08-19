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


# Chaves aceitas pelas saídas estruturadas dos provedores. Tudo fora disto é
# REMOVIDO: a API da Anthropic rejeita a requisição inteira por palavras-chave
# de validação do JSON Schema (ex.: 400 "For 'number' type, property 'minimum'
# is not supported"), e o modo estrito da OpenAI tem restrições equivalentes.
# Os limites 0–10 continuam garantidos pelo prompt + validação Pydantic no parse.
_ALLOWED_SCHEMA_KEYS = {
    "type", "properties", "required", "additionalProperties", "items",
    "enum", "anyOf", "allOf", "$defs", "$ref", "description",
}


def _strictify(node: dict) -> None:
    """Modo estrito de saída estruturada: remove palavras-chave não suportadas,
    fecha propriedades extras e exige todas as chaves (shape exato garantido)."""
    if not isinstance(node, dict):
        return
    for key in list(node.keys()):
        if key not in _ALLOWED_SCHEMA_KEYS:
            node.pop(key)
    if node.get("type") == "object" and "properties" in node:
        node["additionalProperties"] = False
        node["required"] = list(node["properties"].keys())
        for prop in node["properties"].values():
            _strictify(prop)
    if "items" in node:
        _strictify(node["items"])
    for sub in node.get("$defs", {}).values():
        _strictify(sub)
    for key in ("anyOf", "allOf"):
        for sub in node.get(key, []) or []:
            _strictify(sub)


def _inline_refs(node, defs: dict):
    """Substitui {"$ref": "#/$defs/X"} pela definição (nosso schema não é recursivo
    e cada $def é usado uma única vez — inlinar não duplica nada e evita depender
    de suporte a $ref/$defs nos provedores)."""
    if isinstance(node, dict):
        ref = node.get("$ref", "")
        if ref.startswith("#/$defs/"):
            import copy

            alvo = copy.deepcopy(defs[ref.split("/")[-1]])
            _inline_refs(alvo, defs)
            node.clear()
            node.update(alvo)
            return
        for value in node.values():
            _inline_refs(value, defs)
    elif isinstance(node, list):
        for item in node:
            _inline_refs(item, defs)


def strict_chunk_schema() -> dict:
    """JSON Schema estrito de ChunkAnalysis — usado no output_config (Claude),
    no response_format (OpenAI) e no modo Batches."""
    schema = ChunkAnalysis.model_json_schema()
    defs = schema.pop("$defs", {})
    _inline_refs(schema, defs)
    _strictify(schema)
    return schema
