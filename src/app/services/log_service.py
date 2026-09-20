"""Activity log service."""

from __future__ import annotations

from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from src.app.entities.activity_log import ActivityLogEntity
from src.app.enums import LogLevel
from src.app.ids import new_activity_log_id
from src.app.repositories.activity_log_repo import ActivityLogRepository
from src.app.timeutil import utc_now_iso


class LogService:
    def __init__(self, db: Session):
        self.db = db
        self.logs = ActivityLogRepository(db)

    def append(
        self,
        workspace_id: str,
        *,
        level: LogLevel,
        source: str,
        message: str,
        at: Optional[str] = None,
    ) -> ActivityLogEntity:
        entity = ActivityLogEntity(
            id=new_activity_log_id(),
            workspace_id=workspace_id,
            at=at or utc_now_iso(),
            level=level,
            source=source,
            message=message,
        )
        return self.logs.append(entity)

    def list_logs(
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
        return self.logs.list_filtered(
            workspace_id,
            level=level,
            q=q,
            from_at=from_at,
            to_at=to_at,
            limit=limit,
            offset=offset,
        )
