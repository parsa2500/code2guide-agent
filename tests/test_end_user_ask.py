"""Tests for end-user (/ask-enduser) audience mode."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.search.hybrid_indexer import HybridIndexer, collection_name_for_workspace
from src.agent.tools import Code2GuideToolbox
from src.agent.workflow import Code2GuideAgent
from src.knowledge.manager import reset_index_managers


def _offline_indexer(workspace_path: str) -> HybridIndexer:
    return HybridIndexer(
        collection_name=collection_name_for_workspace(workspace_path),
        url=None,
        location=":memory:",
        embedding_provider="none",
    )


def _offline_agent(ws_path: str, index_root: str) -> Code2GuideAgent:
    reset_index_managers()
    with patch("src.core.config.settings.index_storage_path", index_root), patch(
        "src.knowledge.manager.settings.index_storage_path", index_root
    ):
        toolbox = Code2GuideToolbox(
            workspace_path=ws_path,
            hybrid_indexer=_offline_indexer(ws_path),
        )
    return Code2GuideAgent(workspace_path=ws_path, toolbox=toolbox)


class TestEndUserAsk(unittest.TestCase):
    def setUp(self):
        reset_index_managers()
        self._tmpdir = tempfile.TemporaryDirectory()
        self.index_root = self._tmpdir.name
        self.ws_path = str(Path("./sample_workspace").resolve())

    def tearDown(self):
        reset_index_managers()
        self._tmpdir.cleanup()

    def _ask_end_user(self, query: str):
        agent = _offline_agent(self.ws_path, self.index_root)
        agent.workflow.toolbox.index_workspace()
        with patch.object(agent.workflow, "_call_real_llm", return_value=None), patch.dict(
            os.environ, {"OPENROUTER_API_KEY": "", "OPENAI_API_KEY": ""}, clear=False
        ), patch("src.agent.workflow.settings.openrouter_api_key", None), patch(
            "src.agent.workflow.settings.openai_api_key", None
        ):
            return agent.ask(query, workspace_path=self.ws_path, audience="end_user")

    def test_end_user_guide_is_simple(self):
        state = self._ask_end_user("چگونه مناقصه ثبت کنم؟")
        self.assertEqual(state.status, "completed")
        self.assertEqual(state.audience, "end_user")
        guide = state.final_persian_guide or ""
        self.assertIn("چطور این کار را انجام دهید", guide)
        self.assertIn("از کجا شروع کنید", guide)
        self.assertIn("چه چیزهایی را وارد کنید", guide)
        self.assertIn("در پایان چه کنید", guide)
        self.assertIn("عنوان مناقصه", guide)

        # Must not leak technical content
        lower = guide.lower()
        self.assertNotIn("controllers/", lower)
        self.assertNotIn("entity", lower)
        self.assertNotIn("استناد", guide)
        self.assertNotIn("جریان کامل سیستم", guide)
        self.assertNotIn("post /api", lower)
        self.assertNotIn("### ۱. مسیر دسترسی", guide)
        # Technical URL should not be the main content (template has no page_url)
        self.assertNotIn("/tenders/create", guide)
        self.assertNotIn("Create.tsx", guide)

    def test_end_user_forces_ux_intent(self):
        state = self._ask_end_user("چگونه مناقصه ثبت کنم؟")
        plan = state.query_plan or {}
        self.assertEqual(plan.get("intent"), "ux")
        self.assertFalse(state.is_backend_query)
        self.assertFalse(state.is_flow_query)
        self.assertTrue(any("audience=end_user" in s for s in state.steps_taken))

    def test_end_user_no_evidence_simple_message(self):
        empty_ws = tempfile.mkdtemp()
        try:
            agent = _offline_agent(empty_ws, self.index_root)
            with patch.object(agent.workflow, "_call_real_llm", return_value=None), patch.dict(
                os.environ, {"OPENROUTER_API_KEY": "", "OPENAI_API_KEY": ""}, clear=False
            ), patch("src.agent.workflow.settings.openrouter_api_key", None), patch(
                "src.agent.workflow.settings.openai_api_key", None
            ):
                state = agent.ask(
                    "چگونه سفینه فضایی رزرو کنم؟",
                    workspace_path=empty_ws,
                    audience="end_user",
                )
            guide = state.final_persian_guide or ""
            self.assertIn("در راهنمای سامانه چیزی پیدا نشد", guide)
            self.assertNotIn("گراف دانش", guide)
            self.assertNotIn("شاهد استنادپذیری", guide)
        finally:
            import shutil

            shutil.rmtree(empty_ws, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
