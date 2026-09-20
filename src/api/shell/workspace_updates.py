"""Workspace update job routes."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from src.api.deps import get_update_service
from src.api.schemas.update_job import (
    UpdateJobAcceptedOut,
    UpdateJobListOut,
    UpdateJobOut,
    UpdateStartIn,
)
from src.app.constants import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT
from src.app.entities.update_job import UpdateJobEntity
from src.app.services.update_service import UpdateService

router = APIRouter(tags=["Workspace Updates"])


def _job_out(job: UpdateJobEntity) -> UpdateJobOut:
    return UpdateJobOut(
        id=job.id,
        started_at=job.started_at,
        finished_at=job.finished_at,
        status=job.status,
        summary=job.summary,
        detail=job.detail,
    )


@router.post(
    "/workspaces/{workspace_id}/update",
    response_model=UpdateJobAcceptedOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_update(
    workspace_id: str,
    background_tasks: BackgroundTasks,
    body: UpdateStartIn | None = None,
    svc: UpdateService = Depends(get_update_service),
) -> UpdateJobAcceptedOut:
    payload = body or UpdateStartIn()
    job = svc.start(workspace_id, rebuild=payload.rebuild, scope=payload.scope)
    ws = svc.workspaces.get(workspace_id)
    assert ws is not None
    background_tasks.add_task(
        UpdateService.run_index_job,
        job.id,
        ws.path,
        rebuild=payload.rebuild,
    )
    return UpdateJobAcceptedOut(job_id=job.id, status=job.status, started_at=job.started_at)


@router.get("/workspaces/{workspace_id}/updates", response_model=UpdateJobListOut)
def list_updates(
    workspace_id: str,
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    offset: int = Query(default=0, ge=0),
    svc: UpdateService = Depends(get_update_service),
) -> UpdateJobListOut:
    items, total = svc.list_jobs(workspace_id, limit=limit, offset=offset)
    return UpdateJobListOut(
        items=[_job_out(j) for j in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/workspaces/{workspace_id}/updates/{job_id}", response_model=UpdateJobOut)
def get_update(
    workspace_id: str,
    job_id: str,
    svc: UpdateService = Depends(get_update_service),
) -> UpdateJobOut:
    return _job_out(svc.get_job(workspace_id, job_id))
