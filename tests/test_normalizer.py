"""Tests for Persian text normalization and character conversion."""

import unittest
from src.core.normalizer import PersianNormalizer, normalize_persian_text, clean_search_query


class TestPersianNormalizer(unittest.TestCase):

    def setUp(self):
        self.normalizer = PersianNormalizer(use_hazm=False)

    def test_arabic_character_replacement(self):
        raw = "ثبت يک مناقصه جديد با كد رهگيري و تأييد"
        normalized = self.normalizer.unify_characters(raw)
        self.assertNotIn("ي", normalized)
        self.assertNotIn("ك", normalized)
        self.assertIn("یک", normalized)
        self.assertIn("کد", normalized)
        self.assertIn("رهگیری", normalized)

    def test_diacritics_stripping(self):
        raw = "مُناقَصَةٌ جَدِيدَةٌ"
        stripped = self.normalizer.strip_diacritics(raw)
        normalized = self.normalizer.normalize(stripped)
        self.assertTrue(normalized in ("مناقصه جدیده", "مناقصه جدید"))

    def test_zwnj_normalization(self):
        t1 = self.normalizer.normalize_zwnj("می شود")
        self.assertIn("\u200c", t1)
        self.assertEqual(t1, "می\u200cشود")

        t2 = self.normalizer.normalize_zwnj("سامانه ها")
        self.assertIn("\u200c", t2)
        self.assertEqual(t2, "سامانه\u200cها")

    def test_clean_search_query_and_keywords(self):
        q = "چگونه یک مناقصه جدید ثبت کنم؟"
        cleaned = self.normalizer.clean_search_query(q)
        self.assertNotIn("؟", cleaned)
        keywords = self.normalizer.extract_keywords(q)
        self.assertIn("مناقصه", keywords)
        self.assertIn("ثبت", keywords)
        self.assertNotIn("چگونه", keywords)


if __name__ == "__main__":
    unittest.main()
