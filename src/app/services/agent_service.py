"""Agent registry service."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.app.entities.agent_definition import AgentDefinitionEntity
from src.app.enums import AgentKind
from src.app.exceptions import ConflictError, NotFoundError, ValidationAppError
from src.app.repositories.agent_definition_repo import AgentDefinitionRepository
from src.app.services.agent_seed import ensure_seed_agents, migrate_workspace_agent_bindings
from src.app.timeutil import utc_now_iso

_CUSTOM_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,62}$")


def _validate_settings_schema(schema: Any) -> Dict[str, Any]:
    if schema is None:
        return {}
    if isinstance(schema, str):
        try:
            schema = json.loads(schema)
        except json.JSONDecodeError as exc:
            raise ValidationAppError(
                "settings_schema must be valid JSON",
                code="INVALID_SETTINGS_SCHEMA",
                detail=str(exc),
            ) from exc
    if not isinstance(schema, dict):
        raise ValidationAppError(
            "settings_schema must be a JSON object",
            code="INVALID_SETTINGS_SCHEMA",
        )
    for key, meta in schema.items():
        if not isinstance(key, str) or not key:
            raise ValidationAppError(
                "settings_schema keys must be non-empty strings",
                code="INVALID_SETTINGS_SCHEMA",
            )
        if meta is None:
            continue
        if not isinstance(meta, dict):
            raise ValidationAppError(
                f"settings_schema[{key}] must be an object with default/workspace_overridable",
                code="INVALID_SETTINGS_SCHEMA",
            )
        if "workspace_overridable" in meta and not isinstance(meta["workspace_overridable"], bool):
            raise ValidationAppError(
                f"settings_schema[{key}].workspace_overridable must be bool",
                code="INVALID_SETTINGS_SCHEMA",
            )
    return schema


class AgentService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = AgentDefinitionRepository(db)

    def ensure_ready(self) -> None:
        """Seed definitions + migrate bindings (idempotent)."""
        ensure_seed_agents(self.db)
        migrate_workspace_agent_bindings(self.db)
        self.db.commit()

    def list_definitions(self) -> List[AgentDefinitionEntity]:
        ensure_seed_agents(self.db)
        migrate_workspace_agent_bindings(self.db)
        self.db.commit()
        return self.repo.list_all()

    def get(self, agent_id: str) -> AgentDefinitionEntity:
        ensure_seed_agents(self.db)
        self.db.flush()
        entity = self.repo.get(agent_id)
        if entity is None:
            raise NotFoundError("Agent not found", code="AGENT_NOT_FOUND")
        return entity

    def create(
        self,
        *,
        id: Optional[str] = None,
        name: str,
        kind: AgentKind = AgentKind.CUSTOM,
        policy_text: str = "",
        reject_text: str = "",
        clarify_first: bool = False,
        settings_schema: Optional[Any] = None,
        published: bool = False,
    ) -> AgentDefinitionEntity:
        ensure_seed_agents(self.db)
        cleaned_name = (name or "").strip()
        if not cleaned_name:
            raise ValidationAppError("Name must not be empty", code="INVALID_NAME")
        schema = _validate_settings_schema(settings_schema)
        agent_id = (id or "").strip() or re.sub(r"[^a-z0-9_]+", "_", cleaned_name.lower()).strip("_")
        if not _CUSTOM_ID_RE.match(agent_id):
            raise ValidationAppError(
                "id must match ^[a-z][a-z0-9_]{1,62}$",
                code="INVALID_AGENT_ID",
            )
        if self.repo.get(agent_id) is not None:
            raise ConflictError("Agent id already exists", code="AGENT_EXISTS")
        if kind not in AgentKind:
            raise ValidationAppError("Invalid kind", code="INVALID_KIND")
        now = utc_now_iso()
        entity = AgentDefinitionEntity(
            id=agent_id,
            name=cleaned_name,
            kind=kind if isinstance(kind, AgentKind) else AgentKind(kind),
            policy_text=policy_text or "",
            reject_text=reject_text or "",
            clarify_first=bool(clarify_first),
            published=bool(published),
            settings_schema=schema,
            created_at=now,
            updated_at=now,
        )
        saved = self.repo.upsert(entity)
        self.db.commit()
        return saved

    def update(
        self,
        agent_id: str,
        *,
        name: Optional[str] = None,
        kind: Optional[AgentKind] = None,
        policy_text: Optional[str] = None,
        reject_text: Optional[str] = None,
        clarify_first: Optional[bool] = None,
        settings_schema: Optional[Any] = None,
    ) -> AgentDefinitionEntity:
        if self.repo.get(agent_id) is None:
            raise NotFoundError("Agent not found", code="AGENT_NOT_FOUND")
        schema = None
        if settings_schema is not None:
            schema = _validate_settings_schema(settings_schema)
        if name is not None:
            name = name.strip()
            if not name:
                raise ValidationAppError("Name must not be empty", code="INVALID_NAME")
        saved = self.repo.update_fields(
            agent_id,
            name=name,
            kind=kind,
            policy_text=policy_text,
            reject_text=reject_text,
            clarify_first=clarify_first,
            settings_schema=schema,
            updated_at=utc_now_iso(),
        )
        self.db.commit()
        assert saved is not None
        return saved

    def set_published(self, agent_id: str, published: bool) -> AgentDefinitionEntity:
        if self.repo.get(agent_id) is None:
            raise NotFoundError("Agent not found", code="AGENT_NOT_FOUND")
        saved = self.repo.update_fields(
            agent_id,
            published=bool(published),
            updated_at=utc_now_iso(),
        )
        self.db.commit()
        assert saved is not None
        return saved
