"""Tests for Markdown guide normalization / display prep."""

import unittest

from src.core.markdown_guide import normalize_guide_markdown


class TestMarkdownGuide(unittest.TestCase):
    def test_expands_literal_escaped_newlines(self):
        raw = "### ۱. مسیر\\n- گام یک\\n- گام دو\\n\\n### ۲. فیلدها"
        out = normalize_guide_markdown(raw)
        self.assertIn("\n- گام یک\n", out)
        self.assertIn("\n\n### ۲. فیلدها\n", out)
        self.assertNotIn("\\n", out)

    def test_preserves_already_valid_markdown(self):
        raw = "### عنوان\n\n- مورد یک\n- مورد دو\n"
        out = normalize_guide_markdown(raw)
        self.assertEqual(out.strip(), raw.strip())


if __name__ == "__main__":
    unittest.main()
