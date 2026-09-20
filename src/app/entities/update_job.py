"""Update job entity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.app.enums import UpdateJobStatus, UpdateScope


@dataclass(slots=True)
class UpdateJobEntity:
    id: str
    workspace_id: str
    started_at: str
    finished_at: Optional[str]
    status: UpdateJobStatus
    summary: str
    detail: str
    rebuild: bool
    scope: UpdateScope
