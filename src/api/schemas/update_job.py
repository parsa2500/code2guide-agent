"""Update job DTOs."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from src.app.enums import UpdateJobStatus, UpdateScope


class UpdateStartIn(BaseModel):
    rebuild: bool = True
    scope: UpdateScope = UpdateScope.FULL


class UpdateJobAcceptedOut(BaseModel):
    job_id: str
    status: UpdateJobStatus
    started_at: str


class UpdateJobOut(BaseModel):
    id: str
    started_at: str
    finished_at: Optional[str] = None
    status: UpdateJobStatus
    summary: str
    detail: str


class UpdateJobListOut(BaseModel):
    items: List[UpdateJobOut]
    total: int
    limit: int = 50
    offset: int = 0
