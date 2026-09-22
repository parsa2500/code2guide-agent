"""Workspace agent binding entity."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from src.app.entities.agent_definition import AgentDefinitionEntity


@dataclass(slots=True)
class WorkspaceAgentEntity:
    workspace_id: str
    agent_id: str
    enabled: bool = True
    overrides: Dict[str, Any] = field(default_factory=dict)
    message_count: int = 0
    # Populated when listing with definition join
    definition: Optional[AgentDefinitionEntity] = None
    effective_settings: Dict[str, Any] = field(default_factory=dict)
