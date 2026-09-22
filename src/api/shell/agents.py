"""Agent registry routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from src.api.deps import get_agent_service
from src.api.schemas.agents import (
    AgentCreateIn,
    AgentDefinitionListOut,
    AgentDefinitionOut,
    AgentPublishIn,
    AgentUpdateIn,
)
from src.app.entities.agent_definition import AgentDefinitionEntity
from src.app.services.agent_service import AgentService

router = APIRouter(tags=["Agents"])


def _out(e: AgentDefinitionEntity) -> AgentDefinitionOut:
    return AgentDefinitionOut(
        id=e.id,
        name=e.name,
        kind=e.kind,
        policy_text=e.policy_text,
        reject_text=e.reject_text,
        clarify_first=e.clarify_first,
        published=e.published,
        settings_schema=e.settings_schema or {},
        created_at=e.created_at,
        updated_at=e.updated_at,
    )


@router.get("/agents", response_model=AgentDefinitionListOut)
def list_agents(svc: AgentService = Depends(get_agent_service)) -> AgentDefinitionListOut:
    items = svc.list_definitions()
    return AgentDefinitionListOut(items=[_out(i) for i in items], total=len(items))


@router.post("/agents", response_model=AgentDefinitionOut, status_code=status.HTTP_201_CREATED)
def create_agent(
    body: AgentCreateIn,
    svc: AgentService = Depends(get_agent_service),
) -> AgentDefinitionOut:
    entity = svc.create(
        id=body.id,
        name=body.name,
        kind=body.kind,
        policy_text=body.policy_text,
        reject_text=body.reject_text,
        clarify_first=body.clarify_first,
        settings_schema=body.settings_schema,
        published=body.published,
    )
    return _out(entity)


@router.get("/agents/{agent_id}", response_model=AgentDefinitionOut)
def get_agent(
    agent_id: str,
    svc: AgentService = Depends(get_agent_service),
) -> AgentDefinitionOut:
    return _out(svc.get(agent_id))


@router.patch("/agents/{agent_id}", response_model=AgentDefinitionOut)
def update_agent(
    agent_id: str,
    body: AgentUpdateIn,
    svc: AgentService = Depends(get_agent_service),
) -> AgentDefinitionOut:
    entity = svc.update(
        agent_id,
        name=body.name,
        kind=body.kind,
        policy_text=body.policy_text,
        reject_text=body.reject_text,
        clarify_first=body.clarify_first,
        settings_schema=body.settings_schema,
    )
    return _out(entity)


@router.post("/agents/{agent_id}/publish", response_model=AgentDefinitionOut)
def publish_agent(
    agent_id: str,
    body: AgentPublishIn,
    svc: AgentService = Depends(get_agent_service),
) -> AgentDefinitionOut:
    return _out(svc.set_published(agent_id, body.published))
