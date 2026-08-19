"""Dependências FastAPI: autenticação Bearer e acesso a estado do app."""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, Query, Request


def _expected_token(request: Request) -> str:
    token = getattr(request.app.state, "api_token", None)
    if not token:
        raise HTTPException(status_code=503, detail="Motor ainda inicializando")
    return token


def require_token(request: Request, authorization: str | None = Header(default=None)) -> None:
    """Exige `Authorization: Bearer <token>`."""
    expected = _expected_token(request)
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token ausente. Use Authorization: Bearer <token>.")
    provided = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Token inválido")


def require_token_query(request: Request, token: str | None = Query(default=None),
                        authorization: str | None = Header(default=None)) -> None:
    """Variante para streaming de mídia: aceita ?token= (tag <video> não envia headers)."""
    expected = _expected_token(request)
    provided = None
    if authorization and authorization.startswith("Bearer "):
        provided = authorization.removeprefix("Bearer ").strip()
    elif token:
        provided = token
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Token inválido")
