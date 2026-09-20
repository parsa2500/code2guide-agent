"""Settings DTOs."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from src.app.enums import AudienceDefault


class WorkspaceSettingsIn(BaseModel):
    default_agent: str = Field(..., min_length=1)
    enabled_chatbots: List[str]
    audience_default: AudienceDefault
    auto_index: bool
    mcp_enabled: bool


class WorkspaceSettingsOut(BaseModel):
    default_agent: str
    enabled_chatbots: List[str]
    audience_default: AudienceDefault
    auto_index: bool
    mcp_enabled: bool
