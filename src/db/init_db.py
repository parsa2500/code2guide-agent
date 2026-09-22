"""Create app shell tables and run agent seed/migrate."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.core.config import settings
from src.db.base import Base, get_engine

# Import models so metadata is populated
from src.db import models as _models  # noqa: F401


def init_db(db_path: Optional[str] = None) -> None:
    """Ensure parent dir exists, create all tables, seed agents, migrate bindings."""
    target = db_path or settings.app_db_path
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    engine = get_engine(target, force_new=db_path is not None)
    Base.metadata.create_all(bind=engine)

    # Seed + migrate workspace_agents (safe / idempotent)
    from sqlalchemy.orm import Session

    from src.app.services.agent_seed import (
        ensure_seed_agents,
        migrate_workspace_agent_bindings,
    )
    from src.app.services.brain_settings_service import load_brain_settings_file

    load_brain_settings_file()
    with Session(engine) as session:
        ensure_seed_agents(session)
        migrate_workspace_agent_bindings(session)
        session.commit()
