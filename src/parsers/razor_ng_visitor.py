"""Regex visitor for Razor (.cshtml) and AngularJS templates (ng-model forms)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from src.core.normalizer import PersianNormalizer, default_normalizer
from src.parsers.ast_visitor import (
    ComponentInspection,
    DiscoveredForm,
    UIButton,
    UIField,
)


class RazorNgFormVisitor:
    """Extract ng-model fields, Persian labels, and buttons from Razor/HTML."""

    SUBMIT_KEYWORDS = [
        "ثبت",
        "ارسال",
        "ذخیره",
        "تایید",
        "ایجاد",
        "افزودن",
        "امضا",
        "submit",
        "save",
        "confirm",
        "create",
        "sign",
    ]

    def __init__(self, normalizer: Optional[PersianNormalizer] = None):
        self.normalizer = normalizer or default_normalizer

    def parse_source(self, code: str, file_path: str = "") -> ComponentInspection:
        if not code or not code.strip():
            return ComponentInspection(file_path=file_path)

        fields = self._parse_fields(code)
        buttons = self._parse_buttons(code)
        form_name = Path(file_path).stem if file_path else "Form"
        forms: List[DiscoveredForm] = []
        if fields or buttons:
            forms.append(
                DiscoveredForm(
                    form_name=form_name,
                    file_path=file_path,
                    fields=fields,
                    buttons=buttons,
                    start_line=1,
                    end_line=code.count("\n") + 1,
                )
            )
        return ComponentInspection(
            file_path=file_path,
            component_name=form_name,
            forms=forms,
            standalone_fields=[],
            standalone_buttons=[],
        )

    def _parse_fields(self, code: str) -> List[UIField]:
        fields: List[UIField] = []
        seen = set()
        # Match input/select/textarea — prefer ng-model, also accept name/id with clear label
        pattern = re.compile(
            r"<(?P<tag>input|select|textarea|md-input|dx-text-box)(?P<attrs>[^>]*)>",
            re.I | re.DOTALL,
        )
        for m in pattern.finditer(code):
            attrs = m.group("attrs") or ""
            tag = m.group("tag").lower()
            model_m = re.search(r"""ng-model\s*=\s*["']([^"']+)["']""", attrs, re.I)
            name_m = re.search(r"""(?:name|id)\s*=\s*["']([^"']+)["']""", attrs, re.I)
            if model_m:
                model = model_m.group(1).strip()
                name = model.split(".")[-1] if "." in model else model
            elif name_m:
                name = name_m.group(1).strip()
            else:
                continue
            if name in seen:
                continue

            field_type = "text"
            type_m = re.search(r"""type\s*=\s*["']([^"']+)["']""", attrs, re.I)
            if type_m:
                field_type = type_m.group(1).lower()
            elif tag == "select":
                field_type = "select"
            elif tag == "textarea":
                field_type = "textarea"

            required = bool(
                re.search(r"""\brequired\b|ng-required\s*=\s*["']true["']""", attrs, re.I)
            )
            disabled = bool(re.search(r"""\bdisabled\b|ng-disabled\s*=""", attrs, re.I))
            placeholder = None
            ph = re.search(r"""placeholder\s*=\s*["']([^"']+)["']""", attrs, re.I)
            if ph:
                placeholder = ph.group(1)

            line_number = code[: m.start()].count("\n") + 1
            label = self._find_label_near(code, m.start(), name)

            # Without ng-model, only keep if we found a real label (not just the name fallback)
            if not model_m and (not label or label == name) and not placeholder:
                continue

            seen.add(name)
            fields.append(
                UIField(
                    name=name,
                    field_type=field_type,
                    label=label,
                    placeholder=placeholder,
                    required=required,
                    disabled=disabled,
                    line_number=line_number,
                )
            )
        return fields

    def _find_label_near(self, code: str, pos: int, field_name: str) -> Optional[str]:
        window = code[max(0, pos - 500) : pos + 200]

        # IsRtl ? "فارسی" : "English"
        isrtl = re.search(
            r"""IsRtl\s*\?\s*["']([^"']+)["']\s*:\s*["'][^"']*["']""",
            window,
        )
        if isrtl:
            return self.normalizer.normalize(isrtl.group(1)) if hasattr(self.normalizer, "normalize") else isrtl.group(1)

        # @Contracts.Resources.Resources.Key
        res = re.search(
            r"@(?:Contracts\.)?Resources\.Resources\.(\w+)",
            window,
        )
        if res:
            # Use resource key as humanized label fallback
            key = res.group(1)
            human = re.sub(r"([a-z])([A-Z])", r"\1 \2", key)
            return human

        # <label ...>...</label>
        labels = list(
            re.finditer(
                r"<label[^>]*>(.*?)</label>",
                window,
                re.I | re.DOTALL,
            )
        )
        if labels:
            raw = labels[-1].group(1)
            raw = re.sub(r"<[^>]+>", "", raw)
            raw = re.sub(r"@\([^)]+\)", "", raw)
            raw = re.sub(r"\{\{[^}]+\}\}", "", raw)
            raw = re.sub(r"\s+", " ", raw).strip(" *\n\r\t")
            if raw and len(raw) < 80:
                return raw

        return field_name

    def _parse_buttons(self, code: str) -> List[UIButton]:
        buttons: List[UIButton] = []
        pattern = re.compile(
            r"<(?P<tag>button|a|input)(?P<attrs>[^>]*)>(?P<body>.*?)</(?P=tag)>|"
            r"<input(?P<attrs2>[^>]*type\s*=\s*[\"'](?:submit|button)[\"'][^>]*)/?>",
            re.I | re.DOTALL,
        )
        for m in pattern.finditer(code):
            attrs = m.group("attrs") or m.group("attrs2") or ""
            body = m.group("body") or ""
            if not re.search(r"""ng-click\s*=|type\s*=\s*["']submit["']|type\s*=\s*["']button["']""", attrs, re.I):
                # Still accept buttons with Persian text in body
                if not re.search(r"[\u0600-\u06FF]", body):
                    continue

            label = self._button_label(attrs, body)
            if not label:
                continue
            is_submit = bool(
                re.search(r"""type\s*=\s*["']submit["']""", attrs, re.I)
                or any(k in label.lower() for k in self.SUBMIT_KEYWORDS)
                or any(k in label for k in self.SUBMIT_KEYWORDS)
            )
            line_number = code[: m.start()].count("\n") + 1
            name = None
            id_m = re.search(r"""(?:id|name)\s*=\s*["']([^"']+)["']""", attrs, re.I)
            if id_m:
                name = id_m.group(1)
            buttons.append(
                UIButton(
                    label=label,
                    name=name,
                    action_type="submit" if is_submit else "button",
                    is_submit=is_submit,
                    line_number=line_number,
                )
            )
        return buttons

    def _button_label(self, attrs: str, body: str) -> str:
        # IsRtl ternary in body
        isrtl = re.search(
            r"""IsRtl\s*\?\s*["']([^"']+)["']""",
            body,
        )
        if isrtl:
            return isrtl.group(1).strip()
        value_m = re.search(r"""value\s*=\s*["']([^"']+)["']""", attrs, re.I)
        if value_m:
            return value_m.group(1).strip()
        clean = re.sub(r"<[^>]+>", "", body)
        clean = re.sub(r"\{\{[^}]+\}\}", "", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean[:80] if clean else ""
