"""Workspace settings routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.deps import get_settings_service
from src.api.schemas.settings import WorkspaceSettingsIn, WorkspaceSettingsOut
from src.app.entities.settings import WorkspaceSettingsEntity
from src.app.services.settings_service import SettingsService

router = APIRouter(tags=["Workspace Settings"])


def _out(s: WorkspaceSettingsEntity) -> WorkspaceSettingsOut:
    return WorkspaceSettingsOut(
        default_agent=s.default_agent,
        enabled_chatbots=s.enabled_chatbots,
        audience_default=s.audience_default,
        auto_index=s.auto_index,
        mcp_enabled=s.mcp_enabled,
    )


@router.get("/workspaces/{workspace_id}/settings", response_model=WorkspaceSettingsOut)
def get_settings(
    workspace_id: str,
    svc: SettingsService = Depends(get_settings_service),
) -> WorkspaceSettingsOut:
    return _out(svc.get(workspace_id))


@router.put("/workspaces/{workspace_id}/settings", response_model=WorkspaceSettingsOut)
def put_settings(
    workspace_id: str,
    body: WorkspaceSettingsIn,
    svc: SettingsService = Depends(get_settings_service),
) -> WorkspaceSettingsOut:
    return _out(
        svc.replace(
            workspace_id,
            default_agent=body.default_agent,
            enabled_chatbots=body.enabled_chatbots,
            audience_default=body.audience_default,
            auto_index=body.auto_index,
            mcp_enabled=body.mcp_enabled,
        )
    )
