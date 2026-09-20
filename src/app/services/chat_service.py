"""Chat service for workspace chatbots."""

from __future__ import annotations

from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from src.app.entities.chat_message import ChatMessageEntity
from src.app.entities.chatbot import ChatbotEntity
from src.app.enums import ChatRole, ChatbotRole, LogLevel, LogSource
from src.app.exceptions import GuideFailedError, NotFoundError, ValidationAppError
from src.app.ids import new_message_id
from src.app.repositories.chat_message_repo import ChatMessageRepository
from src.app.repositories.chatbot_repo import ChatbotRepository
from src.app.repositories.settings_repo import SettingsRepository
from src.app.repositories.workspace_repo import WorkspaceRepository
from src.app.services.log_service import LogService
from src.app.timeutil import utc_now_iso
from src.core.markdown_guide import normalize_guide_markdown


class ChatService:
    def __init__(self, db: Session):
        self.db = db
        self.workspaces = WorkspaceRepository(db)
        self.chatbots = ChatbotRepository(db)
        self.messages = ChatMessageRepository(db)
        self.settings = SettingsRepository(db)
        self.logs = LogService(db)

    def list_chatbots(self, workspace_id: str) -> List[ChatbotEntity]:
        self._require_active(workspace_id)
        return self.chatbots.list_by_workspace(workspace_id)

    def list_messages(
        self,
        workspace_id: str,
        chatbot_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[ChatMessageEntity], int]:
        self._require_active(workspace_id)
        bot = self.chatbots.get(workspace_id, chatbot_id)
        if bot is None:
            raise NotFoundError("Chatbot not found", code="CHATBOT_NOT_FOUND")
        return self.messages.list_by_bot(workspace_id, chatbot_id, limit=limit, offset=offset)

    def send_message(
        self,
        workspace_id: str,
        chatbot_id: str,
        text: str,
    ) -> Tuple[ChatMessageEntity, ChatMessageEntity]:
        ws = self._require_active(workspace_id)
        bot = self.chatbots.get(workspace_id, chatbot_id)
        if bot is None:
            raise NotFoundError("Chatbot not found", code="CHATBOT_NOT_FOUND")

        cleaned = (text or "").strip()
        if not cleaned:
            raise ValidationAppError("Message text must not be empty", code="EMPTY_TEXT")

        settings = self.settings.get(workspace_id)
        if settings and chatbot_id not in settings.enabled_chatbots:
            raise ValidationAppError("Chatbot is disabled for this workspace", code="CHATBOT_DISABLED")

        now = utc_now_iso()
        user_msg = ChatMessageEntity(
            id=new_message_id(),
            workspace_id=workspace_id,
            chatbot_id=chatbot_id,
            role=ChatRole.USER,
            text=cleaned,
            at=now,
        )

        try:
            guide = self._generate_guide(cleaned, ws.path, bot.role, workspace_id=ws.id)
        except GuideFailedError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise GuideFailedError(str(exc), detail=str(exc)) from exc

        assistant_msg = ChatMessageEntity(
            id=new_message_id(),
            workspace_id=workspace_id,
            chatbot_id=chatbot_id,
            role=ChatRole.ASSISTANT,
            text=guide,
            at=utc_now_iso(),
        )

        try:
            self.messages.create(user_msg)
            self.messages.create(assistant_msg)
            self.logs.append(
                workspace_id,
                level=LogLevel.INFO,
                source=LogSource.CHAT.value,
                message=f"پیام در {chatbot_id}",
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        return user_msg, assistant_msg

    def _generate_guide(
        self,
        query: str,
        workspace_path: str,
        role: ChatbotRole,
        *,
        workspace_id: str | None = None,
    ) -> str:
        from src.agent.workflow import Code2GuideAgent

        agent = Code2GuideAgent(workspace_path=workspace_path, workspace_id=workspace_id)
        audience = "end_user" if role == ChatbotRole.END_USER else None
        try:
            if audience:
                state = agent.ask(query=query, workspace_path=workspace_path, audience=audience)
            else:
                state = agent.ask(query=query, workspace_path=workspace_path)
        except Exception as exc:  # noqa: BLE001
            raise GuideFailedError(f"Guide generation failed: {exc}", detail=str(exc)) from exc

        guide = normalize_guide_markdown(
            state.final_persian_guide
            or (
                "در راهنمای سامانه چیزی پیدا نشد."
                if role == ChatbotRole.END_USER
                else "راهنمایی یافت نشد."
            )
        )
        return guide

    def _require_active(self, workspace_id: str):
        ws = self.workspaces.get(workspace_id)
        if ws is None or ws.deleted_at is not None:
            raise NotFoundError("Workspace not found", code="WORKSPACE_NOT_FOUND")
        return ws
