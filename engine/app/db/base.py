"""Engine SQLite (WAL) e sessões. Inicializado explicitamente no startup (init_engine)."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory: sessionmaker | None = None


def init_engine(path: Path):
    """Cria (ou recria) o engine apontando para `path`. Chamado no lifespan e nos testes."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )

    @event.listens_for(_engine, "connect")
    def _set_pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_engine():
    if _engine is None:
        raise RuntimeError("DB engine não inicializado — chame init_engine() antes.")
    return _engine


@contextmanager
def session() -> Session:
    """Sessão com commit no sucesso e rollback em exceção."""
    if _session_factory is None:
        raise RuntimeError("DB engine não inicializado — chame init_engine() antes.")
    s = _session_factory()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
