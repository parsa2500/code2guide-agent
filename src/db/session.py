"""Session factory for app shell DB."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Optional

from sqlalchemy.orm import Session, sessionmaker

from src.db.base import get_engine

SessionLocal: Optional[sessionmaker[Session]] = None


def get_session_factory(db_path: Optional[str] = None, *, force_new: bool = False) -> sessionmaker[Session]:
    """Return (and cache) a sessionmaker bound to the app engine."""
    global SessionLocal
    if SessionLocal is not None and not force_new and db_path is None:
        return SessionLocal
    engine = get_engine(db_path, force_new=force_new or db_path is not None)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    if db_path is None or force_new:
        SessionLocal = factory
    return factory


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yield a session and close it afterwards."""
    factory = get_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()


def reset_session_factory() -> None:
    """Clear cached sessionmaker (tests)."""
    global SessionLocal
    SessionLocal = None
