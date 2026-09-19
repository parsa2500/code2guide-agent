"""i18n translation dictionary parser for Persian locales and panel pageLabels."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional


class I18nParser:
    """Loads fa locale JSON / t() keys and panel-style pageLabels from i18n.ts."""

    SKIP_DIR_PARTS = ("node_modules", ".git", ".next", "dist", "build", ".venv", "venv")

    def __init__(self, workspace_path: str):
        self.workspace_root = Path(workspace_path).resolve()
        self.translations: Dict[str, str] = {}
        self.page_labels: Dict[str, str] = {}
        self.scan_locales()
        self.scan_page_labels_ts()

    def scan_locales(self) -> None:
        """Load Persian locale JSON files into a flat key → text map."""
        for root, dirnames, files in os.walk(self.workspace_root):
            dirnames[:] = [d for d in dirnames if d not in self.SKIP_DIR_PARTS]
            norm = root.replace("\\", "/")
            if any(p in norm for p in self.SKIP_DIR_PARTS):
                continue
            for f in files:
                lower = f.lower()
                if not lower.endswith(".json"):
                    continue
                if not ("fa" in lower or "persian" in lower or "/fa/" in norm.lower() or "\\fa\\" in root.lower()):
                    # also accept locales/fa/*.json via parent folder name
                    parent = Path(root).name.lower()
                    if parent not in ("fa", "persian", "fa-ir", "fa_ir"):
                        continue
                full_path = Path(root) / f
                try:
                    data = json.loads(full_path.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        self._flatten_dict(data)
                except Exception:
                    continue

    def scan_page_labels_ts(self) -> None:
        """Parse `pageLabels: Record<PageId, Record<Language, string>>` from i18n.ts."""
        candidates = [
            self.workspace_root / "src" / "config" / "i18n.ts",
            self.workspace_root / "src" / "i18n.ts",
            self.workspace_root / "src" / "locales" / "i18n.ts",
        ]
        for path in candidates:
            if not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            # pageId: { fa: "...", en: "..." }
            for m in re.finditer(
                r'["\']?(?P<id>[A-Za-z0-9_-]+)["\']?\s*:\s*\{\s*fa\s*:\s*["\'](?P<fa>[^"\']+)["\']',
                content,
            ):
                page_id = m.group("id")
                fa = m.group("fa")
                self.page_labels[page_id] = fa
                self.translations[f"page.{page_id}"] = fa

    def _flatten_dict(self, d: Dict[str, Any], prefix: str = "") -> None:
        for k, v in d.items():
            full_key = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, dict):
                self._flatten_dict(v, full_key)
            elif isinstance(v, str):
                self.translations[full_key] = v

    def resolve_key(self, key: str) -> Optional[str]:
        if key in self.translations:
            return self.translations[key]
        if key in self.page_labels:
            return self.page_labels[key]
        return None

    def label_for_page_id(self, page_id: str) -> Optional[str]:
        clean = page_id.lstrip("/")
        return self.page_labels.get(clean) or self.translations.get(f"page.{clean}")

    def replace_i18n_calls(self, code: str) -> str:
        """Replace t('key') / t(\"key\") with resolved Persian string literals for AST analysis."""

        def _sub(match: re.Match) -> str:
            key = match.group(1)
            val = self.resolve_key(key)
            text = val if val else key
            escaped = text.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'

        return re.sub(r"""\bt\(\s*['"]([^'"]+)['"]\s*\)""", _sub, code)
