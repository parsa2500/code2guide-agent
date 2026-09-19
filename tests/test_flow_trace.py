"""Tests for Phase 3 front↔back flow tracing."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.parsers.frontend_api_tracer import FrontendApiTracer
from src.search.hybrid_indexer import HybridIndexer, collection_name_for_workspace
from src.agent.tools import Code2GuideToolbox
from src.agent.workflow import Code2GuideAgent
from src.knowledge.manager import reset_index_managers
from src.knowledge.schema import EdgeType, NodeType
from src.knowledge.flow_tracer import FlowTracer


def _offline_indexer(workspace_path: str) -> HybridIndexer:
    return HybridIndexer(
        collection_name=collection_name_for_workspace(workspace_path),
        url=None,
        location=":memory:",
        embedding_provider="none",
    )


class TestFrontendApiTracer(unittest.TestCase):
    def test_parse_fetch_post(self):
        code = """
        await fetch("/api/Tenders", {
          method: "POST",
          body: JSON.stringify({ title: "x" }),
        });
        """
        calls = FrontendApiTracer().parse_file(code, "src/pages/Tenders/Create.tsx")
        self.assertTrue(any(c.method == "POST" and "/api/Tenders" in c.url_normalized for c in calls))

    def test_normalize_template(self):
        n = FrontendApiTracer.normalize_url("`/api/tenders/${id}`".strip("`"))
        # without backticks in input
        n2 = FrontendApiTracer.normalize_url("/api/tenders/${id}")
        self.assertEqual(n2, "/api/tenders/{id}")


class TestFlowTrace(unittest.TestCase):
    def setUp(self):
        reset_index_managers()
        self._tmpdir = tempfile.TemporaryDirectory()
        self.index_root = self._tmpdir.name
        self.ws_path = str(Path("./sample_workspace").resolve())

    def tearDown(self):
        reset_index_managers()
        self._tmpdir.cleanup()

    def _toolbox(self) -> Code2GuideToolbox:
        reset_index_managers()
        with patch("src.core.config.settings.index_storage_path", self.index_root), patch(
            "src.knowledge.manager.settings.index_storage_path", self.index_root
        ):
            return Code2GuideToolbox(
                workspace_path=self.ws_path,
                hybrid_indexer=_offline_indexer(self.ws_path),
            )

    def test_index_links_calls_api(self):
        toolbox = self._toolbox()
        info = toolbox.index_workspace()
        self.assertGreater(info.get("api_calls", 0), 0, msg=info)
        self.assertGreater(info.get("api_endpoints", 0), 0)

        # Find CALLS_API edges via neighbors from Create component/form
        store = toolbox.graph_store
        linked = False
        for n in store.list_nodes(NodeType.COMPONENT) + store.list_nodes(NodeType.FORM) + store.list_nodes(
            NodeType.ROUTE
        ):
            if "Create" not in (n.file_path or "") and "/tenders/create" not in (
                (n.payload or {}).get("path") or ""
            ):
                continue
            for api in store.neighbors(n.id, EdgeType.CALLS_API):
                path = (api.payload or {}).get("path") or ""
                if "Tender" in path or "tender" in path.lower():
                    linked = True
                    break
            if linked:
                break
        self.assertTrue(linked, "Expected CALLS_API from Create page/route to Tenders API")

    def test_trace_reaches_table(self):
        toolbox = self._toolbox()
        toolbox.index_workspace()
        result = toolbox.trace_flow("/tenders/create")
        self.assertTrue(result.get("chains"), msg=result)
        types = set()
        for chain in result["chains"]:
            for step in chain.get("steps") or []:
                types.add(step.get("node_type"))
        self.assertIn(NodeType.API_ENDPOINT.value, types)
        self.assertIn(NodeType.SERVICE.value, types)
        self.assertIn(NodeType.ENTITY.value, types)
        self.assertIn(NodeType.TABLE.value, types)

    def test_field_mappings_present(self):
        toolbox = self._toolbox()
        info = toolbox.index_workspace()
        self.assertGreater(info.get("field_mappings", 0), 0, msg=info)

    def test_ask_flow_question(self):
        toolbox = self._toolbox()
        agent = Code2GuideAgent(workspace_path=self.ws_path, toolbox=toolbox)
        toolbox.index_workspace()

        with patch.object(agent.workflow, "_call_real_llm", return_value=None), patch.dict(
            os.environ, {"OPENROUTER_API_KEY": "", "OPENAI_API_KEY": ""}, clear=False
        ), patch("src.agent.workflow.settings.openrouter_api_key", None), patch(
            "src.agent.workflow.settings.openai_api_key", None
        ):
            state = agent.ask(
                "جریان ثبت مناقصه از UI تا دیتابیس چیست؟",
                workspace_path=self.ws_path,
            )

        self.assertEqual(state.status, "completed")
        self.assertTrue(state.is_flow_query)
        guide = state.final_persian_guide or ""
        self.assertIn("جریان", guide.lower() + guide)
        self.assertTrue(
            "Tender" in guide or "api" in guide.lower() or "Service" in guide,
            msg=guide[:500],
        )


if __name__ == "__main__":
    unittest.main()
