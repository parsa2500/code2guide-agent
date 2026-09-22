"""Workspace CRUD service."""

from __future__ import annotations

from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from src.app.constants import (
    DEFAULT_CHATBOT_TECH_ID,
    DEFAULT_CHATBOT_TECH_NAME,
    DEFAULT_CHATBOT_USER_ID,
    DEFAULT_CHATBOT_USER_NAME,
)
from src.app.entities.chatbot import ChatbotEntity
from src.app.entities.settings import WorkspaceSettingsEntity
from src.app.entities.workspace import WorkspaceEntity
from src.app.enums import ChatbotRole, LogLevel, LogSource, WorkspaceStatus
from src.app.exceptions import ConflictError, NotFoundError, ValidationAppError, WorkspaceBusyError
from src.app.ids import new_workspace_id
from src.app.pathutil import normalize_workspace_path
from src.app.repositories.chatbot_repo import ChatbotRepository
from src.app.repositories.settings_repo import SettingsRepository
from src.app.repositories.update_job_repo import UpdateJobRepository
from src.app.repositories.workspace_repo import WorkspaceRepository
from src.app.services.agent_seed import bind_default_agents
from src.app.services.log_service import LogService
from src.app.services.settings_service import SettingsService
from src.app.timeutil import utc_now_iso


