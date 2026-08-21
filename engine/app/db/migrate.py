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


def _m5_estado_editorial(conn) -> None:
    """v3: máquina de estados editorial, metadados de publicação e revisões.

    'draft' vira 'pending_review' (o estado editorial explícito); descrição e
    platform_metadata preparam a publicação futura; edit_revision/renders.edit_revision
    permitem detectar "render desatualizado" (edit_revision > revisão renderizada)."""
    _add_column(conn, "cut_candidates", "description TEXT DEFAULT ''")
    _add_column(conn, "cut_candidates", "platform_metadata JSON")
    _add_column(conn, "cut_candidates", "edit_revision INTEGER DEFAULT 1")
    _add_column(conn, "renders", "edit_revision INTEGER")
    conn.execute(text("UPDATE cut_candidates SET status = 'pending_review' WHERE status = 'draft'"))


def _m6_motion(conn) -> None:
    """v4: Motion Manifest por corte — fonte única da verdade dos efeitos de
    movimento (texto, vídeo, b-roll, transições, SFX). Cortes antigos abrem
    sem manifest (NULL = manifest vazio); nada é reinterpretado."""
    _add_column(conn, "cut_candidates", "motion JSON")


def _m7_project_media(conn) -> None:
    """v4: biblioteca de mídia do projeto (B-roll) — arquivos COPIADOS para o
    data_dir e referenciados por id (Entrega 82: referência robusta)."""
    conn.execute(text(
        """CREATE TABLE IF NOT EXISTS project_media (
            id VARCHAR(32) PRIMARY KEY,
            project_id VARCHAR(32) NOT NULL,
            filename VARCHAR(255) NOT NULL DEFAULT '',
            path VARCHAR(500) NOT NULL,
            kind VARCHAR(10) NOT NULL DEFAULT 'video',
            duration_s FLOAT,
            width INTEGER,
            height INTEGER,
            created_at VARCHAR(32)
        )"""))


MIGRATIONS: list = [
    (2, _m2_analise_editorial),
    (3, _m3_editor_edl),
    (4, _m4_brand_studio),
    (5, _m5_estado_editorial),
    (6, _m6_motion),
    (7, _m7_project_media),
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
