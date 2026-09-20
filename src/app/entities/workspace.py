"""Workspace domain entity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.app.enums import WorkspaceStatus


@dataclass(slots=True)
class WorkspaceEntity:
    id: str
    name: str
    path: str
    description: str
    status: WorkspaceStatus
    created_at: str
    updated_at: str
    deleted_at: Optional[str] = None
