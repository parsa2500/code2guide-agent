"""Unit tests for alias, i18n, validation, and OpenAPI/RBAC parsers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.parsers.alias_resolver import PathAliasResolver
from src.parsers.i18n_parser import I18nParser
from src.parsers.validation_parser import ValidationParser
from src.parsers.openapi_parser import BackendContractExtractor
from src.agent.workflow import Code2GuideWorkflow
from src.agent.state import AgentState


class TestGeminiAdaptedParsers(unittest.TestCase):

    def test_alias_resolver_from_tsconfig(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src" / "components").mkdir(parents=True)
            form = root / "src" / "components" / "Form.tsx"
            form.write_text("export const Form = () => null;\n", encoding="utf-8")
            (root / "tsconfig.json").write_text(
                json.dumps(
                    {
                        "compilerOptions": {
                            "baseUrl": ".",
                            "paths": {"@/*": ["src/*"]},
                        }
                    }
                ),
                encoding="utf-8",
            )
            resolver = PathAliasResolver(str(root))
            resolved = resolver.resolve_import("@/components/Form", root / "src" / "App.tsx")
            self.assertIsNotNone(resolved)
            self.assertTrue(resolved.exists())
            self.assertEqual(resolved.name, "Form.tsx")

    def test_i18n_t_replace_and_page_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            loc = root / "locales" / "fa"
            loc.mkdir(parents=True)
            (loc / "common.json").write_text(
                json.dumps({"tenders": {"title": "ثبت مناقصه"}}),
                encoding="utf-8",
            )
            cfg = root / "src" / "config"
            cfg.mkdir(parents=True)
            (cfg / "i18n.ts").write_text(
                'export const pageLabels = {\n'
                '  knowledge: { fa: "پایگاه دانش", en: "Knowledge" },\n'
                '};\n',
                encoding="utf-8",
            )
            parser = I18nParser(str(root))
            self.assertEqual(parser.resolve_key("tenders.title"), "ثبت مناقصه")
            self.assertEqual(parser.label_for_page_id("knowledge"), "پایگاه دانش")
            code = "const title = t('tenders.title');"
            replaced = parser.replace_i18n_calls(code)
            self.assertIn('"ثبت مناقصه"', replaced)

    def test_validation_zod_and_rhf(self):
        zod_code = """
        const schema = z.object({
          subject: z.string({ required_error: "عنوان الزامی است" }),
          notes: z.string().optional(),
        });
        """
        zod_rules = ValidationParser.extract_zod_rules(zod_code)
        self.assertIn("subject", zod_rules)
        self.assertTrue(zod_rules["subject"].is_required)
        self.assertEqual(zod_rules["subject"].error_message, "عنوان الزامی است")
        self.assertIn("notes", zod_rules)
        self.assertFalse(zod_rules["notes"].is_required)

        rhf_code = """
        <input {...register("serviceName", { required: "نام سرویس الزامی است" })} />
        """
        rhf_rules = ValidationParser.extract_rhf_rules(rhf_code)
        self.assertTrue(rhf_rules["serviceName"].is_required)
        self.assertEqual(rhf_rules["serviceName"].error_message, "نام سرویس الزامی است")

    def test_openapi_and_permissions_bindings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = root / "docs"
            docs.mkdir()
            (docs / "swagger.json").write_text(
                json.dumps(
                    {
                        "openapi": "3.0.0",
                        "paths": {
                            "/api/companies": {
                                "get": {
                                    "summary": "List companies",
                                    "security": [{"Bearer": ["admin.companies.view"]}],
                                }
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            utils = root / "src" / "utils"
            utils.mkdir(parents=True)
            (utils / "permissions.ts").write_text(
                'export const Permissions = {\n'
                '  CompaniesView: "admin.companies.view",\n'
                '  KnowledgeView: "admin.knowledge.view",\n'
                '};\n',
                encoding="utf-8",
            )
            layouts = root / "src" / "layouts"
            layouts.mkdir(parents=True)
            (layouts / "navigation.ts").write_text(
                'export const navigationItems = [\n'
                '  {\n'
                '    id: "companies",\n'
                '    LabelFa: "شرکت‌ها",\n'
                '    requiredPermission: Permissions.CompaniesView,\n'
                '  },\n'
                '  {\n'
                '    id: "knowledge",\n'
                '    LabelFa: "پایگاه دانش",\n'
                '    requiredPermission: Permissions.KnowledgeView,\n'
                '  },\n'
                '];\n',
                encoding="utf-8",
            )

            extractor = BackendContractExtractor(str(root))
            endpoints = extractor.scan_rbac_and_swagger()
            self.assertTrue(any(e.path == "/api/companies" for e in endpoints))
            companies_ep = next(e for e in endpoints if e.path == "/api/companies")
            self.assertIn("admin.companies.view", companies_ep.roles_required)

            roles = extractor.roles_for_page_id("knowledge")
            self.assertIn("admin.knowledge.view", roles)

    def test_synthesize_guide_includes_rbac_note(self):
        from unittest.mock import patch

        wf = Code2GuideWorkflow(workspace_path=".")
        state = AgentState(
            query="چگونه شرکت‌ها را ببینم؟",
            workspace_path=".",
            extracted_breadcrumbs=["منوی اصلی", "شرکت‌ها"],
            required_roles=["admin.companies.view"],
            discovered_forms=[],
            identified_routes=[],
        )
        # Force template path so RBAC note assertion is deterministic (no live LLM).
        with patch.object(wf, "_call_real_llm", return_value=None), patch(
            "src.agent.workflow.settings.openrouter_api_key", None
        ), patch("src.agent.workflow.settings.openai_api_key", None), patch.dict(
            "os.environ",
            {"OPENROUTER_API_KEY": "", "OPENAI_API_KEY": ""},
            clear=False,
        ):
            out = wf.node_synthesize_guide(state)
        guide = out.get("final_persian_guide") or ""
        self.assertIn("RBAC", guide)
        self.assertIn("admin.companies.view", guide)
        self.assertIn("مسیر دسترسی", guide)


if __name__ == "__main__":
    unittest.main()
