"""Workspace agent binding + agent chat (brain-as-tools)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from src.app.entities.workspace_agent import WorkspaceAgentEntity
from src.app.enums import AgentKind, LogLevel, LogSource
from src.app.exceptions import GuideFailedError, NotFoundError, ValidationAppError
from src.app.repositories.agent_definition_repo import AgentDefinitionRepository
from src.app.repositories.workspace_agent_repo import (
    WorkspaceAgentRepository,
    merge_effective_settings,
)
from src.app.repositories.workspace_repo import WorkspaceRepository
from src.app.services.agent_seed import bind_default_agents, ensure_seed_agents
from src.app.services import brain_tools
from src.app.services.log_service import LogService
from src.core.markdown_guide import normalize_guide_markdown


class WorkspaceAgentService:
    def __init__(self, db: Session):
        self.db = db
        self.workspaces = WorkspaceRepository(db)
        self.agents = AgentDefinitionRepository(db)
        self.bindings = WorkspaceAgentRepository(db)
        self.logs = LogService(db)

    def list_bound(self, workspace_id: str) -> List[WorkspaceAgentEntity]:
        self._require_active(workspace_id)
        ensure_seed_agents(self.db)
        bind_default_agents(self.db, workspace_id)
        self.db.commit()
        return self.bindings.list_by_workspace(workspace_id)

    def bind(self, workspace_id: str, agent_id: str) -> WorkspaceAgentEntity:
        self._require_active(workspace_id)
        ensure_seed_agents(self.db)
        definition = self.agents.get(agent_id)
        if definition is None:
            raise NotFoundError("Agent not found", code="AGENT_NOT_FOUND")
        if not definition.published:
            raise ValidationAppError(
                "Cannot bind unpublished agent",
                code="AGENT_NOT_PUBLISHED",
            )
        existing = self.bindings.get(workspace_id, agent_id)
        if existing is not None:
            return existing
        saved = self.bindings.upsert(workspace_id, agent_id, enabled=True, overrides={})
        self.logs.append(
            workspace_id,
            level=LogLevel.INFO,
            source=LogSource.SETTINGS.value,
            message=f"Agent {agent_id} bound",
        )
        self.db.commit()
        return saved

    def update_binding(
        self,
        workspace_id: str,
        agent_id: str,
        *,
        enabled: Optional[bool] = None,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> WorkspaceAgentEntity:
        self._require_active(workspace_id)
        binding = self.bindings.get(workspace_id, agent_id)
        if binding is None:
            raise NotFoundError("Workspace agent binding not found", code="BINDING_NOT_FOUND")
        definition = binding.definition or self.agents.get(agent_id)
        if definition is None:
            raise NotFoundError("Agent not found", code="AGENT_NOT_FOUND")

        if overrides is not None:
            schema = definition.settings_schema or {}
            bad = []
            for key in overrides:
                meta = schema.get(key)
                if not isinstance(meta, dict) or not meta.get("workspace_overridable"):
                    bad.append(key)
            if bad:
                raise ValidationAppError(
                    f"Override keys not workspace_overridable: {', '.join(bad)}",
                    code="OVERRIDE_NOT_ALLOWED",
                    detail={"keys": bad},
                )

        saved = self.bindings.update(
            workspace_id,
            agent_id,
            enabled=enabled,
            overrides=overrides,
        )
        assert saved is not None
        self.db.commit()
        return saved

    def unbind(self, workspace_id: str, agent_id: str) -> None:
        self._require_active(workspace_id)
        if not self.bindings.delete(workspace_id, agent_id):
            raise NotFoundError("Workspace agent binding not found", code="BINDING_NOT_FOUND")
        self.db.commit()

    def chat(
        self,
        workspace_id: str,
        agent_id: str,
        message: str,
    ) -> Dict[str, Any]:
        ws = self._require_active(workspace_id)
        cleaned = (message or "").strip()
        if not cleaned:
            raise ValidationAppError("Message must not be empty", code="EMPTY_TEXT")

        binding = self.bindings.get(workspace_id, agent_id)
        if binding is None:
            raise NotFoundError("Workspace agent binding not found", code="BINDING_NOT_FOUND")
        if not binding.enabled:
            raise ValidationAppError("Agent binding is disabled", code="AGENT_DISABLED")

        definition = binding.definition or self.agents.get(agent_id)
        if definition is None:
            raise NotFoundError("Agent not found", code="AGENT_NOT_FOUND")
        if not definition.published:
            raise ValidationAppError("Agent is not published", code="AGENT_NOT_PUBLISHED")

        effective = merge_effective_settings(definition.settings_schema, binding.overrides)
        # Apply effective policy/reject/clarify from overrides when schema allows
        policy_text = str(effective.get("policy_text", definition.policy_text) or definition.policy_text)
        reject_text = str(effective.get("reject_text", definition.reject_text) or definition.reject_text)
        clarify_first = definition.clarify_first
        if "clarify_first" in effective:
            clarify_first = bool(effective["clarify_first"])

        # clarify_first: first turn with no history → ask one short clarifying question
        if clarify_first and binding.message_count == 0:
            clarify = (
                "قبل از ادامه، یک سوال کوتاه: دقیقاً می‌خواهید به چه نتیجه‌ای برسید؟ "
                "(هدف، صفحه/فرم، یا نقش کاربری را بگویید.)"
            )
            self.bindings.increment_message_count(workspace_id, agent_id)
            self.logs.append(
                workspace_id,
                level=LogLevel.INFO,
                source=LogSource.CHAT.value,
                message=f"Agent {agent_id} clarify_first",
            )
            self.db.commit()
            return {
                "agent_id": agent_id,
                "clarify": True,
                "answer": clarify,
                "hits": [],
                "effective_settings": effective,
            }

        # Brain tools path
        try:
            k = int(effective.get("max_hits", 5) or 5)
            k = max(1, min(k, 20))
            hits = brain_tools.search(self.db, workspace_id, cleaned, k=k)
        except NotFoundError:
            raise
        except Exception as exc:  # noqa: BLE001
            hits = []
            # soft-fail search; may still try agent
            _ = exc

        if not hits and reject_text:
            self.bindings.increment_message_count(workspace_id, agent_id)
            self.db.commit()
            return {
                "agent_id": agent_id,
                "clarify": False,
                "answer": reject_text,
                "hits": [],
                "effective_settings": effective,
                "rejected": True,
            }

        answer = self._synthesize(
            query=cleaned,
            workspace_path=ws.path,
            workspace_id=workspace_id,
            kind=definition.kind,
            policy_text=policy_text,
            hits=hits,
        )
        self.bindings.increment_message_count(workspace_id, agent_id)
        self.logs.append(
            workspace_id,
            level=LogLevel.INFO,
            source=LogSource.CHAT.value,
            message=f"Agent {agent_id} chat",
        )
        self.db.commit()
        return {
            "agent_id": agent_id,
            "clarify": False,
            "answer": answer,
            "hits": hits,
            "effective_settings": effective,
            "rejected": False,
        }

    def _synthesize(
        self,
        *,
        query: str,
        workspace_path: str,
        workspace_id: str,
        kind: AgentKind,
        policy_text: str,
        hits: List[Dict[str, Any]],
    ) -> str:
        # Prefer Code2GuideAgent.ask when available; wrap with policy.
        try:
            from src.agent.workflow import Code2GuideAgent

            agent = Code2GuideAgent(workspace_path=workspace_path, workspace_id=workspace_id)
            ask_query = query
            if policy_text:
                ask_query = f"[Policy]\n{policy_text}\n\n[User]\n{query}"
            audience = "end_user" if kind == AgentKind.END_USER else None
            if audience:
                state = agent.ask(query=ask_query, workspace_path=workspace_path, audience=audience)
            else:
                state = agent.ask(query=ask_query, workspace_path=workspace_path)
            guide = normalize_guide_markdown(
                state.final_persian_guide or "راهنمایی یافت نشد."
            )
            return guide
        except GuideFailedError:
            raise
        except Exception as exc:  # noqa: BLE001
            # Fallback: structured stub from hits + policy
            if not hits:
                raise GuideFailedError(f"Guide generation failed: {exc}", detail=str(exc)) from exc
            lines = []
            if policy_text:
                lines.append(f"**Policy:** {policy_text}")
            lines.append("## Brain hits")
            for h in hits[:5]:
                title = h.get("title") or h.get("id") or "hit"
                snippet = (h.get("content") or "")[:240]
                lines.append(f"- **{title}** ({h.get('score', 0):.3f}): {snippet}")
            lines.append("")
            lines.append(f"_Query:_ {query}")
            return "\n".join(lines)

    def _require_active(self, workspace_id: str):
        ws = self.workspaces.get(workspace_id)
        if ws is None or ws.deleted_at is not None:
            raise NotFoundError("Workspace not found", code="WORKSPACE_NOT_FOUND")
        return ws
