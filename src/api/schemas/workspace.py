"""Workspace DTOs."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from src.api.schemas.settings import WorkspaceSettingsOut
from src.app.enums import WorkspaceStatus


class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1)
    path: str = Field(..., min_length=1)
    description: str = ""


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    path: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = None


class WorkspaceOut(BaseModel):
    id: str
    name: str
    path: str
    description: str
    status: WorkspaceStatus
    updated_at: str
    deleted_at: Optional[str] = None


class WorkspaceDetailOut(WorkspaceOut):
    created_at: str
    settings: WorkspaceSettingsOut


class WorkspaceListOut(BaseModel):
    items: List[WorkspaceOut]
    total: int
    limit: int = 50
    offset: int = 0
