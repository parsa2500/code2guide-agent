"""Tests for UiTextExtractor and frontend ui_text indexing."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.knowledge.indexer import FrontendIndexer
from src.knowledge.schema import NodeType
from src.knowledge.store import GraphStore
from src.parsers.ui_text_extractor import UiTextExtractor
from src.search.hybrid_indexer import HybridIndexer, collection_name_for_workspace


class TestUiTextExtractor(unittest.TestCase):
    def setUp(self):
        self.ext = UiTextExtractor()

    def test_heading_table_list_and_error(self):
        html = """
        <h1>ثبت مناقصه</h1>
        <table>
          <thead><tr><th>عنوان</th><th>وضعیت</th></tr></thead>
        </table>
        <ul><li>مرحله اول</li><li>مرحله دوم</li></ul>
        <md-tab label="جزئیات"></md-tab>
        <p>لطفا فرم را تکمیل کنید</p>
        <input required ErrorMessage="این فیلد الزامی است" />
        """
        # ErrorMessage on input attr won't match our patterns on raw HTML;
        # use zod-style + DataAnnotations style in same blob:
        code = html + '\nmessage: "مقدار نامعتبر است"\n[Required(ErrorMessage="نام الزامی است")]\n'
        spans = self.ext.extract(code, file_path="Views/Page.cshtml")
        kinds = {s.kind for s in spans}
        texts = {s.text for s in spans}
        self.assertIn("heading", kinds)
        self.assertIn("table_header", kinds)
        self.assertIn("list_item", kinds)
        self.assertIn("tab", kinds)
        self.assertIn("static", kinds)
        self.assertIn("error", kinds)
        self.assertTrue(any("ثبت مناقصه" in t for t in texts))
        self.assertTrue(any("عنوان" in t for t in texts))
        self.assertTrue(any("نام الزامی" in t for t in texts))

    def test_script_ui_near_toast(self):
        js = """
        function save() {
          toastr.success('عملیات با موفقیت انجام شد');
          alert('خطا در ذخیره');
          var x = 'internal_code_path';
        }
        """
        spans = self.ext.extract(js, file_path="Contents/app.js")
        texts = [s.text for s in spans if s.kind == "script_ui"]
        self.assertTrue(any("موفقیت" in t for t in texts))
        self.assertTrue(any("خطا" in t for t in texts))
        self.assertFalse(any("internal_code_path" in t for t in texts))

    def test_noise_filtered(self):
        code = '<p>https://example.com/api</p><p>ok</p><div>node_modules/foo</div>'
        spans = self.ext.extract(code, file_path="a.html")
        texts = {s.text for s in spans}
        self.assertNotIn("https://example.com/api", texts)


class TestUiTextIndexing(unittest.TestCase):
    def test_indexer_creates_ui_text_nodes(self):
        from src.agent.tools import Code2GuideToolbox

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            page = root / "pages" / "Demo.tsx"
            page.parent.mkdir(parents=True)
            page.write_text(
                """
                export default function Demo() {
                  return (
                    <div>
                      <h2>صفحه نمونه</h2>
                      <table><thead><tr><th>نام</th><th>کد</th></tr></thead></table>
                      <button type="submit">ذخیره</button>
                    </div>
                  );
                }
                """,
                encoding="utf-8",
            )
            (root / "routes.tsx").write_text(
                """
                export const menuConfig = [
                  { title: 'نمونه', path: '/demo' }
                ];
                export const AppRouter = () => (
                  <Routes>
                    <Route path="/demo" element={<Demo />} />
                  </Routes>
                );
                """,
                encoding="utf-8",
            )

            indexer = HybridIndexer(
                collection_name=collection_name_for_workspace(str(root)),
                url=None,
                location=":memory:",
                embedding_provider="none",
            )
            toolbox = Code2GuideToolbox(workspace_path=str(root), hybrid_indexer=indexer)
            store = GraphStore(str(root), db_path=root / "test_index.db")
            try:
                result = FrontendIndexer(toolbox, store).index(rebuild=True)

                self.assertGreater(result.ui_texts, 0)
                ui_nodes = store.list_nodes(NodeType.UI_TEXT)
                self.assertGreater(len(ui_nodes), 0)
                titles = " ".join(n.title for n in ui_nodes)
                self.assertTrue("صفحه نمونه" in titles or "نام" in titles)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
