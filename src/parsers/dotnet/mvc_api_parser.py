"""Parse ASP.NET MVC Framework controllers and OData endpoints."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from src.parsers.dotnet.api_parser import ParsedEndpoint


class MvcApiParser:
    """Extract conventional MVC actions, Http* actions, PartialView links, and OData sets."""

    ACTION_RETURN_TYPES = (
        "ActionResult",
        "JsonResult",
        "PartialViewResult",
        "ViewResult",
        "ContentResult",
        "FileResult",
        "RedirectResult",
        "RedirectToRouteResult",
        "HttpResponseMessage",
        "IHttpActionResult",
        "IQueryable",
        "Task<ActionResult>",
        "Task<JsonResult>",
        "Task<PartialViewResult>",
    )

    HTTP_ATTRS = {
        "HttpGet": "GET",
        "HttpPost": "POST",
        "HttpPut": "PUT",
        "HttpDelete": "DELETE",
        "HttpPatch": "PATCH",
    }

    def parse_file(self, content: str, file_path: str = "") -> List[ParsedEndpoint]:
        endpoints: List[ParsedEndpoint] = []
        endpoints.extend(self._parse_mvc_controller(content, file_path))
        endpoints.extend(self._parse_odata_controller(content, file_path))
        endpoints.extend(self._parse_odata_entity_sets(content, file_path))
        return endpoints

    def parse_paths(self, paths: List[Path], workspace_root: Path) -> List[ParsedEndpoint]:
        all_eps: List[ParsedEndpoint] = []
        for path in paths:
            try:
                content = path.read_text(encoding="utf-8-sig", errors="replace")
            except Exception:
                continue
            try:
                rel = str(path.relative_to(workspace_root)).replace("\\", "/")
            except ValueError:
                rel = str(path).replace("\\", "/")
            all_eps.extend(self.parse_file(content, rel))
        return self._dedupe(all_eps)

    def _parse_mvc_controller(self, content: str, file_path: str) -> List[ParsedEndpoint]:
        endpoints: List[ParsedEndpoint] = []
        # Skip pure OData controllers here (handled separately)
        if re.search(r":\s*ODataController\b", content) and "ControllerBase" not in content:
            if "System.Web.Mvc" not in content and "PartialView" not in content:
                return endpoints

        class_m = re.search(
            r"(?:public\s+|internal\s+)?(?:partial\s+)?class\s+(?P<name>\w+Controller)\b"
            r"(?:\s*:\s*(?P<bases>[^{\n]+))?",
            content,
        )
        if not class_m:
            return endpoints

        controller_name = class_m.group("name")
        bases = class_m.group("bases") or ""
        # Prefer MVC / BaseController; skip ApiController-only Web API unless also MVC
        is_mvc = bool(
            re.search(r"\b(Controller|BaseController)\b", bases)
            or "System.Web.Mvc" in content
            or "PartialView" in content
            or "ActionResult" in content
        )
        if not is_mvc and "ApiController" in bases:
            return endpoints

        short = controller_name.replace("Controller", "") if controller_name.endswith("Controller") else controller_name

        # Collect Http* attribute positions for method override
        http_overrides: Dict[int, Tuple[str, str]] = {}
        for m in re.finditer(
            r"\[(?P<attr>HttpGet|HttpPost|HttpPut|HttpDelete|HttpPatch)"
            r"(?:\s*\(\s*[\"'](?P<template>[^\"']*)[\"']\s*\))?\s*\]",
            content,
        ):
            method = self.HTTP_ATTRS[m.group("attr")]
            template = (m.group("template") or "").strip("/")
            http_overrides[m.start()] = (method, template)

        action_re = re.compile(
            r"(?P<attrs>(?:\[[^\]]+\]\s*)*)"
            r"(?:public|protected|internal)\s+(?:async\s+)?"
            r"(?:[\w.<>,\s\[\]]+?)\s+(?P<action>\w+)\s*\((?P<params>[^)]*)\)",
            re.MULTILINE,
        )

        seen_actions: Set[str] = set()
        for m in action_re.finditer(content):
            action = m.group("action")
            if action in (
                "Dispose",
                "ToString",
                "Equals",
                "GetHashCode",
                "GetType",
                "MemberwiseClone",
                "Finalize",
            ):
                continue
            # Skip constructors
            if action == controller_name or action == short + "Controller":
                continue

            attrs = m.group("attrs") or ""
            params = m.group("params") or ""
            ret_window = content[max(0, m.start() - 80) : m.start()]
            # Must look like an action return type or have Http* / ActionResult nearby
            has_action_shape = bool(
                re.search(
                    r"\b(ActionResult|JsonResult|PartialViewResult|ViewResult|ContentResult|"
                    r"FileResult|IHttpActionResult|HttpResponseMessage|IQueryable)\b",
                    ret_window + attrs + content[m.start() : m.end()],
                )
                or re.search(r"\[Http(Get|Post|Put|Delete|Patch)\]", attrs)
            )
            if not has_action_shape:
                continue

            method = "GET"
            template = ""
            # Find nearest Http* attribute before this method
            nearest_http = None
            for pos, (hm, ht) in http_overrides.items():
                if pos < m.start() and m.start() - pos < 400:
                    if nearest_http is None or pos > nearest_http[0]:
                        nearest_http = (pos, hm, ht)
            if nearest_http:
                method = nearest_http[1]
                template = nearest_http[2]
            elif re.search(r"\[HttpPost\]", attrs):
                method = "POST"
            elif re.search(r"\[HttpPut\]", attrs):
                method = "PUT"
            elif re.search(r"\[HttpDelete\]", attrs):
                method = "DELETE"
            elif re.search(r"\[HttpPatch\]", attrs):
                method = "PATCH"
            elif re.search(r"\[HttpGet\]", attrs):
                method = "GET"

            path_parts = [p for p in [short, template or action] if p]
            full_path = "/" + "/".join(path_parts)
            full_path = re.sub(r"/{2,}", "/", full_path)

            from_body = None
            body_m = re.search(r"\[FromBody\]\s+(?P<type>[\w.]+)\s+\w+", params)
            if body_m:
                from_body = body_m.group("type")
            else:
                dto_m = re.search(r"\b([A-Z][\w.]*(?:Dto|Request|Command|Model|VM))\s+\w+", params)
                if dto_m:
                    from_body = dto_m.group(1)

            # PartialView path metadata in summary
            body_after = content[m.end() : m.end() + 600]
            pv = re.search(r'PartialView\s*\(\s*["\']([^"\']+)["\']', body_after)
            view_hint = pv.group(1) if pv else None

            key = f"{method}:{full_path}:{action}"
            if key in seen_actions:
                continue
            seen_actions.add(key)

            line_number = content[: m.start()].count("\n") + 1
            summary = f"{controller_name}.{action}"
            if view_hint:
                summary = f"{summary} → {view_hint}"

            endpoints.append(
                ParsedEndpoint(
                    method=method,
                    path=full_path,
                    action_name=action,
                    controller_name=controller_name,
                    file_path=file_path,
                    from_body_type=from_body,
                    summary=summary,
                    line_number=line_number,
                )
            )
        return endpoints

    def _parse_odata_controller(self, content: str, file_path: str) -> List[ParsedEndpoint]:
        endpoints: List[ParsedEndpoint] = []
        if "ODataController" not in content:
            return endpoints

        class_m = re.search(
            r"(?:public\s+|internal\s+)?(?:partial\s+)?class\s+(?P<name>\w+)\b",
            content,
        )
        if not class_m:
            return endpoints
        controller_name = class_m.group("name")
        # OData entity set name often matches controller without Controller suffix, lowercased
        set_name = controller_name
        if set_name.endswith("Controller"):
            set_name = set_name[: -len("Controller")]
        set_name = set_name[0].lower() + set_name[1:] if set_name else set_name

        for m in re.finditer(
            r"(?:public|protected|internal)\s+(?:async\s+)?"
            r"(?:[\w.<>,\s\[\]]+?)\s+(?P<action>Get\w*|Post|Put|Patch|Delete|Create|Update)\s*\(",
            content,
        ):
            action = m.group("action")
            method = "GET"
            if action.lower().startswith("post") or action in ("Create", "Post"):
                method = "POST"
            elif action.lower().startswith("put") or action == "Update":
                method = "PUT"
            elif action.lower().startswith("delete"):
                method = "DELETE"
            elif action.lower().startswith("patch"):
                method = "PATCH"

            path = f"/odata/{set_name}"
            if action.lower().startswith("get") and action != "Get" and not action.startswith("Get" + set_name[:1].upper()):
                # e.g. GetContracts → collection GET
                pass

            line_number = content[: m.start()].count("\n") + 1
            endpoints.append(
                ParsedEndpoint(
                    method=method,
                    path=path,
                    action_name=action,
                    controller_name=controller_name,
                    file_path=file_path,
                    summary=f"OData {controller_name}.{action}",
                    line_number=line_number,
                )
            )
        return endpoints

    def _parse_odata_entity_sets(self, content: str, file_path: str) -> List[ParsedEndpoint]:
        endpoints: List[ParsedEndpoint] = []
        prefix = "odata"
        prefix_m = re.search(
            r'MapODataServiceRoute\s*\([^)]*routePrefix\s*:\s*["\'](?P<pre>[^"\']+)["\']',
            content,
        )
        if prefix_m:
            prefix = prefix_m.group("pre").strip("/")

        for m in re.finditer(
            r'EntitySet\s*<\s*[\w.]+\s*>\s*\(\s*["\'](?P<name>[^"\']+)["\']\s*\)',
            content,
        ):
            name = m.group("name")
            path = f"/{prefix}/{name}"
            path = re.sub(r"/{2,}", "/", path)
            line_number = content[: m.start()].count("\n") + 1
            endpoints.append(
                ParsedEndpoint(
                    method="GET",
                    path=path,
                    action_name=f"Get{name}",
                    controller_name="OData",
                    file_path=file_path,
                    summary=f"OData EntitySet {name}",
                    line_number=line_number,
                )
            )
            endpoints.append(
                ParsedEndpoint(
                    method="POST",
                    path=path,
                    action_name=f"Post{name}",
                    controller_name="OData",
                    file_path=file_path,
                    summary=f"OData EntitySet {name} POST",
                    line_number=line_number,
                )
            )
        return endpoints

    @staticmethod
    def _dedupe(endpoints: List[ParsedEndpoint]) -> List[ParsedEndpoint]:
        seen: Set[Tuple[str, str, str, str]] = set()
        out: List[ParsedEndpoint] = []
        for ep in endpoints:
            key = (ep.method.upper(), ep.path, ep.file_path, ep.action_name)
            if key in seen:
                continue
            seen.add(key)
            out.append(ep)
        return out
