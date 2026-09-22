"""Workspace agent binding + agent chat routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from src.api.deps import get_workspace_agent_service
from src.api.schemas.agents import (
    AgentChatIn,
    AgentChatOut,
    AgentDefinitionOut,
    WorkspaceAgentBindIn,
    WorkspaceAgentListOut,
    WorkspaceAgentOut,
    WorkspaceAgentUpdateIn,
)
from src.app.entities.workspace_agent import WorkspaceAgentEntity
from src.app.services.workspace_agent_service import WorkspaceAgentService

router = APIRouter(tags=["Workspace Agents"])


def _out(e: WorkspaceAgentEntity) -> WorkspaceAgentOut:
    definition = None
    if e.definition is not None:
        d = e.definition
        definition = AgentDefinitionOut(
            id=d.id,
            name=d.name,
            kind=d.kind,
            policy_text=d.policy_text,
            reject_text=d.reject_text,
            clarify_first=d.clarify_first,
            published=d.published,
            settings_schema=d.settings_schema or {},
            created_at=d.created_at,
            updated_at=d.updated_at,
        )
    return WorkspaceAgentOut(
        workspace_id=e.workspace_id,
        agent_id=e.agent_id,
        enabled=e.enabled,
        overrides=e.overrides or {},
        effective_settings=e.effective_settings or {},
        definition=definition,
    )


@router.get("/workspaces/{workspace_id}/agents", response_model=WorkspaceAgentListOut)
def list_workspace_agents(
    workspace_id: str,
    svc: WorkspaceAgentService = Depends(get_workspace_agent_service),
) -> WorkspaceAgentListOut:
    items = svc.list_bound(workspace_id)
    return WorkspaceAgentListOut(items=[_out(i) for i in items], total=len(items))


@router.post(
    "/workspaces/{workspace_id}/agents",
    response_model=WorkspaceAgentOut,
    status_code=status.HTTP_201_CREATED,
)
def bind_workspace_agent(
    workspace_id: str,
    body: WorkspaceAgentBindIn,
    svc: WorkspaceAgentService = Depends(get_workspace_agent_service),
) -> WorkspaceAgentOut:
    return _out(svc.bind(workspace_id, body.agent_id))


@router.patch(
    "/workspaces/{workspace_id}/agents/{agent_id}",
    response_model=WorkspaceAgentOut,
)
def update_workspace_agent(
    workspace_id: str,
    agent_id: str,
    body: WorkspaceAgentUpdateIn,
    svc: WorkspaceAgentService = Depends(get_workspace_agent_service),
) -> WorkspaceAgentOut:
    return _out(
        svc.update_binding(
            workspace_id,
            agent_id,
            enabled=body.enabled,
            overrides=body.overrides,
        )
    )


@router.delete(
    "/workspaces/{workspace_id}/agents/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def unbind_workspace_agent(
    workspace_id: str,
    agent_id: str,
    svc: WorkspaceAgentService = Depends(get_workspace_agent_service),
) -> None:
    svc.unbind(workspace_id, agent_id)


@router.post(
    "/workspaces/{workspace_id}/agents/{agent_id}/chat",
    response_model=AgentChatOut,
)
def chat_with_agent(
    workspace_id: str,
    agent_id: str,
    body: AgentChatIn,
    svc: WorkspaceAgentService = Depends(get_workspace_agent_service),
) -> AgentChatOut:
    result = svc.chat(workspace_id, agent_id, body.message)
    return AgentChatOut(
        agent_id=result["agent_id"],
        answer=result["answer"],
        clarify=bool(result.get("clarify")),
        rejected=bool(result.get("rejected")),
        hits=list(result.get("hits") or []),
        effective_settings=dict(result.get("effective_settings") or {}),
    )
