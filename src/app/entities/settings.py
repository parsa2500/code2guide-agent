"""Workspace settings entity."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from src.app.enums import AudienceDefault


@dataclass(slots=True)
class WorkspaceSettingsEntity:
    workspace_id: str
    default_agent: str
    enabled_chatbots: List[str] = field(default_factory=list)
    audience_default: AudienceDefault = AudienceDefault.END_USER
    auto_index: bool = True
    mcp_enabled: bool = False
