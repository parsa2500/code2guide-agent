"""Tests for ASP.NET MVC Framework + AngularJS ui-router layer."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.parsers.stack_detector import StackDetector
from src.parsers.dotnet import MvcApiParser, DotNetEntityParser
from src.parsers.route_extractor import RouteExtractor
from src.parsers.razor_ng_visitor import RazorNgFormVisitor
from src.parsers.frontend_api_tracer import FrontendApiTracer
from src.search.hybrid_indexer import HybridIndexer, collection_name_for_workspace
from src.agent.tools import Code2GuideToolbox
from src.knowledge.manager import reset_index_managers


def _offline_indexer(workspace_path: str) -> HybridIndexer:
    return HybridIndexer(
        collection_name=collection_name_for_workspace(workspace_path),
        url=None,
        location=":memory:",
        embedding_provider="none",
    )


class TestMvcParsers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ws = Path("./sample_workspace/mvc_portal").resolve()
        cls.controller = (cls.ws / "Controllers" / "ContractController.cs").read_text(
            encoding="utf-8"
        )
        cls.odata_cfg = (
            cls.ws / "Controllers" / "odata" / "Configuration.cs"
        ).read_text(encoding="utf-8")
        cls.entity = (
            cls.ws / "Contracts.Models" / "BussinessEntities" / "Contract.cs"
        ).read_text(encoding="utf-8")
        cls.view = (cls.ws / "Views" / "Contract" / "Index.cshtml").read_text(
            encoding="utf-8"
        )

    def test_stack_detector_mvc_framework(self):
        det = StackDetector(str(self.ws)).detect()
        self.assertFalse(det.skipped)
        self.assertEqual(det.stack, "dotnet")
        self.assertTrue(det.is_mvc_framework)
        self.assertTrue(
            any("Models" in r or r == "." for r in det.backend_roots)
            or any("." == r for r in det.backend_roots)
        )

    def test_mvc_api_parser_convention_actions(self):
        eps = MvcApiParser().parse_file(
            self.controller, "Controllers/ContractController.cs"
        )
        methods = {(e.method, e.path) for e in eps}
        self.assertIn(("GET", "/Contract/Index"), methods)
        self.assertIn(("GET", "/Contract/Sign"), methods)
        self.assertIn(("POST", "/Contract/GetContractSignContext"), methods)

    def test_mvc_odata_entity_sets(self):
        eps = MvcApiParser().parse_file(
            self.odata_cfg, "Controllers/odata/Configuration.cs"
        )
        paths = {(e.method, e.path) for e in eps}
        self.assertIn(("GET", "/odata/contracts"), paths)
        self.assertIn(("POST", "/odata/contracts"), paths)

    def test_entity_bussinessentities_path(self):
        ents = DotNetEntityParser().parse_file(
            self.entity,
            "Contracts.Models/BussinessEntities/Contract.cs",
        )
        self.assertTrue(any(e.name == "Contract" for e in ents))
        contract = next(e for e in ents if e.name == "Contract")
        self.assertEqual(contract.table_name, "Contracts")
        self.assertIn("Title", {f.name for f in contract.fields})

    def test_angular_ui_router_routes(self):
        tree = RouteExtractor().scan_workspace(str(self.ws))
        paths = {r.path for r in tree.routes}
        self.assertIn("/Contract/Index", paths)
        self.assertIn("/Contract/Sign", paths)
        contract = next(r for r in tree.routes if r.path == "/Contract/Index")
        self.assertEqual(contract.title, "قراردادها")
        self.assertTrue(
            contract.file_path
            and contract.file_path.replace("\\", "/").endswith("Views/Contract/Index.cshtml")
        )

    def test_razor_ng_form_fields(self):
        insp = RazorNgFormVisitor().parse_source(
            self.view, "Views/Contract/Index.cshtml"
        )
        self.assertTrue(insp.forms)
        names = {f.name for f in insp.forms[0].fields}
        self.assertIn("Title", names)
        self.assertIn("ContractNumber", names)
        self.assertTrue(any(b.is_submit for b in insp.forms[0].buttons))

    def test_angular_http_tracer(self):
        js = (self.ws / "Contents" / "angularjs" / "app.js").read_text(encoding="utf-8")
        calls = FrontendApiTracer().parse_file(js, "Contents/angularjs/app.js")
        kinds = {c.kind for c in calls}
        self.assertIn("angular_http", kinds)
        urls = {c.url_normalized for c in calls}
        self.assertTrue(any("/Contract/GetContractSignContext" in u for u in urls))
        self.assertTrue(any("/odata/contracts" in u for u in urls))


class TestMvcIndexIntegration(unittest.TestCase):
    def setUp(self):
        reset_index_managers()
        self._tmpdir = tempfile.TemporaryDirectory()
        self.index_root = self._tmpdir.name
        self.ws_path = str(Path("./sample_workspace/mvc_portal").resolve())

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

    def test_index_mvc_portal(self):
        toolbox = self._toolbox()
        with patch("src.core.config.settings.index_storage_path", self.index_root), patch(
            "src.knowledge.manager.settings.index_storage_path", self.index_root
        ):
            result = toolbox.index_workspace()
        self.assertGreater(result.get("routes", 0), 0)
        self.assertGreater(result.get("api_endpoints", 0), 0)
        self.assertGreater(result.get("form_fields", 0), 0)
        self.assertFalse(result.get("backend_skipped", True))
        # Entity from sibling Models
        self.assertGreaterEqual(result.get("entities", 0), 1)


if __name__ == "__main__":
    unittest.main()
