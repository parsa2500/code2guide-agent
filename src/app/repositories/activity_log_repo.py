"""Activity log repository."""

from __future__ import annotations

from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.app.entities.activity_log import ActivityLogEntity
from src.app.enums import LogLevel
from src.db.models.activity_log import ActivityLog


def _to_entity(row: ActivityLog) -> ActivityLogEntity:
    return ActivityLogEntity(
        id=row.id,
        workspace_id=row.workspace_id,
        at=row.at,
        level=LogLevel(row.level),
        source=row.source,
        message=row.message,
    )


class ActivityLogRepository:
    def __init__(self, db: Session):
        self.db = db

    def append(self, entity: ActivityLogEntity) -> ActivityLogEntity:
        row = ActivityLog(
            id=entity.id,
            workspace_id=entity.workspace_id,
            at=entity.at,
            level=entity.level.value,
            source=entity.source,
            message=entity.message,
        )
        self.db.add(row)
        self.db.flush()
        return _to_entity(row)

    def list_filtered(
        self,
        workspace_id: str,
        *,
        level: Optional[str] = None,
        q: Optional[str] = None,
        from_at: Optional[str] = None,
        to_at: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[ActivityLogEntity], int]:
        filters = [ActivityLog.workspace_id == workspace_id]
        if level:
            filters.append(ActivityLog.level == level)
        if q:
            filters.append(ActivityLog.message.ilike(f"%{q}%"))
        if from_at:
            filters.append(ActivityLog.at >= from_at)
        if to_at:
            filters.append(ActivityLog.at <= to_at)
        total = int(
            self.db.scalar(select(func.count()).select_from(ActivityLog).where(*filters)) or 0
        )
        stmt = (
            select(ActivityLog)
            .where(*filters)
            .order_by(ActivityLog.at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = list(self.db.scalars(stmt).all())
        return [_to_entity(r) for r in rows], total
