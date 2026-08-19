"""Resolução do agente de IA escolhido para um processamento.

O agente é escolhido POR PROCESSAMENTO (options["agent"] no job) com padrão nas
Configurações (default_agent). "local" é uma escolha explícita e válida — o que
não existe mais é IA selecionada silenciosamente virar heurística.
"""

from __future__ import annotations

from ..db import settings_store

AGENTS = ("claude", "gpt", "local")

AGENT_LABELS = {
    "claude": "Claude (Anthropic)",
    "gpt": "GPT (OpenAI)",
    "local": "Análise local (sem IA)",
}


def resolve_agent(explicit: str | None) -> str:
    agent = (explicit or settings_store.get_setting("default_agent") or "claude").strip().lower()
    return agent if agent in AGENTS else "claude"


def agent_api_key(agent: str) -> str:
    if agent == "claude":
        return settings_store.get_setting("anthropic_api_key") or ""
    if agent == "gpt":
        return settings_store.get_setting("openai_api_key") or ""
    return ""


def agent_models(agent: str) -> tuple[str, str | None]:
    """(modelo principal, modelo de contingência) do agente."""
    if agent == "claude":
        return (settings_store.get_setting("claude_model") or "claude-opus-5",
                settings_store.get_setting("claude_fallback_model") or "claude-sonnet-5")
    if agent == "gpt":
        return (settings_store.get_setting("openai_model") or "gpt-5.1",
                settings_store.get_setting("openai_fallback_model") or None)
    return ("", None)


def missing_key_error(agent: str) -> str:
    provider = "Anthropic" if agent == "claude" else "OpenAI"
    return (f"O agente {AGENT_LABELS.get(agent, agent)} foi selecionado, mas não há chave "
            f"de API {provider} configurada. Adicione a chave em Configurações → "
            f"Inteligência artificial, ou escolha o agente 'Análise local'.")


def build_client(agent: str):
    """Instancia o cliente do agente (claude|gpt). Lança ValueError sem chave."""
    key = agent_api_key(agent)
    if not key:
        raise ValueError(missing_key_error(agent))
    model, fallback = agent_models(agent)
    if agent == "claude":
        from .claude_client import SemanticClient

        return SemanticClient(key, model), fallback, model
    if agent == "gpt":
        from .openai_client import OpenAIClient

        return OpenAIClient(key, model), fallback, model
    raise ValueError(f"Agente desconhecido: {agent}")
