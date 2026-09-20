"""Workspace repository."""

from __future__ import annotations

from typing import List, Optional, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from src.app.entities.workspace import WorkspaceEntity
from src.app.enums import WorkspaceStatus
from src.db.models.workspace import Workspace


def _to_entity(row: Workspace) -> WorkspaceEntity:
    return WorkspaceEntity(
        id=row.id,
        name=row.name,
        path=row.path,
        description=row.description or "",
        status=WorkspaceStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
    )


class WorkspaceRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, entity: WorkspaceEntity) -> WorkspaceEntity:
        row = Workspace(
            id=entity.id,
            name=entity.name,
            path=entity.path,
            description=entity.description,
            status=entity.status.value,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            deleted_at=entity.deleted_at,
        )
        self.db.add(row)
        self.db.flush()
        return _to_entity(row)

    def get(self, workspace_id: str) -> Optional[WorkspaceEntity]:
        row = self.db.get(Workspace, workspace_id)
        return _to_entity(row) if row else None

    def get_by_path_active(self, path: str) -> Optional[WorkspaceEntity]:
        stmt = select(Workspace).where(
            Workspace.path == path,
            Workspace.deleted_at.is_(None),
        )
        row = self.db.scalars(stmt).first()
        return _to_entity(row) if row else None

    def list_active(
        self,
        *,
        q: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[WorkspaceEntity], int]:
        filters = [Workspace.deleted_at.is_(None)]
        if status:
            filters.append(Workspace.status == status)
        if q:
            like = f"%{q}%"
            filters.append(
                or_(
                    Workspace.name.ilike(like),
                    Workspace.path.ilike(like),
                    Workspace.description.ilike(like),
                )
            )
        count_stmt = select(func.count()).select_from(Workspace).where(*filters)
        total = int(self.db.scalar(count_stmt) or 0)
        stmt = (
            select(Workspace)
            .where(*filters)
            .order_by(Workspace.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = list(self.db.scalars(stmt).all())
        return [_to_entity(r) for r in rows], total

    def list_deleted(
        self,
        *,
        q: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[WorkspaceEntity], int]:
        filters = [Workspace.deleted_at.is_not(None)]
        if q:
            like = f"%{q}%"
            filters.append(
                or_(
                    Workspace.name.ilike(like),
                    Workspace.path.ilike(like),
                    Workspace.description.ilike(like),
                )
            )
        count_stmt = select(func.count()).select_from(Workspace).where(*filters)
        total = int(self.db.scalar(count_stmt) or 0)
        stmt = (
            select(Workspace)
            .where(*filters)
            .order_by(Workspace.deleted_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = list(self.db.scalars(stmt).all())
        return [_to_entity(r) for r in rows], total

    def update(self, entity: WorkspaceEntity) -> WorkspaceEntity:
        row = self.db.get(Workspace, entity.id)
        if row is None:
            raise KeyError(entity.id)
        row.name = entity.name
        row.path = entity.path
        row.description = entity.description
        row.status = entity.status.value
        row.updated_at = entity.updated_at
        row.deleted_at = entity.deleted_at
        self.db.flush()
        return _to_entity(row)
