"""Agent definition entity."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from src.app.enums import AgentKind


@dataclass(slots=True)
class AgentDefinitionEntity:
    id: str
    name: str
    kind: AgentKind
    policy_text: str = ""
    reject_text: str = ""
    clarify_first: bool = False
    published: bool = False
    settings_schema: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
