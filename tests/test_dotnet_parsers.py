"""Tests for .NET backend parsers and Phase 2 indexing."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.parsers.stack_detector import StackDetector
from src.parsers.dotnet import (
    DotNetApiParser,
    DotNetEntityParser,
    DotNetMigrationParser,
    DotNetServiceParser,
)
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


class TestDotNetParsers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ws = Path("./sample_workspace").resolve()
        cls.controller = (
            cls.ws / "backend" / "Controllers" / "TendersController.cs"
        ).read_text(encoding="utf-8")
        cls.service = (cls.ws / "backend" / "Services" / "TenderService.cs").read_text(
            encoding="utf-8"
        )
        cls.entity = (cls.ws / "backend" / "Entities" / "Tender.cs").read_text(
            encoding="utf-8"
        )
        cls.migration = (
            cls.ws / "backend" / "Migrations" / "20240101000000_CreateTenders.cs"
        ).read_text(encoding="utf-8")

    def test_stack_detector_finds_dotnet(self):
        det = StackDetector(str(self.ws)).detect()
        self.assertFalse(det.skipped)
        self.assertEqual(det.stack, "dotnet")
        self.assertTrue(any("backend" in r for r in det.backend_roots))

    def test_api_parser_controller_routes(self):
        eps = DotNetApiParser().parse_file(
            self.controller, "backend/Controllers/TendersController.cs"
        )
        methods = {(e.method, e.path) for e in eps}
        self.assertIn(("GET", "/api/Tenders"), methods)
        self.assertIn(("POST", "/api/Tenders"), methods)
        post = next(e for e in eps if e.method == "POST")
        self.assertEqual(post.from_body_type, "TenderCreateDto")
        self.assertTrue(post.roles)

    def test_service_parser(self):
        svcs = DotNetServiceParser().parse_file(
            self.service, "backend/Services/TenderService.cs"
        )
        self.assertTrue(any(s.name == "TenderService" for s in svcs))
        svc = next(s for s in svcs if s.name == "TenderService")
        names = {m.name for m in svc.methods}
        self.assertIn("CreateAsync", names)
        self.assertIn("ListAsync", names)

    def test_entity_parser(self):
        ents = DotNetEntityParser().parse_file(
            self.entity, "backend/Entities/Tender.cs"
        )
        names = {e.name for e in ents}
        self.assertIn("Tender", names)
        tender = next(e for e in ents if e.name == "Tender")
        self.assertEqual(tender.table_name, "Tenders")
        field_names = {f.name for f in tender.fields}
        self.assertIn("Title", field_names)
        self.assertIn("Description", field_names)

    def test_migration_parser(self):
        tables = DotNetMigrationParser().parse_file(
            self.migration, "backend/Migrations/20240101000000_CreateTenders.cs"
        )
        names = {t.name for t in tables}
        self.assertIn("Tenders", names)
        tenders = next(t for t in tables if t.name == "Tenders")
        self.assertGreater(len(tenders.columns), 0)
        self.assertTrue(any(c.name == "Title" for c in tenders.columns))


class TestBackendIndexAndAsk(unittest.TestCase):
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

    def test_index_includes_backend_nodes(self):
        toolbox = self._toolbox()
        info = toolbox.index_workspace()
        self.assertGreater(info.get("api_endpoints", 0), 0)
        self.assertGreater(info.get("services", 0), 0)
        self.assertGreater(info.get("entities", 0), 0)
        self.assertGreater(info.get("tables", 0), 0)
        self.assertFalse(info.get("backend_skipped"))

        status = toolbox.index_status()
        self.assertGreater(status["counts"]["entities"], 0)
        self.assertGreater(status["counts"]["api_endpoints"], 0)

        ent = toolbox.get_entity("Tender")
        self.assertIsNotNone(ent)
        self.assertEqual(ent["title"], "Tender")
        fields = (ent.get("payload") or {}).get("fields") or []
        self.assertTrue(any((f.get("name") if isinstance(f, dict) else f) == "Title" for f in fields))

    def test_ask_backend_entity_fields(self):
        toolbox = self._toolbox()
        agent = Code2GuideAgent(workspace_path=self.ws_path, toolbox=toolbox)
        toolbox.index_workspace()

        with patch.object(agent.workflow, "_call_real_llm", return_value=None), patch.dict(
            os.environ, {"OPENROUTER_API_KEY": "", "OPENAI_API_KEY": ""}, clear=False
        ), patch("src.agent.workflow.settings.openrouter_api_key", None), patch(
            "src.agent.workflow.settings.openai_api_key", None
        ):
            state = agent.ask("entity مناقصه Tender چه فیلدهایی دارد؟", workspace_path=self.ws_path)

        self.assertEqual(state.status, "completed")
        self.assertTrue(state.is_backend_query)
        self.assertGreater(len(state.backend_hits), 0)
        guide = state.final_persian_guide or ""
        self.assertIn("Tender", guide)
        self.assertIn("Title", guide)
        self.assertTrue(
            any("backend" in (h.get("file_path") or "").lower() for h in state.backend_hits)
            or "Entities" in guide
            or "entity" in guide.lower()
        )


if __name__ == "__main__":
    unittest.main()
