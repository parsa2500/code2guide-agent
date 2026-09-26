"""Guide chat session entity."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class GuideSessionEntity:
    id: str
    workspace_id: str
    title: str
    created_at: str
    updated_at: str
