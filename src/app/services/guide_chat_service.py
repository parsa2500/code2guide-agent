"""Guide chat orchestration: Support → brain workflow → Jarvis with SSE events."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Generator, List, Optional

from sqlalchemy.orm import Session

from src.agent.state import AgentState
from src.agent.workflow import Code2GuideWorkflow
from src.app.constants import DEFAULT_CHATBOT_USER_ID
from src.app.entities.guide_message import GuideMessageEntity
from src.app.entities.guide_session import GuideSessionEntity
from src.app.enums import ChatRole, LogLevel, LogSource
from src.app.exceptions import NotFoundError, ValidationAppError
from src.app.ids import new_guide_message_id, new_guide_session_id
from src.app.repositories.agent_definition_repo import AgentDefinitionRepository
from src.app.repositories.guide_message_repo import GuideMessageRepository
from src.app.repositories.guide_session_repo import GuideSessionRepository
from src.app.repositories.workspace_repo import WorkspaceRepository
from src.app.services.llm_client import chat_completion
from src.app.services.log_service import LogService
from src.app.timeutil import utc_now_iso
from src.core.markdown_guide import normalize_guide_markdown

DEFAULT_SESSION_TITLE = "Session جدید"

SUPPORT_SYSTEM = """شما لایه Support برای چت راهنمای Code2Guide هستید.
وظیفه: فهم پیام کاربر، بررسی سیاست (policy)، و یکی از دو خروجی JSON خالص (بدون markdown):

1) اگر پیام مبهم است یا با policy سازگار نیست یا نیاز به روشن‌سازی دارد:
{"action":"clarify","message":"سوال کوتاه فارسی برای روشن شدن هدف کاربر"}

2) اگر واضح و مجاز است:
{"action":"proceed","enhanced_prompt":"پرسش تقویت‌شده و دقیق فارسی برای موتور راهنما"}

