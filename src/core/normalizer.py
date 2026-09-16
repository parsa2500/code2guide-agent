"""Persian text and character normalization module.

Handles Arabic-to-Persian letter conversion, ZWNJ (نیم‌فاصله) regularization,
diacritics removal, and search query standardization.
"""

import re
import unicodedata
from typing import Optional, List, Set

try:
    import hazm
    _has_hazm = True
except ImportError:
    _has_hazm = False

ZWNJ = '\u200c'


class PersianNormalizer:
    """Comprehensive Persian normalizer conforming to enterprise UX search standards."""

    # Arabic to Persian character mapping
    ARABIC_TO_PERSIAN_MAP = {
        ord('ي'): 'ی',
        ord('ى'): 'ی',
        ord('ئ'): 'ی',
        ord('ك'): 'ک',
        ord('ة'): 'ه',
        ord('ؤ'): 'و',
        ord('إ'): 'ا',
        ord('أ'): 'ا',
        ord('آ'): 'آ',
        ord('ٱ'): 'ا',
    }

    # Arabic diacritics regex
    DIACRITICS_PATTERN = re.compile(r'[\u064B-\u065F\u0670\u06D6-\u06ED]')

    # Persian conversational stopwords for query intent extraction
    PERSIAN_STOPWORDS: Set[str] = {
        "چگونه", "چطور", "یک", "رو", "را", "کنم", "کنیم", "کنید", "کند",
        "کردن", "انجام", "شود", "می", "نمی", "این", "آن", "با", "از", "به",
        "در", "برای", "و", "یا", "که", "تا", "هست", "بود", "باشم"
    }

    ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
    PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
    ENGLISH_DIGITS = "0123456789"

    def __init__(self, use_hazm: bool = True):
        self.use_hazm = use_hazm and _has_hazm
        if self.use_hazm:
            self._hazm_normalizer = hazm.Normalizer()
        else:
            self._hazm_normalizer = None

    def unify_characters(self, text: str) -> str:
        """Replace Arabic letters with standard Persian equivalents."""
        if not text:
            return ""
        return text.translate(self.ARABIC_TO_PERSIAN_MAP)

    def strip_diacritics(self, text: str) -> str:
        """Remove Arabic/Persian vowels and phonetic markers."""
        if not text:
            return ""
        return self.DIACRITICS_PATTERN.sub('', text)

    def normalize_zwnj(self, text: str) -> str:
        """Normalize Zero Width Non-Joiner (ZWNJ / \u200c / نیم‌فاصله)."""
        if not text:
            return ""

        text = unicodedata.normalize('NFC', text)
        text = re.sub(r'\u200c+', ZWNJ, text)
        text = re.sub(r'[\s\u200c]*\s[\s\u200c]*', ' ', text)
        text = re.sub(r'(^\u200c+|\u200c+$)', '', text)
        text = re.sub(r'\u200c([^\u0600-\u06FF])', r'\1', text)
        text = re.sub(r'([^\u0600-\u06FF])\u200c', r'\1', text)

        text = re.sub(r'(?:\b|^)(ن?می)\s+([\u0600-\u06FF])', r'\g<1>' + ZWNJ + r'\g<2>', text)
        text = re.sub(r'([\u0600-\u06FF])\s+(ها|های|تر|ترین|ام|ات|اش|مان|تان|شان)(?:\b|$)', r'\g<1>' + ZWNJ + r'\g<2>', text)
        return text.strip()

    def normalize(self, text: str) -> str:
        """Full pipeline normalization of Persian text."""
        if not text:
            return ""

        text = self.unify_characters(text)
        text = self.strip_diacritics(text)
        text = self.normalize_zwnj(text)

        if self.use_hazm and self._hazm_normalizer:
            text = self._hazm_normalizer.normalize(text)

        text = re.sub(r'[ \t\r\f\v]+', ' ', text)
        return text.strip()

    def clean_search_query(self, query: str) -> str:
        """Cleans search query and preserves meaningful terms."""
        if not query:
            return ""
        normalized = self.normalize(query)
        cleaned = re.sub(r'["\'`؟?!,،:;؛\(\)\[\]\{\}]', ' ', normalized)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    def extract_keywords(self, query: str) -> List[str]:
        """Extracts substantive Persian action/entity keywords by removing stopwords."""
        cleaned = self.clean_search_query(query)
        words = cleaned.split()
        meaningful = [w for w in words if w not in self.PERSIAN_STOPWORDS and len(w) > 1]
        return meaningful if meaningful else words


default_normalizer = PersianNormalizer()

def normalize_persian_text(text: str) -> str:
    return default_normalizer.normalize(text)

def clean_search_query(query: str) -> str:
    return default_normalizer.clean_search_query(query)
