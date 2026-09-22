"""Agent definition repository."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.app.entities.agent_definition import AgentDefinitionEntity
from src.app.enums import AgentKind
from src.db.models.agent_definition import AgentDefinition


def _parse_schema(raw: str) -> Dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _to_entity(row: AgentDefinition) -> AgentDefinitionEntity:
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


class AgentDefinitionRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self) -> List[AgentDefinitionEntity]:
        stmt = select(AgentDefinition).order_by(AgentDefinition.id)
        return [_to_entity(r) for r in self.db.scalars(stmt).all()]

    def get(self, agent_id: str) -> Optional[AgentDefinitionEntity]:
        row = self.db.get(AgentDefinition, agent_id)
        return _to_entity(row) if row else None

    def upsert(self, entity: AgentDefinitionEntity) -> AgentDefinitionEntity:
        row = self.db.get(AgentDefinition, entity.id)
        schema_json = json.dumps(entity.settings_schema or {}, ensure_ascii=False)
        if row is None:
            row = AgentDefinition(
                id=entity.id,
                name=entity.name,
                kind=entity.kind.value,
                policy_text=entity.policy_text or "",
                reject_text=entity.reject_text or "",
                clarify_first=entity.clarify_first,
                published=entity.published,
                settings_schema=schema_json,
                created_at=entity.created_at,
                updated_at=entity.updated_at,
            )
            self.db.add(row)
        else:
            row.name = entity.name
            row.kind = entity.kind.value
            row.policy_text = entity.policy_text or ""
            row.reject_text = entity.reject_text or ""
            row.clarify_first = entity.clarify_first
            row.published = entity.published
            row.settings_schema = schema_json
            row.updated_at = entity.updated_at
        self.db.flush()
        return _to_entity(row)

    def update_fields(
        self,
        agent_id: str,
        *,
        name: Optional[str] = None,
        kind: Optional[AgentKind] = None,
        policy_text: Optional[str] = None,
        reject_text: Optional[str] = None,
        clarify_first: Optional[bool] = None,
        settings_schema: Optional[Dict[str, Any]] = None,
        published: Optional[bool] = None,
        updated_at: str,
    ) -> Optional[AgentDefinitionEntity]:
        row = self.db.get(AgentDefinition, agent_id)
        if row is None:
            return None
        if name is not None:
            row.name = name
        if kind is not None:
            row.kind = kind.value
        if policy_text is not None:
            row.policy_text = policy_text
        if reject_text is not None:
            row.reject_text = reject_text
        if clarify_first is not None:
            row.clarify_first = clarify_first
        if settings_schema is not None:
            row.settings_schema = json.dumps(settings_schema, ensure_ascii=False)
        if published is not None:
            row.published = published
        row.updated_at = updated_at
        self.db.flush()
        return _to_entity(row)
