"""Activity log entity."""

from __future__ import annotations

from dataclasses import dataclass

from src.app.enums import LogLevel


@dataclass(slots=True)
class ActivityLogEntity:
    id: str
    workspace_id: str
    at: str
    level: LogLevel
    source: str
    message: str
