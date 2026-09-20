"""Knowledge identity contract: workspace_id + revision_id (path is mutable metadata only)."""

from __future__ import annotations

import hashlib
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def sanitize_workspace_id(workspace_id: str) -> str:
    wid = (workspace_id or "").strip()
    if not wid:
        raise ValueError("workspace_id must not be empty")
    return re.sub(r"[^a-zA-Z0-9_-]", "_", wid)[:128]


def workspace_path_hash(workspace_path: str) -> str:
    resolved = str(Path(workspace_path).resolve())
    return hashlib.sha1(resolved.encode("utf-8")).hexdigest()[:12]


def index_root_path(index_root: Optional[str] = None) -> Path:
    root = Path(index_root) if index_root else Path(".code2guide") / "index"
    root.mkdir(parents=True, exist_ok=True)
    return root


def id_keyed_db_path(
    workspace_id: str,
    *,
    revision_id: Optional[str] = None,
    index_root: Optional[str] = None,
) -> Path:
    root = index_root_path(index_root)
    wid = sanitize_workspace_id(workspace_id)
    if revision_id:
        rev = sanitize_workspace_id(revision_id)
        return root / f"ws_{wid}__rev_{rev}.db"
    return root / f"ws_{wid}.db"


def legacy_path_db_path(workspace_path: str, index_root: Optional[str] = None) -> Path:
    root = index_root_path(index_root)
    return root / f"{workspace_path_hash(workspace_path)}.db"


def resolve_graph_db_path(
    *,
    workspace_path: str,
    workspace_id: Optional[str] = None,
    revision_id: Optional[str] = None,
    index_root: Optional[str] = None,
) -> Tuple[Path, str]:
    """Prefer id-keyed DB; fall back to legacy path-hash for dual-read migration."""
    legacy = legacy_path_db_path(workspace_path, index_root=index_root)
    if workspace_id:
        preferred = id_keyed_db_path(
            workspace_id, revision_id=revision_id, index_root=index_root
        )
        if preferred.exists():
            return preferred, "id"
        if legacy.exists():
            return legacy, "legacy"
        return preferred, "id"
    return legacy, "legacy"


def collection_name_for_workspace_id(
    workspace_id: str,
    *,
    revision_id: Optional[str] = None,
    prefix: str = "code2guide",
) -> str:
    wid = sanitize_workspace_id(workspace_id)
    safe_prefix = re.sub(r"[^a-zA-Z0-9_]", "_", prefix)[:32]
    if revision_id:
        rev = sanitize_workspace_id(revision_id)
        return f"{safe_prefix}_ws_{wid}_rev_{rev}"[:255]
    return f"{safe_prefix}_ws_{wid}"[:255]


def legacy_collection_name_for_path(workspace_path: str, prefix: str = "code2guide") -> str:
    digest = workspace_path_hash(workspace_path)
    safe_prefix = re.sub(r"[^a-zA-Z0-9_]", "_", prefix)[:32]
    return f"{safe_prefix}_{digest}"


def resolve_collection_name(
    *,
    workspace_path: str,
    workspace_id: Optional[str] = None,
    revision_id: Optional[str] = None,
    prefix: str = "code2guide",
) -> Tuple[str, str]:
    """Return (collection_name, mode) with id preference."""
    if workspace_id:
        return (
            collection_name_for_workspace_id(
                workspace_id, revision_id=revision_id, prefix=prefix
            ),
            "id",
        )
    return legacy_collection_name_for_path(workspace_path, prefix=prefix), "legacy"


def ensure_id_keyed_graph_migrated(
    *,
    workspace_id: str,
    workspace_path: str,
    index_root: Optional[str] = None,
    revision_id: str = "revision_0",
) -> Dict[str, Any]:
    """Copy legacy path-hash DB to id-keyed path once; leave legacy in place for dual-read."""
    preferred = id_keyed_db_path(
        workspace_id, revision_id=None, index_root=index_root
    )
    legacy = legacy_path_db_path(workspace_path, index_root=index_root)
    info: Dict[str, Any] = {
        "workspace_id": workspace_id,
        "preferred": str(preferred),
        "legacy": str(legacy),
        "copied": False,
        "revision_id": revision_id,
    }
    if preferred.exists():
        info["status"] = "already_id_keyed"
        return info
    if legacy.exists():
        preferred.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy, preferred)
        info["copied"] = True
        info["status"] = "migrated_from_legacy"
        info["migrated_at"] = time.time()
        return info
    info["status"] = "no_legacy"
    return info


def new_revision_id(manifest_hash: Optional[str] = None) -> str:
    stamp = int(time.time())
    if manifest_hash:
        return f"rev_{manifest_hash[:10]}_{stamp}"
    return f"rev_{stamp}"


def set_graph_tombstone(store: Any, *, deleted: bool = True) -> None:
    """Soft-delete marker on graph meta; does not remove DB or collection files."""
    store.set_meta("tombstone", bool(deleted))
    if deleted:
        store.set_meta("tombstoned_at", time.time())
    else:
        store.set_meta("tombstoned_at", None)


def clear_graph_tombstone(store: Any) -> None:
    set_graph_tombstone(store, deleted=False)


def is_graph_tombstoned(store: Any) -> bool:
    val = store.get_meta("tombstone")
    return val is True or val == "true" or val == 1 or val == "1"
