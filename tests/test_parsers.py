"""Tests for AST Visitor and Route Extractor."""

import unittest
from src.parsers.ast_visitor import JSXASTVisitor
from src.parsers.route_extractor import RouteExtractor


class TestParsers(unittest.TestCase):

    def setUp(self):
        self.visitor = JSXASTVisitor()
        self.route_extractor = RouteExtractor()

    def test_jsx_ast_visitor_form_extraction(self):
        jsx_code = """
        import React from 'react';
        export default function TenderForm() {
            return (
                <form>
                    <h2>ثبت مناقصه</h2>
                    <input name="subject" label="موضوع مناقصه" required />
                    <select name="type" label="نوع مناقصه" />
                    <textarea name="notes" label="یادداشت" />
                    <button type="submit">ثبت نهایی و ارسال</button>
                </form>
            );
        }
        """
        inspection = self.visitor.parse_source(jsx_code, file_path="src/pages/TenderForm.tsx")
        self.assertEqual(inspection.component_name, "TenderForm")
        self.assertGreaterEqual(len(inspection.forms), 1)

        form = inspection.forms[0]
        field_names = [f.name for f in form.fields]
        self.assertIn("subject", field_names)
        self.assertIn("type", field_names)
        self.assertIn("notes", field_names)

        subj_field = next(f for f in form.fields if f.name == "subject")
        self.assertTrue(subj_field.required)
        self.assertEqual(subj_field.label, "موضوع مناقصه")

        self.assertGreaterEqual(len(form.buttons), 1)
        submit_btn = form.buttons[0]
        self.assertTrue(submit_btn.is_submit)
        self.assertIn("ثبت نهایی و ارسال", submit_btn.label)

    def test_route_extractor_parsing(self):
        routes_code = """
        export const menuConfig = [
            {
                title: 'مدیریت مناقصات',
                path: '/tenders',
                children: [
                    { title: 'ثبت مناقصه جدید', path: '/tenders/create' }
                ]
            },
            { title: 'داشبورد کاربری', path: '/dashboard' }
        ];

        export const AppRouter = () => (
            <Routes>
                <Route path="/tenders" element={<Tenders />} />
                <Route path="/tenders/create" element={<TenderForm />} />
                <Route path="/dashboard" element={<Dashboard />} />
            </Routes>
        );
        """
        routes = self.route_extractor._parse_route_file(routes_code, file_path="src/routes.tsx")
        self.route_extractor._enrich_breadcrumbs(routes)

        paths = [r.path for r in routes]
        self.assertIn("/tenders", paths)
        self.assertIn("/tenders/create", paths)
        self.assertIn("/dashboard", paths)

        tender_create = next(r for r in routes if r.path == "/tenders/create")
        self.assertIn("منوی اصلی", tender_create.breadcrumbs)
        self.assertIn("مدیریت مناقصات", tender_create.breadcrumbs)
        self.assertIn("ثبت مناقصه جدید", tender_create.breadcrumbs)


if __name__ == "__main__":
    unittest.main()
