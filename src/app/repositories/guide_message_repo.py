"""Guide message repository."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.app.entities.guide_message import GuideMessageEntity
from src.app.enums import ChatRole
from src.db.models.guide_message import GuideMessage


def _parse_steps(raw: Optional[str]) -> Optional[List[Dict[str, Any]]]:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, list) else None


def _to_entity(row: GuideMessage) -> GuideMessageEntity:
    return GuideMessageEntity(
        id=row.id,
        session_id=row.session_id,
        workspace_id=row.workspace_id,
        role=ChatRole(row.role),
        text=row.text,
        at=row.at,
        steps=_parse_steps(row.steps_json),
    )


class GuideMessageRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, entity: GuideMessageEntity) -> GuideMessageEntity:
        steps_json = None
        if entity.steps is not None:
            steps_json = json.dumps(entity.steps, ensure_ascii=False)
        row = GuideMessage(
            id=entity.id,
            session_id=entity.session_id,
            workspace_id=entity.workspace_id,
            role=entity.role.value,
            text=entity.text,
            steps_json=steps_json,
            at=entity.at,
        )
        self.db.add(row)
        self.db.flush()
        return _to_entity(row)

    def list_by_session(
        self,
        workspace_id: str,
        session_id: str,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> Tuple[List[GuideMessageEntity], int]:
        filters = [
            GuideMessage.workspace_id == workspace_id,
            GuideMessage.session_id == session_id,
        ]
        total = int(
            self.db.scalar(select(func.count()).select_from(GuideMessage).where(*filters)) or 0
        )
        stmt = (
            select(GuideMessage)
            .where(*filters)
            .order_by(GuideMessage.at.asc())
            .limit(limit)
            .offset(offset)
        )
        rows = list(self.db.scalars(stmt).all())
        return [_to_entity(r) for r in rows], total

    def count_by_session(self, workspace_id: str, session_id: str) -> int:
        filters = [
            GuideMessage.workspace_id == workspace_id,
            GuideMessage.session_id == session_id,
        ]
        return int(
            self.db.scalar(select(func.count()).select_from(GuideMessage).where(*filters)) or 0
        )
