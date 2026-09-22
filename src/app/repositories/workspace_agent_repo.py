"""Workspace agent binding repository."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.app.entities.agent_definition import AgentDefinitionEntity
from src.app.entities.workspace_agent import WorkspaceAgentEntity
from src.app.enums import AgentKind
from src.db.models.agent_definition import AgentDefinition
from src.db.models.workspace_agent import WorkspaceAgent


def _parse_overrides(raw: str) -> Dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _parse_schema(raw: str) -> Dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _def_entity(row: AgentDefinition) -> AgentDefinitionEntity:
    return AgentDefinitionEntity(
        id=row.id,
        name=row.name,
        kind=AgentKind(row.kind),
        policy_text=row.policy_text or "",
        reject_text=row.reject_text or "",
        clarify_first=bool(row.clarify_first),
        published=bool(row.published),
        settings_schema=_parse_schema(row.settings_schema),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_entity(row: WorkspaceAgent, definition: Optional[AgentDefinition] = None) -> WorkspaceAgentEntity:
    ent = WorkspaceAgentEntity(
        workspace_id=row.workspace_id,
        agent_id=row.agent_id,
        enabled=bool(row.enabled),
        overrides=_parse_overrides(row.overrides),
        message_count=int(row.message_count or 0),
    )
    if definition is not None:
        ent.definition = _def_entity(definition)
    return ent


def merge_effective_settings(
    schema: Dict[str, Any],
    overrides: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge schema defaults with workspace overrides (only overridable keys)."""
    effective: Dict[str, Any] = {}
    for key, meta in (schema or {}).items():
        if isinstance(meta, dict):
            effective[key] = meta.get("default")
        else:
            effective[key] = meta
    for key, value in (overrides or {}).items():
        meta = (schema or {}).get(key)
        if isinstance(meta, dict) and meta.get("workspace_overridable"):
            effective[key] = value
    return effective


class WorkspaceAgentRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_by_workspace(self, workspace_id: str) -> List[WorkspaceAgentEntity]:
        stmt = (
            select(WorkspaceAgent, AgentDefinition)
            .join(AgentDefinition, AgentDefinition.id == WorkspaceAgent.agent_id)
            .where(WorkspaceAgent.workspace_id == workspace_id)
            .order_by(WorkspaceAgent.agent_id)
        )
        results: List[WorkspaceAgentEntity] = []
        for binding, definition in self.db.execute(stmt).all():
            ent = _to_entity(binding, definition)
            ent.effective_settings = merge_effective_settings(
                ent.definition.settings_schema if ent.definition else {},
                ent.overrides,
            )
            results.append(ent)
        return results

    def get(self, workspace_id: str, agent_id: str) -> Optional[WorkspaceAgentEntity]:
        stmt = (
            select(WorkspaceAgent, AgentDefinition)
            .join(AgentDefinition, AgentDefinition.id == WorkspaceAgent.agent_id)
            .where(
                WorkspaceAgent.workspace_id == workspace_id,
                WorkspaceAgent.agent_id == agent_id,
            )
        )
        row = self.db.execute(stmt).first()
        if row is None:
            return None
        binding, definition = row
        ent = _to_entity(binding, definition)
        ent.effective_settings = merge_effective_settings(
            ent.definition.settings_schema if ent.definition else {},
            ent.overrides,
        )
        return ent

    def upsert(
        self,
        workspace_id: str,
        agent_id: str,
        *,
        enabled: bool = True,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> WorkspaceAgentEntity:
        row = self.db.get(WorkspaceAgent, {"workspace_id": workspace_id, "agent_id": agent_id})
        if row is None:
            row = WorkspaceAgent(
                workspace_id=workspace_id,
                agent_id=agent_id,
                enabled=enabled,
                overrides=json.dumps(overrides or {}, ensure_ascii=False),
                message_count=0,
            )
            self.db.add(row)
        else:
            row.enabled = enabled
            if overrides is not None:
                row.overrides = json.dumps(overrides, ensure_ascii=False)
        self.db.flush()
        return self.get(workspace_id, agent_id)  # type: ignore[return-value]

    def update(
        self,
        workspace_id: str,
        agent_id: str,
        *,
        enabled: Optional[bool] = None,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> Optional[WorkspaceAgentEntity]:
        row = self.db.get(WorkspaceAgent, {"workspace_id": workspace_id, "agent_id": agent_id})
        if row is None:
            return None
        if enabled is not None:
            row.enabled = enabled
        if overrides is not None:
            row.overrides = json.dumps(overrides, ensure_ascii=False)
        self.db.flush()
        return self.get(workspace_id, agent_id)

    def delete(self, workspace_id: str, agent_id: str) -> bool:
        row = self.db.get(WorkspaceAgent, {"workspace_id": workspace_id, "agent_id": agent_id})
        if row is None:
            return False
        self.db.delete(row)
        self.db.flush()
        return True

    def increment_message_count(self, workspace_id: str, agent_id: str) -> int:
        row = self.db.get(WorkspaceAgent, {"workspace_id": workspace_id, "agent_id": agent_id})
        if row is None:
            return 0
        row.message_count = int(row.message_count or 0) + 1
        self.db.flush()
        return int(row.message_count)

    def list_workspace_ids(self) -> List[str]:
        from src.db.models.workspace import Workspace

        stmt = select(Workspace.id).where(Workspace.deleted_at.is_(None))
        return list(self.db.scalars(stmt).all())
