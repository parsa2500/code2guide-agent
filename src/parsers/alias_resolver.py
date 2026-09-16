"""TypeScript and JavaScript path alias resolver for tsconfig/jsconfig."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Optional


class PathAliasResolver:
    """Resolves `@/` / configured path aliases and relative imports to real files."""

    def __init__(self, workspace_path: str):
        self.workspace_root = Path(workspace_path).resolve()
        self.aliases: Dict[str, str] = {}
        self._load_configs()

    def _strip_comments(self, json_str: str) -> str:
        # Remove // and /* */ comments commonly found in tsconfig
        no_block = re.sub(r"/\*.*?\*/", "", json_str, flags=re.DOTALL)
        return re.sub(r"//.*?$", "", no_block, flags=re.MULTILINE)

    def _load_configs(self) -> None:
        for config_name in ("tsconfig.json", "tsconfig.app.json", "jsconfig.json"):
            config_file = self.workspace_root / config_name
            if not config_file.is_file():
                continue
            try:
                raw = self._strip_comments(config_file.read_text(encoding="utf-8"))
                data = json.loads(raw)
            except Exception:
                continue

            compiler = data.get("compilerOptions") or {}
            paths = compiler.get("paths") or {}
            base_url = compiler.get("baseUrl", ".")
            base_dir = (self.workspace_root / base_url).resolve()

            for alias_key, target_list in paths.items():
                if not target_list:
                    continue
                clean_alias = alias_key.replace("/*", "").rstrip("/")
                clean_target = str(target_list[0]).replace("/*", "").rstrip("/")
                resolved_target = (base_dir / clean_target).resolve()
                self.aliases[clean_alias] = str(resolved_target)

    def resolve_import(self, import_str: str, from_file: Path) -> Optional[Path]:
        """Resolve an import string relative to from_file into an existing Path."""
        if not import_str:
            return None

        # 1. Configured aliases (@, ~, etc.)
        for alias, target_dir in sorted(self.aliases.items(), key=lambda x: -len(x[0])):
            if import_str == alias or import_str.startswith(alias + "/"):
                rel_suffix = import_str[len(alias):].lstrip("/\\")
                cand_base = Path(target_dir) / rel_suffix
                return self._check_extensions(cand_base)

        # 2. Relative imports
        if import_str.startswith("."):
            cand_base = (from_file.parent / import_str).resolve()
            return self._check_extensions(cand_base)

        return None

    def resolve_to_relative(self, import_str: str, from_file: Path) -> Optional[str]:
        """Resolve import and return path relative to workspace root (POSIX)."""
        resolved = self.resolve_import(import_str, from_file)
        if resolved is None:
            return None
        try:
            return str(resolved.relative_to(self.workspace_root)).replace("\\", "/")
        except ValueError:
            return str(resolved).replace("\\", "/")

    def _check_extensions(self, base_path: Path) -> Optional[Path]:
        if base_path.is_file():
            return base_path
        candidates = [
            Path(str(base_path) + ".tsx"),
            Path(str(base_path) + ".jsx"),
            Path(str(base_path) + ".ts"),
            Path(str(base_path) + ".js"),
            base_path / "index.tsx",
            base_path / "index.jsx",
            base_path / "index.ts",
            base_path / "index.js",
        ]
        for p in candidates:
            if p.is_file():
                return p
        return None
