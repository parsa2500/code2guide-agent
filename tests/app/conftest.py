"""Test helpers for app shell API."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.core.config import settings
from src.db.base import reset_engine
from src.db.init_db import init_db
from src.db.session import get_session_factory, reset_session_factory


@pytest.fixture()
def app_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_file = tmp_path / "app.db"
    monkeypatch.setattr(settings, "app_db_path", str(db_file))
    reset_session_factory()
    reset_engine()
    init_db(str(db_file))
    get_session_factory(str(db_file), force_new=True)

    from src.api.main import app

    with TestClient(app) as client:
        yield client

    reset_session_factory()
    reset_engine()
