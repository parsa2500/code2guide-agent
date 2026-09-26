"""Guide chat routes — sessions + SSE message stream."""

from __future__ import annotations

import json
from typing import Iterator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from src.api.deps import get_guide_chat_service
from src.api.schemas.guide_chat import (
    GuideMessageListOut,
    GuideMessageOut,
    GuideSendMessageIn,
    GuideSessionListOut,
    GuideSessionOut,
)
from src.app.constants import DEFAULT_MESSAGE_LIMIT, MAX_PAGE_LIMIT
from src.app.services.guide_chat_service import GuideChatService

router = APIRouter(tags=["Guide Chat"])


def _sse_pack(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


@router.get("/workspaces/{workspace_id}/guide-sessions", response_model=GuideSessionListOut)
def list_guide_sessions(
    workspace_id: str,
    svc: GuideChatService = Depends(get_guide_chat_service),
) -> GuideSessionListOut:
    items = svc.list_sessions(workspace_id)
    return GuideSessionListOut(
        items=[
            GuideSessionOut(
                id=s.id,
                title=s.title,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in items
        ]
    )


@router.post("/workspaces/{workspace_id}/guide-sessions", response_model=GuideSessionOut)
def create_guide_session(
    workspace_id: str,
    svc: GuideChatService = Depends(get_guide_chat_service),
) -> GuideSessionOut:
    s = svc.create_session(workspace_id)
    return GuideSessionOut(
        id=s.id,
        title=s.title,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


@router.delete("/workspaces/{workspace_id}/guide-sessions/{session_id}", status_code=204)
def delete_guide_session(
    workspace_id: str,
    session_id: str,
    svc: GuideChatService = Depends(get_guide_chat_service),
) -> None:
    svc.delete_session(workspace_id, session_id)


@router.get(
    "/workspaces/{workspace_id}/guide-sessions/{session_id}/messages",
    response_model=GuideMessageListOut,
)
def list_guide_messages(
    workspace_id: str,
    session_id: str,
    limit: int = Query(default=DEFAULT_MESSAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    offset: int = Query(default=0, ge=0),
    svc: GuideChatService = Depends(get_guide_chat_service),
) -> GuideMessageListOut:
    items, total = svc.list_messages(
        workspace_id, session_id, limit=limit, offset=offset
    )
    return GuideMessageListOut(
        items=[
            GuideMessageOut(
                id=m.id,
                role=m.role,
                text=m.text,
                at=m.at,
                steps=m.steps,
            )
            for m in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/workspaces/{workspace_id}/guide-sessions/{session_id}/messages/stream")
def stream_guide_message(
    workspace_id: str,
    session_id: str,
    body: GuideSendMessageIn,
    svc: GuideChatService = Depends(get_guide_chat_service),
) -> StreamingResponse:
    def event_iter() -> Iterator[str]:
        for evt in svc.stream_turn(workspace_id, session_id, body.text):
            yield _sse_pack(str(evt.get("event") or "message"), evt.get("data") or {})

    return StreamingResponse(
        event_iter(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