فقط JSON برگردانید."""

JARVIS_SYSTEM = """شما Jarvis هستید. فقط از شواهد و داده‌های داده‌شده در پرامپت ورودی جواب نهایی کاربرپسند به فارسی بسازید.
چیزی اختراع نکنید. اگر شاهد کافی نیست صادقانه بگویید. بدون ذکر نام فایل/API مگر در شواهد آمده باشد.
خروجی: متن راهنمای نهایی برای کاربر (markdown ساده مجاز است)."""


def _title_from_message(text: str) -> str:
    cleaned = (text or "").strip().replace("\n", " ")
    if not cleaned:
        return DEFAULT_SESSION_TITLE
    return cleaned[:48]


def _extract_json_object(raw: str) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    text = raw.strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _fallback_support(user_text: str) -> Dict[str, str]:
    t = (user_text or "").strip()
    ambiguous = (
        len(t) < 8
        or t in ("سلام", "درود", "hi", "hello", "؟", "?")
        or t.endswith("؟") and len(t) < 16
    )
    if ambiguous:
        return {
            "action": "clarify",
            "message": (
                "قبل از ادامه، یک سوال کوتاه: دقیقاً می‌خواهید به چه نتیجه‌ای برسید؟ "
                "(هدف، صفحه/فرم، یا نقش کاربری را بگویید.)"
            ),
        }
    return {"action": "proceed", "enhanced_prompt": t}


class GuideChatService:
    def __init__(self, db: Session):
        self.db = db
        self.workspaces = WorkspaceRepository(db)
        self.sessions = GuideSessionRepository(db)
        self.messages = GuideMessageRepository(db)
        self.agents = AgentDefinitionRepository(db)
        self.logs = LogService(db)

    def list_sessions(self, workspace_id: str) -> List[GuideSessionEntity]:
        self._require_active(workspace_id)
        return self.sessions.list_by_workspace(workspace_id)

    def create_session(self, workspace_id: str) -> GuideSessionEntity:
        self._require_active(workspace_id)
        now = utc_now_iso()
        entity = GuideSessionEntity(
            id=new_guide_session_id(),
            workspace_id=workspace_id,
            title=DEFAULT_SESSION_TITLE,
            created_at=now,
            updated_at=now,
        )
        saved = self.sessions.create(entity)
        self.db.commit()
        return saved

    def delete_session(self, workspace_id: str, session_id: str) -> None:
        self._require_active(workspace_id)
        if not self.sessions.delete(workspace_id, session_id):
            raise NotFoundError("Guide session not found", code="GUIDE_SESSION_NOT_FOUND")
        self.db.commit()

    def list_messages(
        self,
        workspace_id: str,
        session_id: str,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[List[GuideMessageEntity], int]:
        self._require_active(workspace_id)
        self._require_session(workspace_id, session_id)
        return self.messages.list_by_session(
            workspace_id, session_id, limit=limit, offset=offset
        )

    def stream_turn(
        self,
        workspace_id: str,
        session_id: str,
        text: str,
    ) -> Generator[Dict[str, Any], None, None]:
        """Yield SSE event dicts: {event, data}."""
        collected_steps: List[Dict[str, Any]] = []
        step_n = 0

        def emit_step(phase: str, title: str, detail: str = "") -> Dict[str, Any]:
            nonlocal step_n
            step_n += 1
            step = {
                "id": f"s{step_n}",
                "phase": phase,
                "title": title,
                "detail": detail or "",
            }
            collected_steps.append(step)
            return {"event": "step", "data": step}

        try:
            ws = self._require_active(workspace_id)
            session = self._require_session(workspace_id, session_id)

            cleaned = (text or "").strip()
            if not cleaned:
                raise ValidationAppError("Message must not be empty", code="EMPTY_TEXT")

            now = utc_now_iso()
            prior_count = self.messages.count_by_session(workspace_id, session_id)
            if prior_count == 0 and session.title == DEFAULT_SESSION_TITLE:
                self.sessions.update_title(
                    workspace_id, session_id, _title_from_message(cleaned), now
                )

            user_msg = GuideMessageEntity(
                id=new_guide_message_id(),
                session_id=session_id,
                workspace_id=workspace_id,
                role=ChatRole.USER,
                text=cleaned,
                at=now,
                steps=None,
            )
            self.messages.create(user_msg)
            self.sessions.touch(workspace_id, session_id, now)
            self.db.commit()

            history, _ = self.messages.list_by_session(
                workspace_id, session_id, limit=30, offset=0
            )
            history_for_llm = [m for m in history if m.id != user_msg.id][-12:]

            yield emit_step("support", "فهم پیام کاربر", cleaned[:240])

            bot_user = self.agents.get(DEFAULT_CHATBOT_USER_ID)
            policy_text = (bot_user.policy_text if bot_user else "") or ""
            yield emit_step(
                "support",
                "بررسی policy",
                policy_text[:400] if policy_text else "بدون policy اختصاصی",
            )

            support = self._run_support(
                user_text=cleaned,
                policy_text=policy_text,
                history=history_for_llm,
            )

            if support.get("action") == "clarify":
                clarify_text = (
                    support.get("message")
                    or "لطفاً هدف‌تان را دقیق‌تر بگویید."
                )
                yield emit_step("support", "نیاز به روشن‌سازی", clarify_text)
                yield {"event": "clarify", "data": {"text": clarify_text}}
                assistant = self._persist_assistant(
                    workspace_id, session_id, clarify_text, collected_steps
                )
                yield {
                    "event": "final",
                    "data": {"message": self._message_payload(assistant)},
                }
                yield {"event": "done", "data": {}}
                return

            enhanced = (support.get("enhanced_prompt") or cleaned).strip()
            yield emit_step("support", "تقویت پرامپت", enhanced[:500])

            yield emit_step("brain", "شروع موتور راهنما", enhanced[:200])
            state, brain_steps = self._run_brain(
                query=enhanced,
                workspace_path=ws.path,
                workspace_id=workspace_id,
            )
            for bs in brain_steps:
                yield emit_step("brain", bs["title"], bs.get("detail", ""))

            raw_guide = normalize_guide_markdown(
                state.final_persian_guide or "راهنمایی یافت نشد."
            )
            breadcrumbs = " > ".join(state.extracted_breadcrumbs or [])
            routes_summary = ", ".join(
                (r.path or r.name or "?") for r in (state.identified_routes or [])[:5]
            )
            hits_summary = (
                f"routes={len(state.identified_routes or [])}, "
                f"forms={len(state.discovered_forms or [])}, "
                f"evidence={len(state.tool_evidence or [])}"
            )
            yield emit_step(
                "brain",
                "خروجی خام workflow",
                f"{hits_summary}\nbreadcrumbs: {breadcrumbs or '—'}\nroutes: {routes_summary or '—'}",
            )

            yield emit_step("jarvis", "آماده‌سازی پرامپت نهایی", "ترکیب شواهد + تاریخچه")
            jarvis_answer = self._run_jarvis(
                user_text=cleaned,
                enhanced_prompt=enhanced,
                raw_guide=raw_guide,
                history=history_for_llm,
                breadcrumbs=breadcrumbs,
                hits_summary=hits_summary,
                brain_step_titles=[s["title"] for s in collected_steps if s["phase"] == "brain"],
            )
            yield emit_step("jarvis", "تولید پاسخ نهایی", jarvis_answer[:320])

            assistant = self._persist_assistant(
                workspace_id, session_id, jarvis_answer, collected_steps
            )
            self.logs.append(
                workspace_id,
                level=LogLevel.INFO,
                source=LogSource.CHAT.value,
                message=f"Guide chat session {session_id}",
            )
            self.db.commit()

            yield {
                "event": "final",
                "data": {"message": self._message_payload(assistant)},
            }
            yield {"event": "done", "data": {}}

        except Exception as exc:  # noqa: BLE001
            self.db.rollback()
            yield {"event": "error", "data": {"message": str(exc)}}
            yield {"event": "done", "data": {}}

    def _run_support(
        self,
        *,
        user_text: str,
        policy_text: str,
        history: List[GuideMessageEntity],
    ) -> Dict[str, str]:
        hist_lines = []
        for m in history:
            role = "کاربر" if m.role == ChatRole.USER else "دستیار"
            hist_lines.append(f"{role}: {m.text[:400]}")
        hist_block = "\n".join(hist_lines) if hist_lines else "(خالی)"
        user_prompt = (
            f"Policy:\n{policy_text or '(ندارد)'}\n\n"
            f"تاریخچه اخیر:\n{hist_block}\n\n"
            f"پیام جدید کاربر:\n{user_text}\n"
        )
        raw = chat_completion(system=SUPPORT_SYSTEM, user=user_prompt, temperature=0.1)
        parsed = _extract_json_object(raw or "")
        if not parsed:
            return _fallback_support(user_text)
        action = str(parsed.get("action") or "").strip().lower()
        if action == "clarify":
            msg = str(parsed.get("message") or "").strip()
            if not msg:
                return _fallback_support(user_text)
            return {"action": "clarify", "message": msg}
        enhanced = str(parsed.get("enhanced_prompt") or "").strip()
        if not enhanced:
            return _fallback_support(user_text)
        return {"action": "proceed", "enhanced_prompt": enhanced}

    def _run_brain(
        self,
        *,
        query: str,
        workspace_path: str,
        workspace_id: str,
    ) -> tuple[AgentState, List[Dict[str, str]]]:
        workflow = Code2GuideWorkflow(
            workspace_path=workspace_path,
            workspace_id=workspace_id,
        )
        state = AgentState(
            query=query,
            workspace_path=workspace_path,
            audience="end_user",
        )
        nodes = [
            ("برنامه‌ریزی پرسش", workflow.node_plan_query),
            ("کشف مسیرها", workflow.node_discover_routes),
            ("جستجوی برچسب‌ها", workflow.node_search_labels),
            ("بازرسی فرم/AST", workflow.node_inspect_ast),
            ("جمع‌آوری شواهد", workflow.node_gather_evidence),
            ("سنتز راهنما", workflow.node_synthesize_guide),
        ]
        brain_steps: List[Dict[str, str]] = []
        for title, node_fn in nodes:
            before = len(state.steps_taken or [])
            node_fn(state)
            new_notes = (state.steps_taken or [])[before:]
            detail = "\n".join(new_notes) if new_notes else title
            brain_steps.append({"title": title, "detail": detail})

        from src.agent.abstain import apply_abstain_to_state

        store = getattr(workflow.toolbox, "_graph_store", None)
        apply_abstain_to_state(state, store=store)
        return state, brain_steps

    def _run_jarvis(
        self,
        *,
        user_text: str,
        enhanced_prompt: str,
        raw_guide: str,
        history: List[GuideMessageEntity],
        breadcrumbs: str,
        hits_summary: str,
        brain_step_titles: List[str],
    ) -> str:
        hist_lines = []
        for m in history[-8:]:
            role = "user" if m.role == ChatRole.USER else "assistant"
            hist_lines.append(f"{role}: {m.text[:350]}")
        hist_block = "\n".join(hist_lines) if hist_lines else "(خالی)"
        user_prompt = f"""پیام اصلی کاربر:
{user_text}

