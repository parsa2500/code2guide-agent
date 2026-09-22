"""Seed agent definitions and migrate workspace_agents bindings.

Migration path (slice-1):
- Keep creating legacy Chatbot rows for AskConsole / chatbots UI.
- ALSO upsert workspace_agents for bot_user + bot_tech (+ jarvis on new workspaces).
- migrate_workspace_agent_bindings() backfills existing workspaces.
"""

from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy.orm import Session

from src.app.constants import (
    DEFAULT_AGENT_JARVIS_ID,
    DEFAULT_AGENT_JARVIS_NAME,
    DEFAULT_CHATBOT_TECH_ID,
    DEFAULT_CHATBOT_TECH_NAME,
    DEFAULT_CHATBOT_USER_ID,
    DEFAULT_CHATBOT_USER_NAME,
)
from src.app.entities.agent_definition import AgentDefinitionEntity
from src.app.enums import AgentKind
from src.app.repositories.agent_definition_repo import AgentDefinitionRepository
from src.app.repositories.workspace_agent_repo import WorkspaceAgentRepository
from src.app.timeutil import utc_now_iso
from src.db.models.workspace import Workspace
from src.db.models.workspace_agent import WorkspaceAgent
from sqlalchemy import select


SEED_SPECS = (
    {
        "id": DEFAULT_AGENT_JARVIS_ID,
        "name": DEFAULT_AGENT_JARVIS_NAME,
        "kind": AgentKind.JARVIS,
    },
    {
        "id": DEFAULT_CHATBOT_USER_ID,
        "name": DEFAULT_CHATBOT_USER_NAME,
        "kind": AgentKind.END_USER,
    },
    {
        "id": DEFAULT_CHATBOT_TECH_ID,
        "name": DEFAULT_CHATBOT_TECH_NAME,
        "kind": AgentKind.TECHNICAL,
    },
)

# Agents bound on every new workspace (chatbots stay in sync for legacy UI).
DEFAULT_WORKSPACE_BINDINGS = (
    DEFAULT_CHATBOT_USER_ID,
    DEFAULT_CHATBOT_TECH_ID,
    DEFAULT_AGENT_JARVIS_ID,
)


def ensure_seed_agents(db: Session) -> None:
    """Upsert the three published seed agent definitions."""
    repo = AgentDefinitionRepository(db)
    now = utc_now_iso()
    for spec in SEED_SPECS:
        existing = repo.get(spec["id"])
        if existing is None:
            repo.upsert(
                AgentDefinitionEntity(
                    id=spec["id"],
                    name=spec["name"],
                    kind=spec["kind"],
                    policy_text="",
                    reject_text="",
                    clarify_first=False,
                    published=True,
                    settings_schema={},
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            # Keep published=true and names aligned with constants for seeds.
            repo.update_fields(
                spec["id"],
                name=spec["name"],
                kind=spec["kind"],
                published=True,
                updated_at=now,
            )
    db.flush()


def bind_default_agents(
    db: Session,
    workspace_id: str,
    *,
    agent_ids: Optional[Iterable[str]] = None,
) -> None:
    """Upsert workspace_agents for default (or given) agent ids if missing."""
    ensure_seed_agents(db)
    wa = WorkspaceAgentRepository(db)
    for agent_id in agent_ids or DEFAULT_WORKSPACE_BINDINGS:
        row = db.get(WorkspaceAgent, {"workspace_id": workspace_id, "agent_id": agent_id})
        if row is None:
            wa.upsert(workspace_id, agent_id, enabled=True, overrides={})
    db.flush()


def migrate_workspace_agent_bindings(db: Session) -> int:
    """For each existing workspace, upsert bot_user/bot_tech/jarvis bindings if missing.

    Returns number of bindings created.
    """
    ensure_seed_agents(db)
    created = 0
    wa = WorkspaceAgentRepository(db)
    stmt = select(Workspace.id)
    for workspace_id in db.scalars(stmt).all():
        for agent_id in DEFAULT_WORKSPACE_BINDINGS:
            row = db.get(
                WorkspaceAgent,
                {"workspace_id": workspace_id, "agent_id": agent_id},
            )
            if row is None:
                wa.upsert(workspace_id, agent_id, enabled=True, overrides={})
                created += 1
    db.flush()
    return created
