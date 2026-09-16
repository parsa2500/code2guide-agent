"""OpenAPI/Swagger and frontend RBAC permissions extractor."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class EndpointRequirement(BaseModel):
    """A backend or documented API endpoint with optional role requirements."""

    path: str
    method: str
    roles_required: List[str] = Field(default_factory=list)
    request_dto_fields: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    source: str = Field(default="openapi")


class PermissionBinding(BaseModel):
    """Maps a UI page/route id to a permission string."""

    page_id: str
    permission: str
    permission_const: Optional[str] = None
    source_file: Optional[str] = None


class BackendContractExtractor:
    """Extracts OpenAPI contracts, C# Authorize roles, and frontend Permissions bindings."""

    SKIP_DIR_NAMES = {
        "node_modules",
        ".git",
        ".next",
        "dist",
        "build",
        ".venv",
        "venv",
        "coverage",
    }

    def __init__(self, workspace_path: str):
        self.workspace_root = Path(workspace_path).resolve()
        self._permission_constants: Dict[str, str] = {}
        self._page_permissions: List[PermissionBinding] = []
        self._endpoints: Optional[List[EndpointRequirement]] = None

    def scan_rbac_and_swagger(self) -> List[EndpointRequirement]:
        if self._endpoints is not None:
            return self._endpoints

        requirements: List[EndpointRequirement] = []
        requirements.extend(self._scan_openapi_files())
        requirements.extend(self._scan_csharp_authorize())
        self._load_frontend_permissions()
        self._endpoints = requirements
        return requirements

    def get_permission_constants(self) -> Dict[str, str]:
        self._load_frontend_permissions()
        return dict(self._permission_constants)

    def get_page_permissions(self) -> List[PermissionBinding]:
        self._load_frontend_permissions()
        return list(self._page_permissions)

    def roles_for_page_id(self, page_id: str) -> List[str]:
        """Resolve required permission strings for a PageId or path segment."""
        self._load_frontend_permissions()
        clean = page_id.lstrip("/").strip()
        roles: List[str] = []
        for binding in self._page_permissions:
            if binding.page_id == clean:
                roles.append(binding.permission)
        return roles

    def _iter_files(self, suffixes: tuple) -> List[Path]:
        found: List[Path] = []
        for root, dirnames, filenames in os.walk(self.workspace_root):
            dirnames[:] = [d for d in dirnames if d not in self.SKIP_DIR_NAMES]
            for name in filenames:
                if name.lower().endswith(suffixes):
                    found.append(Path(root) / name)
        return found

    def _scan_openapi_files(self) -> List[EndpointRequirement]:
        requirements: List[EndpointRequirement] = []
        for path in self._iter_files((".json",)):
            lower = path.name.lower()
            if "swagger" not in lower and "openapi" not in lower:
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            if not isinstance(data, dict) or "paths" not in data:
                continue

            for url, methods in (data.get("paths") or {}).items():
                if not isinstance(methods, dict):
                    continue
                for method, details in methods.items():
                    if method.lower() in ("parameters", "summary", "description", "servers"):
                        continue
                    if not isinstance(details, dict):
                        continue
                    roles = self._extract_roles_from_operation(details, data)
                    dto_fields = self._extract_request_fields(details, data)
                    requirements.append(
                        EndpointRequirement(
                            path=str(url),
                            method=str(method).upper(),
                            roles_required=roles,
                            request_dto_fields=dto_fields,
                            summary=details.get("summary") or details.get("operationId"),
                            source=str(path.relative_to(self.workspace_root)).replace("\\", "/"),
                        )
                    )
        return requirements

    def _extract_roles_from_operation(self, details: dict, root: dict) -> List[str]:
        roles: List[str] = []
        security = details.get("security")
        if security is None:
            security = root.get("security")
        if not security:
            return roles
        for item in security:
            if isinstance(item, dict):
                for scheme, scopes in item.items():
                    if scopes:
                        roles.extend(str(s) for s in scopes)
                    else:
                        roles.append(str(scheme))
            else:
                roles.append(str(item))
        # de-dupe preserve order
        seen = set()
        out = []
        for r in roles:
            if r not in seen:
                seen.add(r)
                out.append(r)
        return out

    def _extract_request_fields(self, details: dict, root: dict) -> List[str]:
        fields: List[str] = []
        body = (details.get("requestBody") or {}).get("content") or {}
        for _mime, schema_wrap in body.items():
            schema = (schema_wrap or {}).get("schema") or {}
            fields.extend(self._schema_property_names(schema, root))
        return fields[:40]

    def _schema_property_names(self, schema: dict, root: dict, depth: int = 0) -> List[str]:
        if depth > 4 or not isinstance(schema, dict):
            return []
        if "$ref" in schema:
            ref = schema["$ref"]
            name = ref.split("/")[-1]
            components = (root.get("components") or {}).get("schemas") or {}
            return self._schema_property_names(components.get(name, {}), root, depth + 1)
        props = schema.get("properties") or {}
        names = list(props.keys())
        for key in ("allOf", "oneOf", "anyOf"):
            for sub in schema.get(key) or []:
                names.extend(self._schema_property_names(sub, root, depth + 1))
        return names

    def _scan_csharp_authorize(self) -> List[EndpointRequirement]:
        requirements: List[EndpointRequirement] = []
        for cs_file in self._iter_files((".cs",)):
            try:
                content = cs_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for am in re.finditer(
                r'\[Authorize\s*\(\s*Roles\s*=\s*["\']([^"\']+)["\']\s*\)\]',
                content,
            ):
                roles = [r.strip() for r in am.group(1).split(",") if r.strip()]
                requirements.append(
                    EndpointRequirement(
                        path=cs_file.stem,
                        method="BACKEND_ROLE",
                        roles_required=roles,
                        source=str(cs_file.relative_to(self.workspace_root)).replace("\\", "/"),
                    )
                )
        return requirements

    def _load_frontend_permissions(self) -> None:
        if self._page_permissions:
            return

        # Pass 1: permission constant maps (prefer *permission* files first)
        ts_files = self._iter_files((".ts", ".tsx", ".js", ".jsx"))
        ts_files.sort(
            key=lambda p: (0 if "permission" in p.name.lower() else 1, str(p).lower())
        )

        for path in ts_files:
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if "Permissions" not in content and "permission" not in path.name.lower():
                continue
            for m in re.finditer(
                r"""(?P<const>[A-Za-z_][\w]*)\s*:\s*["'](?P<val>admin\.[^"']+)["']""",
                content,
            ):
                self._permission_constants[m.group("const")] = m.group("val")

        # Pass 2: page id → Permissions.Const within the same object literal
        for path in ts_files:
            rel = str(path.relative_to(self.workspace_root)).replace("\\", "/")
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if "requiredPermission" not in content:
                continue

            for block in re.finditer(r"\{[^{}]*\}", content, re.MULTILINE | re.DOTALL):
                obj = block.group(0)
                if "requiredPermission" not in obj or "id" not in obj:
                    continue
                id_m = re.search(r"""\bid\s*:\s*["']([^"']+)["']""", obj)
                perm_m = re.search(
                    r"""requiredPermission\s*:\s*Permissions\.([A-Za-z_][\w]*)""",
                    obj,
                )
                if not id_m or not perm_m:
                    continue
                page_id = id_m.group(1)
                if any(b.page_id == page_id for b in self._page_permissions):
                    continue
                const = perm_m.group(1)
                perm = self._permission_constants.get(const, f"Permissions.{const}")
                self._page_permissions.append(
                    PermissionBinding(
                        page_id=page_id,
                        permission=perm,
                        permission_const=const,
                        source_file=rel,
                    )
                )
