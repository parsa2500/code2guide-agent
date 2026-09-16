"""Schema validation parser for Zod and react-hook-form required rules."""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ValidationRule(BaseModel):
    """A single field validation constraint extracted from schema or form code."""

    field_name: str
    is_required: bool = True
    error_message: Optional[str] = None
    min_value: Optional[str] = None
    max_value: Optional[str] = None
    source: str = Field(default="unknown", description="zod | rhf | yup")


class ValidationParser:
    """Extracts required/optional rules from Zod objects and react-hook-form register()."""

    @staticmethod
    def extract_zod_rules(code: str) -> Dict[str, ValidationRule]:
        rules: Dict[str, ValidationRule] = {}
        for block in ValidationParser._iter_zod_object_bodies(code):
            for m in re.finditer(
                r"(?:^|[,{\n])\s*(?P<name>[A-Za-z_][\w]*)\s*:\s*(?P<schema>z\.[^\n]+)",
                block,
            ):
                field_name = m.group("name")
                schema_chain = m.group("schema").strip().rstrip(",")
                rules[field_name] = ValidationParser._rule_from_zod_chain(
                    field_name, schema_chain
                )
        return rules

    @staticmethod
    def _iter_zod_object_bodies(code: str):
        """Yield inner bodies of z.object({ ... }) with nested-brace awareness."""
        marker = "z.object("
        start = 0
        while True:
            idx = code.find(marker, start)
            if idx < 0:
                return
            i = idx + len(marker)
            while i < len(code) and code[i].isspace():
                i += 1
            if i >= len(code) or code[i] != "{":
                start = idx + len(marker)
                continue
            depth = 0
            body_start = i + 1
            j = i
            while j < len(code):
                ch = code[j]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        yield code[body_start:j]
                        start = j + 1
                        break
                j += 1
            else:
                return

    @staticmethod
    def _rule_from_zod_chain(field_name: str, schema_chain: str) -> ValidationRule:
        is_optional = ".optional()" in schema_chain or ".nullable()" in schema_chain
        err_match = re.search(
            r"""(?:message|required_error|invalid_type_error)\s*:\s*['"]([^'"]+)['"]""",
            schema_chain,
        )
        min_m = re.search(r"""\.min\(\s*([^,\)]+)""", schema_chain)
        max_m = re.search(r"""\.max\(\s*([^,\)]+)""", schema_chain)
        return ValidationRule(
            field_name=field_name,
            is_required=not is_optional,
            error_message=err_match.group(1) if err_match else None,
            min_value=min_m.group(1).strip() if min_m else None,
            max_value=max_m.group(1).strip() if max_m else None,
            source="zod",
        )

    @staticmethod
    def extract_rhf_rules(code: str) -> Dict[str, ValidationRule]:
        """Parse register('field', { required: '...' | true }) patterns."""
        rules: Dict[str, ValidationRule] = {}
        pattern = re.finditer(
            r"""register\(\s*['"](?P<name>[^'"]+)['"]\s*,\s*\{(?P<body>[^{}]*)\}""",
            code,
            re.MULTILINE | re.DOTALL,
        )
        for m in pattern:
            field_name = m.group("name")
            body = m.group("body")
            req_str = re.search(
                r"""required\s*:\s*['"](?P<msg>[^'"]+)['"]""",
                body,
            )
            req_bool = re.search(r"""required\s*:\s*true\b""", body)
            if not req_str and not req_bool:
                # still record if other validators present
                if "min" not in body and "max" not in body and "validate" not in body:
                    continue
                rules[field_name] = ValidationRule(
                    field_name=field_name,
                    is_required=False,
                    source="rhf",
                )
                continue
            rules[field_name] = ValidationRule(
                field_name=field_name,
                is_required=True,
                error_message=req_str.group("msg") if req_str else None,
                source="rhf",
            )
        return rules

    @classmethod
    def extract_all(cls, code: str) -> Dict[str, ValidationRule]:
        merged = cls.extract_zod_rules(code)
        for name, rule in cls.extract_rhf_rules(code).items():
            if name not in merged:
                merged[name] = rule
            else:
                # Prefer required=True and non-empty message
                if rule.is_required:
                    merged[name].is_required = True
                if rule.error_message and not merged[name].error_message:
                    merged[name].error_message = rule.error_message
        return merged

    @classmethod
    def as_notes(cls, rules: Dict[str, ValidationRule]) -> List[str]:
        notes: List[str] = []
        for rule in rules.values():
            status = "الزامی" if rule.is_required else "اختیاری"
            msg = f" — {rule.error_message}" if rule.error_message else ""
            notes.append(f"{rule.field_name}: {status}{msg} ({rule.source})")
        return notes
