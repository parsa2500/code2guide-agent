"""Adapter for ASP.NET MVC Razor + AngularJS UI signals beyond ng-model forms.

Closes W1-03 gaps: Permission.* bindings, FieldHelper dynamic fields, and
JS HTTP actions (fetch / $http / axios) embedded in .cshtml.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from pydantic import BaseModel, Field

from src.parsers.ast_visitor import ComponentInspection, UIButton
from src.parsers.frontend_api_tracer import FrontendApiCall, FrontendApiTracer
from src.parsers.razor_ng_visitor import RazorNgFormVisitor


class PermissionBinding(BaseModel):
    """A Permission.* or CheckPermission* reference in view/controller source."""

    expression: str
    kind: str = "permission"  # permission | check_permission
    line_number: int = 1
    source: str = "view"  # view | controller


class FieldHelperCall(BaseModel):
    """A FieldHelper.* call that implies runtime-dynamic form fields."""

    method: str
    line_number: int = 1
    source: str = "controller"  # view | controller
    snippet: str = ""


class MvcUiAdapterResult(BaseModel):
    """Combined Razor form inspection plus MVC/Angular adapter signals."""

    inspection: ComponentInspection
    permissions: List[PermissionBinding] = Field(default_factory=list)
    field_helpers: List[FieldHelperCall] = Field(default_factory=list)
    api_calls: List[FrontendApiCall] = Field(default_factory=list)


class MvcRazorAngularAdapter:
    """Enrich Razor/Angular pages with permission, FieldHelper, and JS API signals."""

    PERMISSION_RE = re.compile(r"\bPermission\.[A-Za-z0-9_\.]+")
    CHECK_PERM_RE = re.compile(
        r"\b(?:ApplicationSecurity\.)?CheckPermission(?:AdditionalOptions)?\s*\("
    )
    FIELD_HELPER_RE = re.compile(
        r"\bFieldHelper\.(?P<method>[A-Za-z0-9_]+)\s*\(",
        re.I,
    )
    NG_CLICK_RE = re.compile(
        r"""ng-click\s*=\s*["']([^"']+)["']""",
        re.I,
    )

    def __init__(self, razor: Optional[RazorNgFormVisitor] = None):
        self.razor = razor or RazorNgFormVisitor()
        self.http = FrontendApiTracer()

    def parse(
        self,
        view_code: str,
        file_path: str = "",
        controller_code: str = "",
        controller_path: str = "",
    ) -> MvcUiAdapterResult:
        inspection = self.razor.parse_source(view_code or "", file_path=file_path)
        permissions = self.extract_permissions(view_code or "", source="view")
        if controller_code:
            permissions.extend(
                self.extract_permissions(controller_code, source="controller")
            )
        field_helpers = self.extract_field_helpers(view_code or "", source="view")
        if controller_code:
            field_helpers.extend(
                self.extract_field_helpers(controller_code, source="controller")
            )

        api_calls = self.http.parse_file(view_code or "", file_path or "view.cshtml")
        if controller_code:
            # Rare, but keep parity if scripts live near controller comments
            api_calls.extend(
                self.http.parse_file(
                    controller_code, controller_path or "controller.cs"
                )
            )

        # Promote JS HTTP calls into form buttons so existing consumers see actions
        self._merge_api_buttons(inspection, api_calls)
        self._merge_ng_click_buttons(inspection, view_code or "")

        return MvcUiAdapterResult(
            inspection=inspection,
            permissions=self._dedupe_permissions(permissions),
            field_helpers=self._dedupe_field_helpers(field_helpers),
            api_calls=self._dedupe_api_calls(api_calls),
        )

    def extract_permissions(
        self, code: str, source: str = "view"
    ) -> List[PermissionBinding]:
        out: List[PermissionBinding] = []
        for m in self.PERMISSION_RE.finditer(code):
            out.append(
                PermissionBinding(
                    expression=m.group(0),
                    kind="permission",
                    line_number=code[: m.start()].count("\n") + 1,
                    source=source,
                )
            )
        for m in self.CHECK_PERM_RE.finditer(code):
            out.append(
                PermissionBinding(
                    expression=m.group(0).rstrip("(").strip(),
                    kind="check_permission",
                    line_number=code[: m.start()].count("\n") + 1,
                    source=source,
                )
            )
        return out

    def extract_field_helpers(
        self, code: str, source: str = "controller"
    ) -> List[FieldHelperCall]:
        out: List[FieldHelperCall] = []
        for m in self.FIELD_HELPER_RE.finditer(code):
            start = m.start()
            line = code[:start].count("\n") + 1
            snippet = code[start : start + 80].replace("\n", " ").strip()
            out.append(
                FieldHelperCall(
                    method=m.group("method"),
                    line_number=line,
                    source=source,
                    snippet=snippet,
                )
            )
        return out

    def _merge_api_buttons(
        self, inspection: ComponentInspection, api_calls: List[FrontendApiCall]
    ) -> None:
        if not api_calls:
            return
        existing: set[Tuple[str, str]] = set()
        target_buttons = self._ensure_button_bucket(inspection)
        for b in target_buttons:
            existing.add((b.label or "", b.action_type or ""))
        for call in api_calls:
            label = f"{call.method} {call.url_normalized or call.url_raw}".strip()
            key = (label, "api")
            if key in existing:
                continue
            existing.add(key)
            target_buttons.append(
                UIButton(
                    label=label,
                    name=call.url_normalized or call.url_raw,
                    action_type="api",
                    is_submit=call.method.upper() in {"POST", "PUT", "PATCH"},
                    line_number=call.line_number,
                )
            )

    def _merge_ng_click_buttons(
        self, inspection: ComponentInspection, code: str
    ) -> None:
        target_buttons = self._ensure_button_bucket(inspection)
        existing_labels = {(b.label or "").strip() for b in target_buttons}
        for m in self.NG_CLICK_RE.finditer(code):
            expr = (m.group(1) or "").strip()
            if not expr or expr in existing_labels:
                continue
            # Skip if a button already captured nearby label-only entries
            existing_labels.add(expr)
            target_buttons.append(
                UIButton(
                    label=expr[:80],
                    name=None,
                    action_type="ng_click",
                    is_submit=False,
                    line_number=code[: m.start()].count("\n") + 1,
                )
            )

    @staticmethod
    def _ensure_button_bucket(inspection: ComponentInspection) -> List[UIButton]:
        if inspection.forms:
            return inspection.forms[0].buttons
        return inspection.standalone_buttons

    @staticmethod
    def _dedupe_permissions(
        items: List[PermissionBinding],
    ) -> List[PermissionBinding]:
        seen = set()
        out: List[PermissionBinding] = []
        for item in items:
            key = (item.expression, item.kind, item.source)
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    @staticmethod
    def _dedupe_field_helpers(
        items: List[FieldHelperCall],
    ) -> List[FieldHelperCall]:
        seen = set()
        out: List[FieldHelperCall] = []
        for item in items:
            key = (item.method, item.line_number, item.source)
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    @staticmethod
    def _dedupe_api_calls(items: List[FrontendApiCall]) -> List[FrontendApiCall]:
        seen = set()
        out: List[FrontendApiCall] = []
        for item in items:
            key = (item.method, item.url_normalized or item.url_raw, item.kind)
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out
