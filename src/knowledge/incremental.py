"""Incremental index helpers: file-hash manifest for skip-unchanged."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from src.knowledge.store import GraphStore

SOURCE_EXTS: Set[str] = {".tsx", ".ts", ".jsx", ".js", ".cs"}
IGNORE_DIRS: Set[str] = {
    "node_modules",
    ".git",
    "dist",
    "build",
    ".next",
    "bin",
    "obj",
    "__pycache__",
    ".code2guide",
    ".venv",
    "venv",
}

META_KEY = "file_hash_manifest"


def iter_source_files(workspace_path: str) -> List[Path]:
    root = Path(workspace_path)
    files: List[Path] = []
    if not root.exists():
        return files
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in SOURCE_EXTS:
            continue
        if any(part in IGNORE_DIRS for part in p.parts):
            continue
        files.append(p)
    return sorted(files)


def file_content_sha1(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_workspace_hashes(workspace_path: str) -> Dict[str, str]:
    """Return relative_path → sha1 for source files."""
    root = Path(workspace_path).resolve()
    out: Dict[str, str] = {}
    for p in iter_source_files(str(root)):
        rel = str(p.relative_to(root)).replace("\\", "/")
        try:
            out[rel] = file_content_sha1(p)
        except OSError:
            continue
    return out


class FileHashManifest:
    """Compare current workspace hashes against graph meta manifest."""

    def __init__(self, workspace_path: str, store: "GraphStore"):
        self.workspace_path = str(Path(workspace_path).resolve())
        self.store = store

    def current_hashes(self) -> Dict[str, str]:
        return scan_workspace_hashes(self.workspace_path)

    def load(self) -> Dict[str, str]:
        raw = self.store.get_meta(META_KEY, default=None)
        if isinstance(raw, dict):
            return {str(k): str(v) for k, v in raw.items()}
        return {}

    def save(self, hashes: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        hashes = hashes if hashes is not None else self.current_hashes()
        self.store.set_meta(META_KEY, hashes)
        return hashes

    def changed_files(self) -> List[str]:
        old = self.load()
        new = self.current_hashes()
        changed: List[str] = []
        all_keys = set(old) | set(new)
        for k in sorted(all_keys):
            if old.get(k) != new.get(k):
                changed.append(k)
        return changed

    def has_changes(self) -> bool:
        return bool(self.changed_files())

    def summary(self) -> Dict[str, Any]:
        changed = self.changed_files()
        return {
            "unchanged": len(changed) == 0 and bool(self.load()),
            "changed_files": changed,
            "changed_count": len(changed),
            "tracked_count": len(self.load()) or len(self.current_hashes()),
        }
