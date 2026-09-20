"""Workspace chat routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.api.deps import get_chat_service
from src.api.schemas.chat import (
    ChatbotListOut,
    ChatbotOut,
    ChatMessageListOut,
    ChatMessageOut,
    SendMessageIn,
    SendMessageOut,
)
from src.app.constants import DEFAULT_MESSAGE_LIMIT, MAX_PAGE_LIMIT
from src.app.services.chat_service import ChatService

router = APIRouter(tags=["Workspace Chat"])


@router.get("/workspaces/{workspace_id}/chatbots", response_model=ChatbotListOut)
def list_chatbots(
    workspace_id: str,
    svc: ChatService = Depends(get_chat_service),
) -> ChatbotListOut:
    bots = svc.list_chatbots(workspace_id)
    return ChatbotListOut(
        items=[ChatbotOut(id=b.id, name=b.name, role=b.role) for b in bots]
    )


@router.get(
    "/workspaces/{workspace_id}/chatbots/{bot_id}/messages",
    response_model=ChatMessageListOut,
)
def list_messages(
    workspace_id: str,
    bot_id: str,
    limit: int = Query(default=DEFAULT_MESSAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    offset: int = Query(default=0, ge=0),
    svc: ChatService = Depends(get_chat_service),
) -> ChatMessageListOut:
    items, total = svc.list_messages(workspace_id, bot_id, limit=limit, offset=offset)
    return ChatMessageListOut(
        items=[
            ChatMessageOut(id=m.id, role=m.role, text=m.text, at=m.at) for m in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/workspaces/{workspace_id}/chatbots/{bot_id}/messages",
    response_model=SendMessageOut,
)
def send_message(
    workspace_id: str,
    bot_id: str,
    body: SendMessageIn,
    svc: ChatService = Depends(get_chat_service),
) -> SendMessageOut:
    user_msg, assistant_msg = svc.send_message(workspace_id, bot_id, body.text)
    return SendMessageOut(
        user_message=ChatMessageOut(
            id=user_msg.id,
            role=user_msg.role,
            text=user_msg.text,
            at=user_msg.at,
        ),
        assistant_message=ChatMessageOut(
            id=assistant_msg.id,
            role=assistant_msg.role,
            text=assistant_msg.text,
            at=assistant_msg.at,
        ),
    )
