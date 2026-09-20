"""Create app shell tables."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.core.config import settings
from src.db.base import Base, get_engine

# Import models so metadata is populated
from src.db import models as _models  # noqa: F401


def init_db(db_path: Optional[str] = None) -> None:
    """Ensure parent dir exists and create all tables."""
    target = db_path or settings.app_db_path
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    engine = get_engine(target, force_new=db_path is not None)
    Base.metadata.create_all(bind=engine)
