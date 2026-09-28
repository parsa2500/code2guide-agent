"""Tests for MVC Razor/Angular UI adapter (Permission, FieldHelper, fetch)."""

import unittest
from pathlib import Path

from src.parsers.mvc_ui_adapter import MvcRazorAngularAdapter
from src.parsers.frontend_api_tracer import FrontendApiTracer


class TestMvcUiAdapter(unittest.TestCase):
    def setUp(self):
        self.adapter = MvcRazorAngularAdapter()

    def test_permissions_and_field_helper(self):
        view = """
        @if (Permission.Contract.contract_base.Edit) {
          <button ng-click="save()">ذخیره</button>
        }
        """
        controller = """
        vm.Fields = FieldHelper.GetFieldWithCondition(json, step);
        bool ok = ApplicationSecurity.CheckPermissionAdditionalOptions(Permission.Request.Save);
        """
        result = self.adapter.parse(view, "Views/Contract/Edit.cshtml", controller, "Controllers/ContractController.cs")
        exprs = {p.expression for p in result.permissions}
        self.assertIn("Permission.Contract.contract_base.Edit", exprs)
        self.assertIn("Permission.Request.Save", exprs)
        self.assertTrue(any(p.kind == "check_permission" for p in result.permissions))
        methods = {f.method for f in result.field_helpers}
        self.assertIn("GetFieldWithCondition", methods)

    def test_fetch_in_cshtml_promoted_to_api_button(self):
        view = """
        <script>
        const res = await fetch("/ChatBot/Chat", { method: "POST", body: "{}" });
        </script>
        <button>گفتگوی جدید</button>
        """
        result = self.adapter.parse(view, "Views/ChatBot/Index.cshtml")
        urls = {c.url_normalized or c.url_raw for c in result.api_calls}
        self.assertTrue(any("/ChatBot/Chat" in u for u in urls))
        labels = []
        if result.inspection.forms:
            labels = [b.label for b in result.inspection.forms[0].buttons]
        labels += [b.label for b in result.inspection.standalone_buttons]
        self.assertTrue(any("ChatBot/Chat" in (l or "") for l in labels))

    def test_frontend_tracer_accepts_cshtml_extension(self):
        self.assertIn(".cshtml", FrontendApiTracer.EXTS)


class TestMvcUiAdapterAgainstDargahSample(unittest.TestCase):
    """Optional live-path smoke when Dargah tree is present."""

    ROOT = Path(r"C:\DargahNew\DargahV3\Dargah\Contracts.Main")

    def test_contract_edit_if_present(self):
        view = self.ROOT / "Areas/Requests/Views/Contract/Edit.cshtml"
        ctrl = self.ROOT / "Areas/Requests/Controllers/ContractController.cs"
        if not view.exists() or not ctrl.exists():
            self.skipTest("Dargah Contracts.Main not on disk")
        result = MvcRazorAngularAdapter().parse(
            view.read_text(encoding="utf-8", errors="replace"),
            str(view),
            ctrl.read_text(encoding="utf-8", errors="replace"),
            str(ctrl),
        )
        self.assertGreater(len(result.permissions), 0)
        self.assertGreater(len(result.field_helpers), 0)


if __name__ == "__main__":
    unittest.main()
