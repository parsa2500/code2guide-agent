"""Activity log DTOs."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel

from src.app.enums import LogLevel


class ActivityLogOut(BaseModel):
    id: str
    at: str
    level: LogLevel
    source: str
    message: str


class ActivityLogListOut(BaseModel):
    items: List[ActivityLogOut]
    total: int
    limit: int = 50
    offset: int = 0
