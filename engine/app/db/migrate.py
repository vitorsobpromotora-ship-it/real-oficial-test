"""Migrações simples por PRAGMA user_version.

create_all cobre bancos novos; as migrações abaixo evoluem bancos existentes.
ALTERs são tolerantes a "duplicate column" para conviver com o create_all.
"""

from __future__ import annotations

from sqlalchemy import text

from .base import Base, get_engine


def _add_column(conn, table: str, column_ddl: str) -> None:
    try:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column_ddl}"))
    except Exception as exc:  # coluna já existe (banco novo via create_all)
        if "duplicate column" not in str(exc).lower():
            raise


def _m2_analise_editorial(conn) -> None:
    """v1.1.0: veredito e análise editorial detalhada por corte."""
    _add_column(conn, "cut_candidates", "verdict VARCHAR(12) DEFAULT 'revisar'")
    _add_column(conn, "cut_candidates", "analysis JSON")


def _m3_editor_edl(conn) -> None:
    """v2.0.0: EDL não destrutiva do Editor de Corte (trim/split/fades por corte)."""
    _add_column(conn, "cut_candidates", "edl JSON")


def _m4_brand_studio(conn) -> None:
    """v2.0.0: layout do Brand Studio por kit (canvas 9:16 com camadas)."""
    _add_column(conn, "brand_kits", "layout JSON")


MIGRATIONS: list = [
    (2, _m2_analise_editorial),
    (3, _m3_editor_edl),
    (4, _m4_brand_studio),
]


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
                current = version
        if current == 0:
            conn.execute(text("PRAGMA user_version = 1"))
            conn.commit()
