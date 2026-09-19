"""Parse ASP.NET Controllers and Minimal APIs into endpoint models."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field


class ParsedEndpoint(BaseModel):
    """A discovered HTTP endpoint from C# sources."""

    method: str = "GET"
    path: str = ""
    action_name: str = ""
    controller_name: str = ""
    file_path: str = ""
    roles: List[str] = Field(default_factory=list)
    from_body_type: Optional[str] = None
    summary: Optional[str] = None
    line_number: int = 1


class DotNetApiParser:
    """Extract HttpGet/Post/... routes and MapGet/MapPost minimal APIs."""

    HTTP_ATTRS = {
        "HttpGet": "GET",
        "HttpPost": "POST",
        "HttpPut": "PUT",
        "HttpDelete": "DELETE",
        "HttpPatch": "PATCH",
        "HttpHead": "HEAD",
        "HttpOptions": "OPTIONS",
    }

    def parse_file(self, content: str, file_path: str = "") -> List[ParsedEndpoint]:
        endpoints: List[ParsedEndpoint] = []
        endpoints.extend(self._parse_controller(content, file_path))
        endpoints.extend(self._parse_minimal_apis(content, file_path))
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
        return all_eps

    def _parse_controller(self, content: str, file_path: str) -> List[ParsedEndpoint]:
        endpoints: List[ParsedEndpoint] = []
        # Class-level route + name
        class_m = re.search(
            r"(?:\[Route\s*\(\s*[\"'](?P<route>[^\"']+)[\"']\s*\)\]\s*)?"
            r"(?:public\s+)?(?:partial\s+)?class\s+(?P<name>\w+Controller)\b",
            content,
        )
        if not class_m and "[ApiController]" not in content and "ControllerBase" not in content:
            # Still try method attributes if Controller suffix present
            if "Controller" not in content:
                return endpoints

        controller_name = class_m.group("name") if class_m else Path(file_path).stem
        class_route = (class_m.group("route") if class_m else None) or ""
        if not class_route:
            route_before = re.search(
                r'\[Route\s*\(\s*["\']([^"\']+)["\']\s*\)\]\s*(?:\[[^\]]+\]\s*)*(?:public\s+)?(?:partial\s+)?class\s+\w+Controller',
                content,
            )
            if route_before:
                class_route = route_before.group(1)

        class_route = class_route.replace("[controller]", controller_name.replace("Controller", "")).strip("/")

        # Class-level Authorize
        class_roles = self._roles_near(content, 0, 800)

        # Method blocks with Http* attributes
        for m in re.finditer(
            r"\[(?P<attr>HttpGet|HttpPost|HttpPut|HttpDelete|HttpPatch|HttpHead|HttpOptions)"
            r"(?:\s*\(\s*[\"'](?P<template>[^\"']*)[\"']\s*\))?\s*\]",
            content,
        ):
            method = self.HTTP_ATTRS[m.group("attr")]
            template = (m.group("template") or "").strip("/")
            # Find method signature after attribute cluster
            after = content[m.end() : m.end() + 500]
            # Skip other attributes
            sig = re.search(
                r"(?:public|protected|internal|private)\s+(?:async\s+)?(?:[\w.<>,\s\[\]]+?)\s+(?P<action>\w+)\s*\((?P<params>[^)]*)\)",
                after,
            )
            if not sig:
                continue
            action = sig.group("action")
            params = sig.group("params") or ""
            from_body = None
            body_m = re.search(r"\[FromBody\]\s+(?P<type>[\w.]+)\s+\w+", params)
            if body_m:
                from_body = body_m.group("type")
            else:
                # conventional: Create(TenderDto dto)
                dto_m = re.search(r"\b([A-Z][\w.]*(?:Dto|Request|Command|Model))\s+\w+", params)
                if dto_m:
                    from_body = dto_m.group(1)

            path_parts = [p for p in [class_route, template] if p]
            full_path = "/" + "/".join(path_parts) if path_parts else f"/{controller_name}/{action}"
            full_path = re.sub(r"/{2,}", "/", full_path)

            # Local authorize near method
            window_start = max(0, m.start() - 200)
            local_roles = self._roles_near(content, window_start, m.end() + 50) or class_roles

            line_number = content[: m.start()].count("\n") + 1
            endpoints.append(
                ParsedEndpoint(
                    method=method,
                    path=full_path,
                    action_name=action,
                    controller_name=controller_name,
                    file_path=file_path,
                    roles=list(local_roles),
                    from_body_type=from_body,
                    summary=f"{controller_name}.{action}",
                    line_number=line_number,
                )
            )
        return endpoints

    def _parse_minimal_apis(self, content: str, file_path: str) -> List[ParsedEndpoint]:
        endpoints: List[ParsedEndpoint] = []
        for m in re.finditer(
            r"\.(?P<map>MapGet|MapPost|MapPut|MapDelete|MapPatch)\s*\(\s*[\"'](?P<path>[^\"']+)[\"']",
            content,
        ):
            method = m.group("map").replace("Map", "").upper()
            if method == "PATCH":
                method = "PATCH"
            path = m.group("path")
            if not path.startswith("/"):
                path = "/" + path
            line_number = content[: m.start()].count("\n") + 1
            endpoints.append(
                ParsedEndpoint(
                    method=method,
                    path=path,
                    action_name=m.group("map"),
                    controller_name="MinimalApi",
                    file_path=file_path,
                    summary=f"MinimalApi {method} {path}",
                    line_number=line_number,
                )
            )
        return endpoints

    @staticmethod
    def _roles_near(content: str, start: int, end: int) -> List[str]:
        chunk = content[start:end]
        roles: List[str] = []
        for am in re.finditer(
            r'\[Authorize\s*\(\s*Roles\s*=\s*["\']([^"\']+)["\']\s*\)\]',
            chunk,
        ):
            roles.extend(r.strip() for r in am.group(1).split(",") if r.strip())
        # de-dupe
        seen = set()
        out = []
        for r in roles:
            if r not in seen:
                seen.add(r)
                out.append(r)
        return out
