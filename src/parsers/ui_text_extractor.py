"""Extract visible UI copy from markup and script sources.

Targets headings, table headers, list/tab labels, short static text,
UI-facing script string literals, and validation error messages.
Filters noise (URLs, paths, empty bindings, class-like tokens, duplicates).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import List, Optional, Set

from pydantic import BaseModel, Field

from src.core.normalizer import PersianNormalizer, default_normalizer


class UiTextSpan(BaseModel):
    """A single visible UI text span extracted from source."""

    kind: str = Field(
        description="heading | table_header | list_item | tab | static | script_ui | error"
    )
    text: str
    line_number: int = 1
    context: Optional[str] = None
    file_path: str = ""


class UiTextExtractor:
    """Deterministic extractor for human-visible UI strings."""

    MIN_LEN = 2
    MAX_LEN = 80

    HEADING_TAGS = "h1|h2|h3|h4|h5|h6"
    STATIC_TAGS = "p|span|label|Label|FormLabel|InputLabel|div|strong|em|small|legend|caption"
    TAB_TAGS = "md-tab|Tab|TabPane|el-tab-pane|NavLink|NavItem"

    SCRIPT_UI_HINTS = re.compile(
        r"(?i)(?:alert|toast|snackbar|notify|notification|message|title|label|"
        r"caption|placeholder|error|warning|success|\$scope\.\w+|toastr|"
        r"showMessage|showError|showSuccess|SweetAlert|swal)"
    )

    NOISE_EXACT = frozenset(
        {
            "div",
            "span",
            "true",
            "false",
            "null",
            "undefined",
            "none",
            "n/a",
            "loading",
            "…",
            "...",
        }
    )

    def __init__(self, normalizer: Optional[PersianNormalizer] = None):
        self.normalizer = normalizer or default_normalizer

    def extract(self, code: str, file_path: str = "") -> List[UiTextSpan]:
        if not code or not code.strip():
            return []

        ext = Path(file_path).suffix.lower() if file_path else ""
        spans: List[UiTextSpan] = []
        seen: Set[str] = set()

        if ext in (".tsx", ".jsx", ".vue", ".html", ".cshtml", ".htm") or not ext:
            spans.extend(self._extract_markup(code, file_path))
            spans.extend(self._extract_typography_headings(code, file_path))
            spans.extend(self._extract_grid_columns(code, file_path))

        if ext in (".js", ".ts", ".tsx", ".jsx", ".vue", ".html", ".cshtml", ".htm") or not ext:
            spans.extend(self._extract_script_ui(code, file_path))

        spans.extend(self._extract_error_messages(code, file_path))

        out: List[UiTextSpan] = []
        for span in spans:
            cleaned = self._clean_text(span.text)
            if not self._is_useful(cleaned):
                continue
            key = f"{span.kind}:{cleaned.lower()}"
            if key in seen:
                continue
            seen.add(key)
            span.text = cleaned
            out.append(span)
        return out

    def _extract_markup(self, code: str, file_path: str) -> List[UiTextSpan]:
        spans: List[UiTextSpan] = []

        for m in re.finditer(
            rf"<(?P<tag>{self.HEADING_TAGS})\b[^>]*>(?P<body>.*?)</(?P=tag)>",
            code,
            re.I | re.DOTALL,
        ):
            text = self._strip_tags(m.group("body"))
            spans.append(
                UiTextSpan(
                    kind="heading",
                    text=text,
                    line_number=self._line_at(code, m.start()),
                    context=m.group("tag").lower(),
                    file_path=file_path,
                )
            )

        for m in re.finditer(
            r"<th\b[^>]*>(?P<body>.*?)</th>",
            code,
            re.I | re.DOTALL,
        ):
            text = self._strip_tags(m.group("body"))
            spans.append(
                UiTextSpan(
                    kind="table_header",
                    text=text,
                    line_number=self._line_at(code, m.start()),
                    context="th",
                    file_path=file_path,
                )
            )

        for m in re.finditer(
            r"<li\b[^>]*>(?P<body>.*?)</li>",
            code,
            re.I | re.DOTALL,
        ):
            text = self._strip_tags(m.group("body"))
            # Prefer short labels; skip huge nested blocks
            if text and len(text) <= self.MAX_LEN:
                spans.append(
                    UiTextSpan(
                        kind="list_item",
                        text=text,
                        line_number=self._line_at(code, m.start()),
                        context="li",
                        file_path=file_path,
                    )
                )

        for m in re.finditer(
            rf"<(?P<tag>{self.TAB_TAGS})\b(?P<attrs>[^>]*)>(?P<body>.*?)</(?P=tag)>",
            code,
            re.I | re.DOTALL,
        ):
            attrs = m.group("attrs") or ""
            label = self._attr_value(attrs, "label") or self._attr_value(attrs, "title")
            if not label:
                label = self._strip_tags(m.group("body"))
            if label:
                spans.append(
                    UiTextSpan(
                        kind="tab",
                        text=label,
                        line_number=self._line_at(code, m.start()),
                        context=m.group("tag"),
                        file_path=file_path,
                    )
                )

        # Self-closing / open tags with label/title attrs (md-tab label="…")
        for m in re.finditer(
            rf"<(?P<tag>{self.TAB_TAGS})\b(?P<attrs>[^>]*?)/?>",
            code,
            re.I,
        ):
            attrs = m.group("attrs") or ""
            label = self._attr_value(attrs, "label") or self._attr_value(attrs, "title")
            if label:
                spans.append(
                    UiTextSpan(
                        kind="tab",
                        text=label,
                        line_number=self._line_at(code, m.start()),
                        context=m.group("tag"),
                        file_path=file_path,
                    )
                )

        for m in re.finditer(
            rf"<(?P<tag>{self.STATIC_TAGS})\b[^>]*>(?P<body>.*?)</(?P=tag)>",
            code,
            re.I | re.DOTALL,
        ):
            body = m.group("body")
            # Only leaf-ish text (no nested block elements)
            if re.search(r"<(?:div|table|form|ul|ol|section|article)\b", body, re.I):
                continue
            text = self._strip_tags(body)
            if not text:
                continue
            spans.append(
                UiTextSpan(
                    kind="static",
                    text=text,
                    line_number=self._line_at(code, m.start()),
                    context=m.group("tag").lower(),
                    file_path=file_path,
                )
            )

        return spans

    def _extract_typography_headings(self, code: str, file_path: str) -> List[UiTextSpan]:
        """MUI-style <Typography variant=\"h1|h2|…\">text</Typography>."""
        spans: List[UiTextSpan] = []
        for m in re.finditer(
            r"""<(?P<tag>Typography)\b(?P<attrs>[^>]*)>(?P<body>.*?)</Typography>""",
            code,
            re.I | re.DOTALL,
        ):
            attrs = m.group("attrs") or ""
            variant = (self._attr_value(attrs, "variant") or "").lower()
            if not re.match(r"h[1-6]|title|subtitle", variant):
                continue
            text = self._strip_tags(m.group("body"))
            spans.append(
                UiTextSpan(
                    kind="heading",
                    text=text,
                    line_number=self._line_at(code, m.start()),
                    context=f"Typography:{variant}",
                    file_path=file_path,
                )
            )
        return spans

    def _extract_grid_columns(self, code: str, file_path: str) -> List[UiTextSpan]:
        """Common grid column caption patterns: field: 'x', headerName/title/caption."""
        spans: List[UiTextSpan] = []
        pattern = re.compile(
            r"""(?:headerName|header|caption|title|HeaderText)\s*[:=]\s*['"]([^'"]+)['"]""",
            re.I,
        )
        for m in pattern.finditer(code):
            spans.append(
                UiTextSpan(
                    kind="table_header",
                    text=m.group(1),
                    line_number=self._line_at(code, m.start()),
                    context="grid_column",
                    file_path=file_path,
                )
            )
        return spans

    def _extract_script_ui(self, code: str, file_path: str) -> List[UiTextSpan]:
        spans: List[UiTextSpan] = []
        for m in re.finditer(r"""(['"])(?P<text>[^'"\n]{2,80})\1""", code):
            start = m.start()
            window = code[max(0, start - 120) : start]
            text_raw = m.group("text")
            hinted = bool(self.SCRIPT_UI_HINTS.search(window))
            persian_scope = bool(
                re.search(r"[\u0600-\u06FF]", text_raw) and re.search(r"\$scope\.", window)
            )
            if not hinted and not persian_scope:
                continue
            text = text_raw.replace("\\'", "'").replace('\\"', '"').replace("\\n", " ")
            spans.append(
                UiTextSpan(
                    kind="script_ui",
                    text=text,
                    line_number=self._line_at(code, start),
                    context="script",
                    file_path=file_path,
                )
            )
        return spans

    def _extract_error_messages(self, code: str, file_path: str) -> List[UiTextSpan]:
        spans: List[UiTextSpan] = []
        patterns = [
            # Zod / RHF / JSX helpers
            r"""(?:message|required_error|invalid_type_error|helperText|errorMessage)\s*[:=]\s*['"]([^'"]+)['"]""",
            # DataAnnotations
            r"""ErrorMessage\s*=\s*["']([^"']+)["']""",
            # Angular / generic required message attrs
            r"""(?:ng-required-message|data-msg-required|validationMessage)\s*=\s*["']([^"']+)["']""",
        ]
        for pat in patterns:
            for m in re.finditer(pat, code, re.I):
                spans.append(
                    UiTextSpan(
                        kind="error",
                        text=m.group(1),
                        line_number=self._line_at(code, m.start()),
                        context="validation",
                        file_path=file_path,
                    )
                )
        return spans

    @staticmethod
    def stable_id(file_path: str, kind: str, text: str) -> str:
        digest = hashlib.md5(f"{file_path}|{kind}|{text}".encode("utf-8")).hexdigest()[:12]
        return f"ui_text:{file_path}:{kind}:{digest}"

    def _clean_text(self, text: str) -> str:
        text = text or ""
        text = re.sub(r"\{\{[^}]*\}\}", " ", text)
        text = re.sub(r"@\([^)]*\)", " ", text)
        text = re.sub(r"\s+", " ", text).strip(" \n\r\t*·•|-")
        if hasattr(self.normalizer, "normalize"):
            try:
                text = self.normalizer.normalize(text)
            except Exception:
                pass
        return text.strip()

    def _is_useful(self, text: str) -> bool:
        if not text or len(text) < self.MIN_LEN or len(text) > self.MAX_LEN:
            return False
        low = text.lower().strip()
        if low in self.NOISE_EXACT:
            return False
        # Empty / binding-only leftovers
        if re.fullmatch(r"[\{\}\[\]\(\)\s\.\,\;\:]+", text):
            return False
        # URL / path / email
        if re.search(r"https?://|www\.|\\|/[\w.\-]+/|@", text) and not re.search(
            r"[\u0600-\u06FF]", text
        ):
            if re.match(r"^(https?://|www\.|[./\\]|[A-Za-z]:\\)", text):
                return False
            if "/" in text or "\\" in text:
                if not re.search(r"\s", text):
                    return False
        # Pure class/id-like tokens
        if re.fullmatch(r"[A-Za-z][\w\-]*", text) and not re.search(r"[a-z][A-Z]", text):
            # Allow short English UI words with spaces only; single camel/snake skip if looks like code
            if "_" in text or text.endswith("Id") or text.endswith("Ctrl"):
                return False
        # Minified-looking: no spaces and very long alphanumeric
        if " " not in text and len(text) > 40 and re.fullmatch(r"[\w\-]+", text):
            return False
        return True

    @staticmethod
    def _strip_tags(html: str) -> str:
        text = re.sub(r"<[^>]+>", " ", html or "")
        text = re.sub(r"\{\{[^}]*\}\}", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _attr_value(attrs: str, name: str) -> Optional[str]:
        m = re.search(
            rf"""\b{re.escape(name)}\s*=\s*(?:['"]([^'"]+)['"]|\{{['"]([^'"]+)['"]\}})""",
            attrs or "",
            re.I,
        )
        if not m:
            return None
        return m.group(1) or m.group(2)

    @staticmethod
    def _line_at(code: str, pos: int) -> int:
        return code[:pos].count("\n") + 1