پرامپت تقویت‌شده:
{enhanced_prompt}

تاریخچه session:
{hist_block}

خلاصه شواهد مغز:
{hits_summary}
breadcrumbs: {breadcrumbs or '—'}
مراحل مغز: {', '.join(brain_step_titles) or '—'}

راهنمای خام workflow:
{raw_guide}

بر اساس همین ورودی‌ها، پیام نهایی کاربرپسند را بنویس.
"""
        out = chat_completion(system=JARVIS_SYSTEM, user=user_prompt, temperature=0.2)
        if out and out.strip():
            return normalize_guide_markdown(out.strip())
        return raw_guide

    def _persist_assistant(
        self,
        workspace_id: str,
        session_id: str,
        text: str,
        steps: List[Dict[str, Any]],
    ) -> GuideMessageEntity:
        now = utc_now_iso()
        entity = GuideMessageEntity(
            id=new_guide_message_id(),
            session_id=session_id,
            workspace_id=workspace_id,
            role=ChatRole.ASSISTANT,
            text=text,
            at=now,
            steps=list(steps),
        )
        saved = self.messages.create(entity)
        self.sessions.touch(workspace_id, session_id, now)
        self.db.commit()
        return saved

    @staticmethod
    def _message_payload(msg: GuideMessageEntity) -> Dict[str, Any]:
        return {
            "id": msg.id,
            "role": msg.role.value,
            "text": msg.text,
            "at": msg.at,
            "steps": msg.steps or [],
        }

    def _require_active(self, workspace_id: str):
        ws = self.workspaces.get(workspace_id)
        if ws is None or ws.deleted_at is not None:
            raise NotFoundError("Workspace not found", code="WORKSPACE_NOT_FOUND")
        return ws

    def _require_session(self, workspace_id: str, session_id: str) -> GuideSessionEntity:
        session = self.sessions.get(workspace_id, session_id)
        if session is None:
            raise NotFoundError("Guide session not found", code="GUIDE_SESSION_NOT_FOUND")
        return session
