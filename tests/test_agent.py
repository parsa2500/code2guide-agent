"""Tests for Search Engine, ReAct Toolbox, and Code2Guide Agent."""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from src.search.hybrid_indexer import HybridIndexer, IndexedItem, collection_name_for_workspace
from src.agent.tools import Code2GuideToolbox
from src.agent.workflow import Code2GuideAgent


def _offline_indexer(workspace_path: str) -> HybridIndexer:
    return HybridIndexer(
        collection_name=collection_name_for_workspace(workspace_path),
        url=None,
        location=":memory:",
        embedding_provider="none",
    )


def _offline_agent(ws_path: str) -> Code2GuideAgent:
    toolbox = Code2GuideToolbox(
        workspace_path=ws_path,
        hybrid_indexer=_offline_indexer(ws_path),
    )
    return Code2GuideAgent(workspace_path=ws_path, toolbox=toolbox)


class TestAgent(unittest.TestCase):

    def test_hybrid_indexer(self):
        # Force in-memory fallback so the unit test does not depend on Docker/Google.
        indexer = HybridIndexer(
            url=None,
            location=":memory:",
            embedding_provider="none",
        )
        items = [
            IndexedItem(
                id="route-1",
                title="ثبت مناقصه جدید",
                content="صفحه ثبت اطلاعات و مستندات مناقصه",
                file_path="src/pages/Tenders/Create.tsx",
                item_type="route"
            ),
            IndexedItem(
                id="page-2",
                title="مدیریت کاربران",
                content="جدول فهرست کاربران و دسترسی‌ها",
                file_path="src/pages/Users.tsx",
                item_type="page"
            )
        ]
        indexer.index_items(items)
        hits = indexer.search("ثبت مناقصه", limit=2)
        self.assertGreater(len(hits), 0)
        self.assertEqual(hits[0].id, "route-1")

    def test_collection_name_scoped_to_workspace(self):
        a = collection_name_for_workspace("/tmp/ws-a")
        b = collection_name_for_workspace("/tmp/ws-b")
        self.assertNotEqual(a, b)
        self.assertTrue(a.startswith("code2guide_"))

    def test_toolbox_index_and_hybrid_search(self):
        ws_path = str(Path("./sample_workspace").resolve())
        toolbox = Code2GuideToolbox(
            workspace_path=ws_path,
            hybrid_indexer=_offline_indexer(ws_path),
        )
        info = toolbox.index_workspace()
        self.assertGreater(info["indexed_count"], 0)
        self.assertFalse(info["use_vector"])

        hits = toolbox.hybrid_search("ثبت مناقصه جدید", limit=5)["hits"]
        self.assertGreater(len(hits), 0)
        paths = [h.get("metadata", {}).get("path") for h in hits]
        self.assertIn("/tenders/create", paths)

        routes = toolbox.routes_from_hybrid_hits(hits)
        self.assertTrue(any(r.path == "/tenders/create" for r in routes))

    def test_ensure_indexed_feeds_discover(self):
        ws_path = str(Path("./sample_workspace").resolve())
        agent = _offline_agent(ws_path)
        with patch.object(agent.workflow, "_call_real_llm", return_value=None), patch.dict(
            os.environ, {"OPENROUTER_API_KEY": "", "OPENAI_API_KEY": ""}, clear=False
        ), patch("src.agent.workflow.settings.openrouter_api_key", None), patch(
            "src.agent.workflow.settings.openai_api_key", None
        ):
            state = agent.ask("چگونه مناقصه ثبت کنم؟", workspace_path=ws_path)
        self.assertEqual(state.status, "completed")
        self.assertTrue(any("Hybrid hits=" in s for s in state.steps_taken))
        self.assertGreater(len(state.identified_routes), 0)

    def test_agent_end_to_end_on_sample_workspace(self):
        ws_path = str(Path("./sample_workspace").resolve())
        agent = _offline_agent(ws_path)
        with patch.object(agent.workflow, "_call_real_llm", return_value=None), patch.dict(
            os.environ, {"OPENROUTER_API_KEY": "", "OPENAI_API_KEY": ""}, clear=False
        ), patch("src.agent.workflow.settings.openrouter_api_key", None), patch(
            "src.agent.workflow.settings.openai_api_key", None
        ):
            state = agent.ask("چگونه یک مناقصه جدید ثبت کنم؟", workspace_path=ws_path)

        self.assertEqual(state.status, "completed")
        self.assertGreater(len(state.extracted_breadcrumbs), 0)
        self.assertIn("مدیریت مناقصات", state.extracted_breadcrumbs)
        self.assertIn("ثبت مناقصه جدید", state.extracted_breadcrumbs)

        guide = state.final_persian_guide
        self.assertIsNotNone(guide)
        self.assertIn("### ۱. مسیر دسترسی (Navigation)", guide)
        self.assertIn("### ۲. اطلاعات لازم و فیلدهای فرم (Form Fields)", guide)
        self.assertIn("### ۳. دکمه اقدام نهایی (Action)", guide)
        self.assertIn("/tenders/create", guide)
        self.assertIn("عنوان مناقصه", guide)
        self.assertIn("ثبت نهایی و ارسال مناقصه", guide)


if __name__ == "__main__":
    unittest.main()
