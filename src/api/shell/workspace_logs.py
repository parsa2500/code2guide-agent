"""Workspace activity log routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from src.api.deps import get_log_service, get_workspace_service
from src.api.schemas.activity_log import ActivityLogListOut, ActivityLogOut
from src.app.constants import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT
from src.app.services.log_service import LogService
from src.app.services.workspace_service import WorkspaceService

router = APIRouter(tags=["Workspace Logs"])


@router.get("/workspaces/{workspace_id}/logs", response_model=ActivityLogListOut)
def list_logs(
    workspace_id: str,
    level: Optional[str] = None,
    q: Optional[str] = None,
    from_at: Optional[str] = Query(default=None, alias="from"),
    to_at: Optional[str] = Query(default=None, alias="to"),
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    offset: int = Query(default=0, ge=0),
    workspaces: WorkspaceService = Depends(get_workspace_service),
    logs: LogService = Depends(get_log_service),
) -> ActivityLogListOut:
    workspaces.get(workspace_id)
    items, total = logs.list_logs(
        workspace_id,
        level=level,
        q=q,
        from_at=from_at,
        to_at=to_at,
        limit=limit,
        offset=offset,
    )
    return ActivityLogListOut(
        items=[
            ActivityLogOut(
                id=i.id,
                at=i.at,
                level=i.level,
                source=i.source,
                message=i.message,
            )
            for i in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
