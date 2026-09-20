"""SQLAlchemy declarative base and engine factory."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase

from src.core.config import settings

_engine: Optional[Engine] = None


class Base(DeclarativeBase):
    """Declarative base for app shell ORM models."""


def _sqlite_url(db_path: str) -> str:
    path = Path(db_path)
    if not path.is_absolute():
        path = path.resolve()
    return f"sqlite:///{path.as_posix()}"


def get_engine(db_path: Optional[str] = None, *, force_new: bool = False) -> Engine:
    """Return a process-level engine (recreated when force_new or first call)."""
    global _engine
    target = db_path or settings.app_db_path
    if _engine is not None and not force_new:
        return _engine

    Path(target).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        _sqlite_url(target),
        connect_args={"check_same_thread": False},
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    if force_new and _engine is not None:
        _engine.dispose()
    _engine = engine
    return _engine


def reset_engine() -> None:
    """Dispose and clear the global engine (tests)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None
