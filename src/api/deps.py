"""FastAPI dependencies for app shell."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends
from sqlalchemy.orm import Session

from src.app.services.chat_service import ChatService
from src.app.services.log_service import LogService
from src.app.services.settings_service import SettingsService
from src.app.services.update_service import UpdateService
from src.app.services.workspace_service import WorkspaceService
from src.db.session import get_db


def get_workspace_service(db: Session = Depends(get_db)) -> WorkspaceService:
    return WorkspaceService(db)


def get_settings_service(db: Session = Depends(get_db)) -> SettingsService:
    return SettingsService(db)


def get_update_service(db: Session = Depends(get_db)) -> UpdateService:
    return UpdateService(db)


def get_log_service(db: Session = Depends(get_db)) -> LogService:
    return LogService(db)


def get_chat_service(db: Session = Depends(get_db)) -> ChatService:
    return ChatService(db)
