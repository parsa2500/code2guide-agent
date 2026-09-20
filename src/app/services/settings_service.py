"""Workspace settings service."""

from __future__ import annotations

from typing import List

from sqlalchemy.orm import Session

from src.app.constants import DEFAULT_AGENT, DEFAULT_CHATBOT_TECH_ID, DEFAULT_CHATBOT_USER_ID
from src.app.entities.settings import WorkspaceSettingsEntity
from src.app.enums import AudienceDefault, LogLevel, LogSource
from src.app.exceptions import NotFoundError, ValidationAppError
from src.app.repositories.chatbot_repo import ChatbotRepository
from src.app.repositories.settings_repo import SettingsRepository
from src.app.repositories.workspace_repo import WorkspaceRepository
from src.app.services.log_service import LogService


class SettingsService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = SettingsRepository(db)
        self.workspaces = WorkspaceRepository(db)
        self.chatbots = ChatbotRepository(db)
        self.logs = LogService(db)

    def create_defaults(self, workspace_id: str) -> WorkspaceSettingsEntity:
        entity = WorkspaceSettingsEntity(
            workspace_id=workspace_id,
            default_agent=DEFAULT_AGENT,
            enabled_chatbots=[DEFAULT_CHATBOT_USER_ID, DEFAULT_CHATBOT_TECH_ID],
            audience_default=AudienceDefault.END_USER,
            auto_index=True,
            mcp_enabled=False,
        )
        return self.settings.upsert(entity)

    def get(self, workspace_id: str) -> WorkspaceSettingsEntity:
        self._require_active_or_any(workspace_id)
        entity = self.settings.get(workspace_id)
        if entity is None:
            raise NotFoundError("Settings not found", code="SETTINGS_NOT_FOUND")
        return entity

    def replace(
        self,
        workspace_id: str,
        *,
        default_agent: str,
        enabled_chatbots: List[str],
        audience_default: AudienceDefault,
        auto_index: bool,
        mcp_enabled: bool,
    ) -> WorkspaceSettingsEntity:
        self._require_active(workspace_id)
        bots = self.chatbots.list_by_workspace(workspace_id)
        known = {b.id for b in bots}
        unknown = [b for b in enabled_chatbots if b not in known]
        if unknown:
            raise ValidationAppError(
                f"Unknown chatbot ids: {', '.join(unknown)}",
                code="INVALID_SETTINGS",
            )
        entity = WorkspaceSettingsEntity(
            workspace_id=workspace_id,
            default_agent=default_agent.strip() or DEFAULT_AGENT,
            enabled_chatbots=list(enabled_chatbots),
            audience_default=audience_default,
            auto_index=auto_index,
            mcp_enabled=mcp_enabled,
        )
        saved = self.settings.upsert(entity)
        self.logs.append(
            workspace_id,
            level=LogLevel.INFO,
            source=LogSource.SETTINGS.value,
            message="تنظیمات به‌روز شد",
        )
        self.db.commit()
        return saved

    def _require_active_or_any(self, workspace_id: str) -> None:
        ws = self.workspaces.get(workspace_id)
        if ws is None:
            raise NotFoundError("Workspace not found", code="WORKSPACE_NOT_FOUND")

    def _require_active(self, workspace_id: str) -> None:
        ws = self.workspaces.get(workspace_id)
        if ws is None or ws.deleted_at is not None:
            raise NotFoundError("Workspace not found", code="WORKSPACE_NOT_FOUND")