class WorkspaceService:
    def __init__(self, db: Session):
        self.db = db
        self.workspaces = WorkspaceRepository(db)
        self.settings_repo = SettingsRepository(db)
        self.chatbots = ChatbotRepository(db)
        self.jobs = UpdateJobRepository(db)
        self.logs = LogService(db)
        self.settings_service = SettingsService(db)

    def create(self, *, name: str, path: str, description: str = "") -> WorkspaceEntity:
        name = (name or "").strip()
        if not name:
            raise ValidationAppError("Name must not be empty", code="INVALID_NAME")
        norm_path = normalize_workspace_path(path)
        if self.workspaces.get_by_path_active(norm_path):
            raise ConflictError("An active workspace with this path already exists", code="PATH_ALREADY_EXISTS")

        now = utc_now_iso()
        ws = WorkspaceEntity(
            id=new_workspace_id(),
            name=name,
            path=norm_path,
            description=(description or "").strip(),
            status=WorkspaceStatus.IDLE,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
        self.workspaces.create(ws)
        self.settings_service.create_defaults(ws.id)
        self.chatbots.create_many(
            [
                ChatbotEntity(
                    id=DEFAULT_CHATBOT_USER_ID,
                    workspace_id=ws.id,
                    name=DEFAULT_CHATBOT_USER_NAME,
                    role=ChatbotRole.END_USER,
                ),
                ChatbotEntity(
                    id=DEFAULT_CHATBOT_TECH_ID,
                    workspace_id=ws.id,
                    name=DEFAULT_CHATBOT_TECH_NAME,
                    role=ChatbotRole.TECHNICAL,
                ),
            ]
        )
        # Slice-1: keep chatbot rows for AskConsole AND bind workspace_agents
        bind_default_agents(self.db, ws.id)
        self.logs.append(
            ws.id,
            level=LogLevel.INFO,
            source=LogSource.SYSTEM.value,
            message="Workspace ساخته شد",
        )
        self.db.commit()
        return ws

    def list_active(
        self,
        *,
        q: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[WorkspaceEntity], int]:
        return self.workspaces.list_active(q=q, status=status, limit=limit, offset=offset)

    def list_deleted(
        self,
        *,
        q: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[WorkspaceEntity], int]:
        return self.workspaces.list_deleted(q=q, limit=limit, offset=offset)

    def get(self, workspace_id: str) -> WorkspaceEntity:
        ws = self.workspaces.get(workspace_id)
        if ws is None:
            raise NotFoundError("Workspace not found", code="WORKSPACE_NOT_FOUND")
        return ws

    def get_detail(self, workspace_id: str) -> Tuple[WorkspaceEntity, WorkspaceSettingsEntity]:
        ws = self.get(workspace_id)
        settings = self.settings_repo.get(workspace_id)
        if settings is None:
            raise NotFoundError("Settings not found", code="SETTINGS_NOT_FOUND")
        return ws, settings

    def update(
        self,
        workspace_id: str,
        *,
        name: Optional[str] = None,
        path: Optional[str] = None,
        description: Optional[str] = None,
    ) -> WorkspaceEntity:
        ws = self._require_active(workspace_id)
        if name is None and path is None and description is None:
            raise ValidationAppError("At least one field is required", code="EMPTY_PATCH")
        if name is not None:
            name = name.strip()
            if not name:
                raise ValidationAppError("Name must not be empty", code="INVALID_NAME")
            ws.name = name
        if description is not None:
            ws.description = description.strip()
        if path is not None:
            norm = normalize_workspace_path(path)
            other = self.workspaces.get_by_path_active(norm)
            if other and other.id != workspace_id:
                raise ConflictError(
                    "An active workspace with this path already exists",
                    code="PATH_ALREADY_EXISTS",
                )
            ws.path = norm
        ws.updated_at = utc_now_iso()
        saved = self.workspaces.update(ws)
        self.logs.append(
            workspace_id,
            level=LogLevel.INFO,
            source=LogSource.SYSTEM.value,
            message="Workspace ویرایش شد",
        )
        self.db.commit()
        return saved

    def soft_delete(self, workspace_id: str) -> WorkspaceEntity:
        ws = self._require_active(workspace_id)
        if self.jobs.has_running(workspace_id):
            raise WorkspaceBusyError("Cannot delete while indexing is running")
        now = utc_now_iso()
        ws.deleted_at = now
        ws.updated_at = now
        saved = self.workspaces.update(ws)
        self.logs.append(
            workspace_id,
            level=LogLevel.INFO,
            source=LogSource.SYSTEM.value,
            message="Workspace به سطل حذف منتقل شد",
        )
        self.db.commit()
        try:
            from src.knowledge.manager import get_index_manager

            get_index_manager(saved.path, workspace_id=workspace_id).mark_tombstone(True)
        except Exception:
            pass
        return saved

    def restore(self, workspace_id: str) -> WorkspaceEntity:
        ws = self.workspaces.get(workspace_id)
        if ws is None:
            raise NotFoundError("Workspace not found", code="WORKSPACE_NOT_FOUND")
        if ws.deleted_at is None:
            raise ConflictError("Workspace is not deleted", code="NOT_DELETED")
        other = self.workspaces.get_by_path_active(ws.path)
        if other and other.id != workspace_id:
            raise ConflictError(
                "An active workspace with this path already exists",
                code="PATH_ALREADY_EXISTS",
            )
        ws.deleted_at = None
        ws.updated_at = utc_now_iso()
        saved = self.workspaces.update(ws)
        self.logs.append(
            workspace_id,
            level=LogLevel.INFO,
            source=LogSource.SYSTEM.value,
            message="Workspace بازیابی شد",
        )
        self.db.commit()
        try:
            from src.knowledge.manager import get_index_manager

            get_index_manager(saved.path, workspace_id=workspace_id).mark_tombstone(False)
        except Exception:
            pass
        return saved

    def set_status(self, workspace_id: str, status: WorkspaceStatus) -> WorkspaceEntity:
        ws = self.workspaces.get(workspace_id)
        if ws is None:
            raise NotFoundError("Workspace not found", code="WORKSPACE_NOT_FOUND")
        ws.status = status
        ws.updated_at = utc_now_iso()
        return self.workspaces.update(ws)

    def _require_active(self, workspace_id: str) -> WorkspaceEntity:
        ws = self.workspaces.get(workspace_id)
        if ws is None or ws.deleted_at is not None:
            raise NotFoundError("Workspace not found", code="WORKSPACE_NOT_FOUND")
        return ws
