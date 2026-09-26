"""Guide session repository."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.app.entities.guide_session import GuideSessionEntity
from src.db.models.guide_session import GuideSession


def _to_entity(row: GuideSession) -> GuideSessionEntity:
    return GuideSessionEntity(
        id=row.id,
        workspace_id=row.workspace_id,
        title=row.title,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class GuideSessionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, entity: GuideSessionEntity) -> GuideSessionEntity:
        row = GuideSession(
            id=entity.id,
            workspace_id=entity.workspace_id,
            title=entity.title,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
        self.db.add(row)
        self.db.flush()
        return _to_entity(row)

    def get(self, workspace_id: str, session_id: str) -> Optional[GuideSessionEntity]:
        row = self.db.get(GuideSession, session_id)
        if row is None or row.workspace_id != workspace_id:
            return None
        return _to_entity(row)

    def list_by_workspace(self, workspace_id: str) -> List[GuideSessionEntity]:
        stmt = (
            select(GuideSession)
            .where(GuideSession.workspace_id == workspace_id)
            .order_by(GuideSession.updated_at.desc())
        )
        return [_to_entity(r) for r in self.db.scalars(stmt).all()]

    def update_title(self, workspace_id: str, session_id: str, title: str, updated_at: str) -> Optional[GuideSessionEntity]:
        row = self.db.get(GuideSession, session_id)
        if row is None or row.workspace_id != workspace_id:
            return None
        row.title = title
        row.updated_at = updated_at
        self.db.flush()
        return _to_entity(row)

    def touch(self, workspace_id: str, session_id: str, updated_at: str) -> None:
        row = self.db.get(GuideSession, session_id)
        if row is None or row.workspace_id != workspace_id:
            return
        row.updated_at = updated_at
        self.db.flush()

    def delete(self, workspace_id: str, session_id: str) -> bool:
        row = self.db.get(GuideSession, session_id)
        if row is None or row.workspace_id != workspace_id:
            return False
        self.db.delete(row)
        self.db.flush()
        return True
