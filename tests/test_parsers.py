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

    def test_spa_pageid_label_fa_and_switch(self):
        nav_code = """
        export const navigationItems = [
          {
            id: "dashboard",
            LabelFa: "داشبورد",
            LabelEn: "Dashboard",
            icon: Gauge,
          },
          {
            id: "knowledge",
            LabelFa: "پایگاه دانش",
            LabelEn: "Knowledge Base",
            icon: KeyRound,
          },
          // {
          //   id: "appearance",
          //   LabelFa: "ظاهر",
          //   LabelEn: "Appearance",
          // },
        ];
        """
        app_code = """
        const page = useMemo(() => {
          switch (effectivePage) {
            case "dashboard":
              return <DashboardPage language={language} />;
            case "knowledge":
              return <KnowledgeBasePage language={language} />;
            case "user-chat":
              return (
                <UserChatPage
                  userId={apiConfig.defaultUserId}
                  language={language}
                />
              );
            case "profile":
              return <ProfilePage language={language} />;
            default:
              return null;
          }
        }, [effectivePage]);
        """
        nav_routes = self.route_extractor._parse_route_file(nav_code, file_path="src/layouts/navigation.ts")
        app_routes = self.route_extractor._parse_route_file(app_code, file_path="src/App.tsx")

        by_path = {r.path: r for r in nav_routes}
        for r in app_routes:
            if r.path in by_path:
                if r.component_name and not by_path[r.path].component_name:
                    by_path[r.path].component_name = r.component_name
            else:
                by_path[r.path] = r

        routes = list(by_path.values())
        self.route_extractor._enrich_breadcrumbs(routes)

        paths = [r.path for r in routes]
        self.assertIn("/dashboard", paths)
        self.assertIn("/knowledge", paths)
        self.assertIn("/user-chat", paths)
        self.assertIn("/profile", paths)
        self.assertNotIn("/appearance", paths)

        dashboard = by_path["/dashboard"]
        self.assertEqual(dashboard.title, "داشبورد")
        self.assertEqual(dashboard.component_name, "DashboardPage")
        self.assertIn("داشبورد", dashboard.breadcrumbs)

        knowledge = by_path["/knowledge"]
        self.assertEqual(knowledge.title, "پایگاه دانش")
        self.assertEqual(knowledge.component_name, "KnowledgeBasePage")

        user_chat = by_path["/user-chat"]
        self.assertEqual(user_chat.component_name, "UserChatPage")


if __name__ == "__main__":
    unittest.main()
