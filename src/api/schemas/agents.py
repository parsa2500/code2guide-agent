"""Agent registry and workspace binding schemas."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from src.app.enums import AgentKind


class AgentDefinitionOut(BaseModel):
    id: str
    name: str
    kind: AgentKind
    policy_text: str = ""
    reject_text: str = ""
    clarify_first: bool = False
    published: bool = False
    settings_schema: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class AgentDefinitionListOut(BaseModel):
    items: List[AgentDefinitionOut]
    total: int


class AgentCreateIn(BaseModel):
    id: Optional[str] = None
    name: str
    kind: AgentKind = AgentKind.CUSTOM
    policy_text: str = ""
    reject_text: str = ""
    clarify_first: bool = False
    settings_schema: Dict[str, Any] = Field(default_factory=dict)
    published: bool = False


class AgentUpdateIn(BaseModel):
    name: Optional[str] = None
    kind: Optional[AgentKind] = None
    policy_text: Optional[str] = None
    reject_text: Optional[str] = None
    clarify_first: Optional[bool] = None
    settings_schema: Optional[Dict[str, Any]] = None


class AgentPublishIn(BaseModel):
    published: bool


class WorkspaceAgentBindIn(BaseModel):
    agent_id: str


class WorkspaceAgentUpdateIn(BaseModel):
    enabled: Optional[bool] = None
    overrides: Optional[Dict[str, Any]] = None


class WorkspaceAgentOut(BaseModel):
    workspace_id: str
    agent_id: str
    enabled: bool
    overrides: Dict[str, Any] = Field(default_factory=dict)
    effective_settings: Dict[str, Any] = Field(default_factory=dict)
    definition: Optional[AgentDefinitionOut] = None


class WorkspaceAgentListOut(BaseModel):
    items: List[WorkspaceAgentOut]
    total: int


class AgentChatIn(BaseModel):
    message: str


class AgentChatOut(BaseModel):
    agent_id: str
    answer: str
    clarify: bool = False
    rejected: bool = False
    hits: List[Dict[str, Any]] = Field(default_factory=list)
    effective_settings: Dict[str, Any] = Field(default_factory=dict)


class BrainSettingsOut(BaseModel):
    qdrant_url: Optional[str] = None
    qdrant_location: Optional[str] = None
    embedding_provider: str
    embedding_model: str
    embedding_dim: int
    persistence: Optional[str] = None


class BrainSettingsUpdateIn(BaseModel):
    qdrant_url: Optional[str] = None
    qdrant_location: Optional[str] = None
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None
    embedding_dim: Optional[int] = None
