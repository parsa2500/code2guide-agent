"""Update job repository."""

from __future__ import annotations

from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.app.entities.update_job import UpdateJobEntity
from src.app.enums import UpdateJobStatus, UpdateScope
from src.db.models.update_job import UpdateJob


def _to_entity(row: UpdateJob) -> UpdateJobEntity:
    return UpdateJobEntity(
        id=row.id,
        workspace_id=row.workspace_id,
        started_at=row.started_at,
        finished_at=row.finished_at,
        status=UpdateJobStatus(row.status),
        summary=row.summary or "",
        detail=row.detail or "",
        rebuild=bool(row.rebuild),
        scope=UpdateScope(row.scope),
    )


class UpdateJobRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, entity: UpdateJobEntity) -> UpdateJobEntity:
        row = UpdateJob(
            id=entity.id,
            workspace_id=entity.workspace_id,
            started_at=entity.started_at,
            finished_at=entity.finished_at,
            status=entity.status.value,
            summary=entity.summary,
            detail=entity.detail,
            rebuild=1 if entity.rebuild else 0,
            scope=entity.scope.value,
        )
        self.db.add(row)
        self.db.flush()
        return _to_entity(row)

    def get(self, job_id: str) -> Optional[UpdateJobEntity]:
        row = self.db.get(UpdateJob, job_id)
        return _to_entity(row) if row else None

    def list_by_workspace(
        self,
        workspace_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[UpdateJobEntity], int]:
        filters = [UpdateJob.workspace_id == workspace_id]
        total = int(
            self.db.scalar(select(func.count()).select_from(UpdateJob).where(*filters)) or 0
        )
        stmt = (
            select(UpdateJob)
            .where(*filters)
            .order_by(UpdateJob.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = list(self.db.scalars(stmt).all())
        return [_to_entity(r) for r in rows], total

    def has_running(self, workspace_id: str) -> bool:
        stmt = select(UpdateJob.id).where(
            UpdateJob.workspace_id == workspace_id,
            UpdateJob.status == UpdateJobStatus.RUNNING.value,
        )
        return self.db.scalars(stmt).first() is not None

    def set_finished(
        self,
        job_id: str,
        *,
        status: UpdateJobStatus,
        finished_at: str,
        summary: str,
        detail: str,
    ) -> Optional[UpdateJobEntity]:
        row = self.db.get(UpdateJob, job_id)
        if row is None:
            return None
        row.status = status.value
        row.finished_at = finished_at
        row.summary = summary
        row.detail = detail
        self.db.flush()
        return _to_entity(row)
