"""Knowledge contract: id-keyed storage survives path rename / soft-delete."""

from __future__ import annotations

from pathlib import Path

from src.knowledge.contract import (
    ensure_id_keyed_graph_migrated,
    id_keyed_db_path,
    is_graph_tombstoned,
    legacy_path_db_path,
    resolve_collection_name,
    resolve_graph_db_path,
    set_graph_tombstone,
)
from src.knowledge.manager import get_index_manager, reset_index_managers
from src.knowledge.store import GraphStore
from src.core.config import settings


def test_resolve_prefers_id_keyed(tmp_path: Path):
    ws_path = tmp_path / "proj_a"
    ws_path.mkdir()
    index_root = tmp_path / "index"
    preferred, mode = resolve_graph_db_path(
        workspace_path=str(ws_path),
        workspace_id="ws_demo",
        index_root=str(index_root),
    )
    assert mode == "id"
    assert "ws_ws_demo" in preferred.name or preferred.name.startswith("ws_")


def test_legacy_dual_read_then_migrate(tmp_path: Path):
    ws_path = tmp_path / "proj_b"
    ws_path.mkdir()
    index_root = tmp_path / "index"
    legacy = legacy_path_db_path(str(ws_path), index_root=str(index_root))
    legacy.parent.mkdir(parents=True, exist_ok=True)
    store = GraphStore(str(ws_path), db_path=legacy)
    store.set_meta("marker", "legacy")
    store.close()

    info = ensure_id_keyed_graph_migrated(
        workspace_id="ws_b",
        workspace_path=str(ws_path),
        index_root=str(index_root),
    )
    assert info["copied"] is True
    preferred = id_keyed_db_path("ws_b", index_root=str(index_root))
    assert preferred.exists()
    path, mode = resolve_graph_db_path(
        workspace_path=str(ws_path),
        workspace_id="ws_b",
        index_root=str(index_root),
    )
    assert mode == "id"
    assert path == preferred


def test_rename_keeps_same_manager_cache(tmp_path: Path):
    reset_index_managers()
    a = tmp_path / "old_name"
    b = tmp_path / "new_name"
    a.mkdir()
    index_root = tmp_path / "idx"
    old = getattr(settings, "index_storage_path", None)
    try:
        settings.index_storage_path = str(index_root)
        m1 = get_index_manager(str(a), workspace_id="ws_rename")
        db1 = m1.graph_store.db_path
        a.rename(b)
        m2 = get_index_manager(str(b), workspace_id="ws_rename")
        assert m1 is m2
        assert m2.graph_store.db_path == db1
        assert Path(m2.workspace_path) == b.resolve()
    finally:
        settings.index_storage_path = old
        reset_index_managers()


def test_tombstone_meta(tmp_path: Path):
    ws = tmp_path / "t"
    ws.mkdir()
    db = tmp_path / "g.db"
    store = GraphStore(str(ws), db_path=db)
    set_graph_tombstone(store, deleted=True)
    assert is_graph_tombstoned(store) is True
    set_graph_tombstone(store, deleted=False)
    assert is_graph_tombstoned(store) is False
    store.close()


def test_collection_name_id_keyed():
    name, mode = resolve_collection_name(
        workspace_path="/tmp/x",
        workspace_id="ws_c",
    )
    assert mode == "id"
    assert "ws_c" in name
