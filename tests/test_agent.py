"""Tests for Search Engine, ReAct Toolbox, and Code2Guide Agent."""

import unittest
from pathlib import Path

from src.search.hybrid_indexer import HybridIndexer, IndexedItem
from src.agent.tools import Code2GuideToolbox
from src.agent.workflow import Code2GuideAgent


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

    def test_agent_end_to_end_on_sample_workspace(self):
        ws_path = "./sample_workspace"
        agent = Code2GuideAgent(workspace_path=ws_path)
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
