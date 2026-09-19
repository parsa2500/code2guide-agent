"""Golden-set evaluation for Phase 4 Q&A (offline, no LLM)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agent.planner import QueryPlanner
from src.agent.tools import Code2GuideToolbox
from src.agent.workflow import Code2GuideAgent
from src.knowledge.manager import get_index_manager, reset_index_managers
from src.search.hybrid_indexer import HybridIndexer, collection_name_for_workspace

GOLDEN_PATH = Path(__file__).parent / "golden" / "sample_workspace_qa.json"


def _offline_indexer(workspace_path: str) -> HybridIndexer:
    return HybridIndexer(
        collection_name=collection_name_for_workspace(workspace_path),
        url=None,
        location=":memory:",
        embedding_provider="none",
    )


class TestGoldenQA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reset_index_managers()
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.index_root = cls._tmpdir.name
        cls.ws_path = str(Path("./sample_workspace").resolve())
        with patch("src.core.config.settings.index_storage_path", cls.index_root), patch(
            "src.knowledge.manager.settings.index_storage_path", cls.index_root
        ):
            toolbox = Code2GuideToolbox(
                workspace_path=cls.ws_path,
                hybrid_indexer=_offline_indexer(cls.ws_path),
            )
            info = toolbox.index_workspace()
            cls.toolbox = toolbox
            cls.index_info = info
        cls.cases = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
        cls.planner = QueryPlanner()

    @classmethod
    def tearDownClass(cls):
        reset_index_managers()
        cls._tmpdir.cleanup()

    def _ask(self, query: str):
        agent = Code2GuideAgent(workspace_path=self.ws_path, toolbox=self.toolbox)
        with patch.object(agent.workflow, "_call_real_llm", return_value=None), patch.dict(
            os.environ, {"OPENROUTER_API_KEY": "", "OPENAI_API_KEY": ""}, clear=False
        ), patch("src.agent.workflow.settings.openrouter_api_key", None), patch(
            "src.agent.workflow.settings.openai_api_key", None
        ):
            return agent.ask(query, workspace_path=self.ws_path)

    def test_index_ready(self):
        self.assertGreater(self.index_info.get("indexed_count", 0), 0)
        self.assertGreater(self.index_info.get("api_endpoints", 0), 0)

    def test_golden_cases(self):
        failures = []
        for case in self.cases:
            cid = case["id"]
            query = case["query"]
            expected_intent = case.get("intent")
            plan = self.planner.plan(query)
            if expected_intent and plan.intent != expected_intent:
                # Allow mixed≈flow overlap for flow-ish questions
                if not (
                    expected_intent == "flow"
                    and plan.intent in ("flow", "mixed")
                    or expected_intent == "mixed"
                    and plan.intent in ("flow", "mixed")
                ):
                    failures.append(f"{cid}: intent want={expected_intent} got={plan.intent}")
                    continue

            state = self._ask(query)
            guide = state.final_persian_guide or ""
            for needle in case.get("must_contain") or []:
                if needle not in guide:
                    failures.append(f"{cid}: missing must_contain {needle!r}")
            for cite in case.get("must_cite_substr") or []:
                if cite not in guide:
                    failures.append(f"{cid}: missing citation {cite!r}")
            for bad in case.get("must_not_contain") or []:
                if bad in guide:
                    failures.append(f"{cid}: unexpected content {bad!r}")

        self.assertFalse(failures, msg="\n".join(failures))


class TestIncrementalSkip(unittest.TestCase):
    def setUp(self):
        reset_index_managers()
        self._tmpdir = tempfile.TemporaryDirectory()
        self.index_root = self._tmpdir.name
        self.ws_path = str(Path("./sample_workspace").resolve())

    def tearDown(self):
        reset_index_managers()
        self._tmpdir.cleanup()

    def test_second_index_skips_unchanged(self):
        with patch("src.core.config.settings.index_storage_path", self.index_root), patch(
            "src.knowledge.manager.settings.index_storage_path", self.index_root
        ):
            toolbox = Code2GuideToolbox(
                workspace_path=self.ws_path,
                hybrid_indexer=_offline_indexer(self.ws_path),
            )
            mgr = get_index_manager(self.ws_path, hybrid_indexer=toolbox.hybrid_indexer)
            first = mgr.index_workspace(toolbox, rebuild=True)
            self.assertFalse(first.skipped_unchanged)
            self.assertGreater(first.indexed_count, 0)

            second = mgr.index_workspace(toolbox, rebuild=False)
            self.assertTrue(
                second.skipped_unchanged,
                msg=f"expected skip, got stats={second.stats}",
            )


if __name__ == "__main__":
    unittest.main()
