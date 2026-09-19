"""Tests for Search Engine, ReAct Toolbox, and Code2Guide Agent."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.search.hybrid_indexer import HybridIndexer, IndexedItem, collection_name_for_workspace
from src.agent.tools import Code2GuideToolbox
from src.agent.workflow import Code2GuideAgent
from src.knowledge.manager import get_index_manager, reset_index_managers
from src.knowledge.schema import NodeType


def _offline_indexer(workspace_path: str) -> HybridIndexer:
    return HybridIndexer(
        collection_name=collection_name_for_workspace(workspace_path),
        url=None,
        location=":memory:",
        embedding_provider="none",
    )


def _offline_toolbox(ws_path: str, index_root: str) -> Code2GuideToolbox:
    reset_index_managers()
    with patch("src.core.config.settings.index_storage_path", index_root), patch(
        "src.knowledge.manager.settings.index_storage_path", index_root
    ):
        toolbox = Code2GuideToolbox(
            workspace_path=ws_path,
            hybrid_indexer=_offline_indexer(ws_path),
        )
    return toolbox


def _offline_agent(ws_path: str, index_root: str) -> Code2GuideAgent:
    toolbox = _offline_toolbox(ws_path, index_root)
    return Code2GuideAgent(workspace_path=ws_path, toolbox=toolbox)


class TestAgent(unittest.TestCase):

    def setUp(self):
        reset_index_managers()
        self._tmpdir = tempfile.TemporaryDirectory()
        self.index_root = self._tmpdir.name

    def tearDown(self):
        reset_index_managers()
        self._tmpdir.cleanup()

    def test_hybrid_indexer(self):
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
        toolbox = _offline_toolbox(ws_path, self.index_root)
        info = toolbox.index_workspace()
        self.assertGreater(info["indexed_count"], 0)
        self.assertFalse(info["use_vector"])
        self.assertGreater(info.get("forms", 0), 0)
        self.assertGreater(info.get("form_fields", 0), 0)

        hits = toolbox.hybrid_search("ثبت مناقصه جدید", limit=5)["hits"]
        self.assertGreater(len(hits), 0)
        # Deep index includes route and form/field items
        types = {h.get("item_type") for h in hits}
        self.assertTrue(types & {"route", "form", "field", "button", "component"})

        routes = toolbox.routes_from_hybrid_hits(hits)
        self.assertTrue(
            any(r.path == "/tenders/create" for r in routes)
            or any(h.get("metadata", {}).get("path") == "/tenders/create" for h in hits)
            or any("Create.tsx" in (h.get("file_path") or "") for h in hits)
        )

    def test_deep_index_persists_graph_and_status(self):
        ws_path = str(Path("./sample_workspace").resolve())
        toolbox = _offline_toolbox(ws_path, self.index_root)
        info = toolbox.index_workspace()
        self.assertGreater(info["files_inspected"], 0)

        status = toolbox.index_status()
        self.assertTrue(status["exists"])
        self.assertGreater(status["counts"]["forms"], 0)
        self.assertGreater(status["counts"]["form_fields"], 0)
        self.assertGreater(status["counts"]["routes"], 0)

        forms = toolbox.forms_from_index()
        self.assertGreater(len(forms), 0)
        labels = [f.label or f.name for form in forms for f in form.fields]
        self.assertTrue(any("عنوان" in (l or "") for l in labels))

    def test_ask_loads_forms_from_index(self):
        ws_path = str(Path("./sample_workspace").resolve())
        agent = _offline_agent(ws_path, self.index_root)
        # Pre-index once
        agent.workflow.toolbox.index_workspace()

        with patch.object(agent.workflow, "_call_real_llm", return_value=None), patch.dict(
            os.environ, {"OPENROUTER_API_KEY": "", "OPENAI_API_KEY": ""}, clear=False
        ), patch("src.agent.workflow.settings.openrouter_api_key", None), patch(
            "src.agent.workflow.settings.openai_api_key", None
        ):
            state = agent.ask("چگونه مناقصه ثبت کنم؟", workspace_path=ws_path)

        self.assertEqual(state.status, "completed")
        self.assertTrue(any("from_store=" in s or "via index" in s for s in state.steps_taken))
        self.assertTrue(
            any("Loaded forms via index" in s for s in state.steps_taken),
            msg=state.steps_taken,
        )
        self.assertGreater(len(state.discovered_forms), 0)

    def test_ensure_indexed_feeds_discover(self):
        ws_path = str(Path("./sample_workspace").resolve())
        agent = _offline_agent(ws_path, self.index_root)
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
        agent = _offline_agent(ws_path, self.index_root)
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
