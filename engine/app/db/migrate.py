"""Migrações simples por PRAGMA user_version. v1 = baseline (create_all)."""

from __future__ import annotations

from sqlalchemy import text

from .base import Base, get_engine

# Cada entrada é (versão, função(conn) -> None). Baseline cria tudo via metadata.
MIGRATIONS: list = []


def migrate() -> None:
    engine = get_engine()
    Base.metadata.create_all(engine)
    with engine.connect() as conn:
        current = conn.execute(text("PRAGMA user_version")).scalar() or 0
        for version, fn in MIGRATIONS:
            if version > current:
                fn(conn)
                conn.execute(text(f"PRAGMA user_version = {version}"))
                conn.commit()
        if not MIGRATIONS and current == 0:
            conn.execute(text("PRAGMA user_version = 1"))
            conn.commit()
