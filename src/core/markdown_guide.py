"""Normalize and prepare Persian UX guide markdown for display."""

from __future__ import annotations

import re


_ESCAPED_NEWLINE = re.compile(r"(?<!\\)\\n")
_ESCAPED_TAB = re.compile(r"(?<!\\)\\t")
_ESCAPED_CR = re.compile(r"(?<!\\)\\r(?!\\n)")


def normalize_guide_markdown(text: str | None) -> str:
    """Turn JSON/LLM-style escaped newlines into real Markdown line breaks.

    Models and JSON round-trips sometimes leave literal ``\\n`` sequences in the
    guide string. Markdown viewers then show one long line instead of headings,
    lists, and sections.
    """
    if not text:
        return ""

    guide = text.strip()

    # Expand escapes when the payload looks like a single escaped block
    # (common when copying the JSON ``guide`` field into a .md file).
    if "\\n" in guide and guide.count("\n") <= 1:
        guide = guide.replace("\\r\\n", "\n")
        guide = _ESCAPED_NEWLINE.sub("\n", guide)
        guide = _ESCAPED_TAB.sub("\t", guide)
        guide = _ESCAPED_CR.sub("", guide)

    guide = guide.replace("\r\n", "\n").replace("\r", "\n")
    guide = "\n".join(line.rstrip() for line in guide.split("\n"))
    return guide.strip() + "\n"
