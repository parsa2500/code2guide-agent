"""Workspace CRUD routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, status

from src.api.deps import get_workspace_service
from src.api.schemas.settings import WorkspaceSettingsOut
from src.api.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceDetailOut,
    WorkspaceListOut,
    WorkspaceOut,
    WorkspaceUpdate,
)
from src.app.constants import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT
from src.app.entities.settings import WorkspaceSettingsEntity
from src.app.entities.workspace import WorkspaceEntity
from src.app.services.workspace_service import WorkspaceService

router = APIRouter(tags=["Workspaces"])


def _ws_out(ws: WorkspaceEntity) -> WorkspaceOut:
    return WorkspaceOut(
        id=ws.id,
        name=ws.name,
        path=ws.path,
        description=ws.description,
        status=ws.status,
        updated_at=ws.updated_at,
        deleted_at=ws.deleted_at,
    )


def _settings_out(s: WorkspaceSettingsEntity) -> WorkspaceSettingsOut:
    return WorkspaceSettingsOut(
        default_agent=s.default_agent,
        enabled_chatbots=s.enabled_chatbots,
        audience_default=s.audience_default,
        auto_index=s.auto_index,
        mcp_enabled=s.mcp_enabled,
    )


@router.get("/workspaces", response_model=WorkspaceListOut)
def list_workspaces(
    q: Optional[str] = None,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    offset: int = Query(default=0, ge=0),
    svc: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceListOut:
    items, total = svc.list_active(q=q, status=status_filter, limit=limit, offset=offset)
    return WorkspaceListOut(
        items=[_ws_out(w) for w in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/workspaces/deleted", response_model=WorkspaceListOut)
def list_deleted_workspaces(
    q: Optional[str] = None,
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    offset: int = Query(default=0, ge=0),
    svc: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceListOut:
    items, total = svc.list_deleted(q=q, limit=limit, offset=offset)
    return WorkspaceListOut(
        items=[_ws_out(w) for w in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceDetailOut)
def get_workspace(
    workspace_id: str,
    svc: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceDetailOut:
    ws, settings = svc.get_detail(workspace_id)
    base = _ws_out(ws)
    return WorkspaceDetailOut(
        **base.model_dump(),
        created_at=ws.created_at,
        settings=_settings_out(settings),
    )


@router.post("/workspaces", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
def create_workspace(
    body: WorkspaceCreate,
    svc: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceOut:
    ws = svc.create(name=body.name, path=body.path, description=body.description)
    return _ws_out(ws)


@router.patch("/workspaces/{workspace_id}", response_model=WorkspaceOut)
def update_workspace(
    workspace_id: str,
    body: WorkspaceUpdate,
    svc: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceOut:
    ws = svc.update(
        workspace_id,
        name=body.name,
        path=body.path,
        description=body.description,
    )
    return _ws_out(ws)


@router.delete("/workspaces/{workspace_id}", response_model=WorkspaceOut)
def delete_workspace(
    workspace_id: str,
    svc: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceOut:
    return _ws_out(svc.soft_delete(workspace_id))


@router.post("/workspaces/{workspace_id}/restore", response_model=WorkspaceOut)
def restore_workspace(
    workspace_id: str,
    svc: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceOut:
    return _ws_out(svc.restore(workspace_id))
