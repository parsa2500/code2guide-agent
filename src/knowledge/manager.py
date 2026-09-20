"""Process-level workspace index manager (shared graph + hybrid indexer)."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Dict, Optional, TYPE_CHECKING

from src.core.config import settings
from src.knowledge.contract import ensure_id_keyed_graph_migrated, set_graph_tombstone
from src.knowledge.store import GraphStore, default_db_path
from src.search.hybrid_indexer import HybridIndexer, collection_name_for_workspace

if TYPE_CHECKING:
    from src.agent.tools import Code2GuideToolbox
    from src.knowledge.indexer import IndexResult


_lock = threading.Lock()
_managers: Dict[str, "WorkspaceIndexManager"] = {}


class WorkspaceIndexManager:
    """Holds persistent graph store + hybrid indexer for one workspace."""

    def __init__(
        self,
        workspace_path: str,
        hybrid_indexer: Optional[HybridIndexer] = None,
        graph_store: Optional[GraphStore] = None,
        *,
        workspace_id: Optional[str] = None,
        revision_id: Optional[str] = None,
    ):
        self.workspace_path = str(Path(workspace_path).resolve())
        self.workspace_id = workspace_id
        self.revision_id = revision_id
        index_root = getattr(settings, "index_storage_path", None) or ".code2guide/index"

        if workspace_id:
            ensure_id_keyed_graph_migrated(
                workspace_id=workspace_id,
                workspace_path=self.workspace_path,
                index_root=index_root,
                revision_id=revision_id or "revision_0",
            )

        db_path = default_db_path(
            self.workspace_path,
            index_root=index_root,
            workspace_id=workspace_id,
            revision_id=None,
        )
        self.graph_store = graph_store or GraphStore(
            self.workspace_path,
            db_path=db_path,
            workspace_id=workspace_id,
            revision_id=revision_id,
            index_root=index_root,
        )
        self.hybrid_indexer = hybrid_indexer or HybridIndexer(
            collection_name=collection_name_for_workspace(
                self.workspace_path,
                workspace_id=workspace_id,
                revision_id=revision_id,
            ),
        )
        self._last_result: Optional[Dict] = None

    @property
    def is_indexed(self) -> bool:
        status = self.graph_store.status()
        return bool(status.get("exists"))

    def status(self) -> Dict:
        st = self.graph_store.status()
        st["use_vector"] = bool(self.hybrid_indexer.use_vector)
        st["collection_name"] = self.hybrid_indexer.collection_name
        st["workspace_id"] = self.workspace_id
        st["revision_id"] = self.revision_id or self.graph_store.get_meta("revision_id")
        st["storage_mode"] = getattr(self.graph_store, "storage_mode", None)
        if self._last_result:
            st["last_result"] = self._last_result
        return st

    def mark_tombstone(self, deleted: bool = True) -> None:
        """Soft-delete: keep graph/vector files; stamp tombstone meta."""
        set_graph_tombstone(self.graph_store, deleted=deleted)

    def attach_toolbox(self, toolbox: "Code2GuideToolbox") -> "Code2GuideToolbox":
        """Point toolbox at this manager's hybrid indexer and mark indexed if graph exists."""
        toolbox.hybrid_indexer = self.hybrid_indexer
        toolbox._graph_store = self.graph_store
        toolbox._index_manager = self
        if self.workspace_id:
            toolbox.workspace_id = self.workspace_id
        if self.is_indexed:
            # Rebuild in-memory fallback from graph so /ask works without Qdrant
            from src.knowledge.indexer import FrontendIndexer

            # Prefer loading hybrid from prior index_items kept in fallback;
            # if empty, mark so ensure_indexed triggers a reindex.
            if self.hybrid_indexer._fallback_indexer.items:
                toolbox._indexed = True
            else:
                toolbox._indexed = False
        return toolbox

    def index_workspace(self, toolbox: "Code2GuideToolbox", *, rebuild: bool = True) -> "IndexResult":
        from src.knowledge.indexer import FrontendIndexer, IndexResult
        from src.knowledge.backend_indexer import BackendIndexer
        from src.knowledge.flow_tracer import FlowIndexer
        from src.knowledge.incremental import FileHashManifest

        toolbox.hybrid_indexer = self.hybrid_indexer
        toolbox._graph_store = self.graph_store
        toolbox._index_manager = self

        manifest = FileHashManifest(self.workspace_path, self.graph_store)

        # Skip-unchanged: only when rebuild=False and graph already exists with identical hashes
        if not rebuild and self.is_indexed:
            summary = manifest.summary()
            if summary.get("unchanged") and not summary.get("changed_files"):
                prev = dict(self._last_result or self.graph_store.get_meta("stats") or {})
                result = IndexResult(
                    workspace_path=self.workspace_path,
                    duration_ms=0.0,
                    routes=int(prev.get("routes") or 0),
                    components=int(prev.get("components") or 0),
                    forms=int(prev.get("forms") or 0),
                    form_fields=int(prev.get("form_fields") or 0),
                    ui_buttons=int(prev.get("ui_buttons") or 0),
                    i18n_strings=int(prev.get("i18n_strings") or 0),
                    ui_texts=int(prev.get("ui_texts") or 0),
                    edges=int(prev.get("edges") or 0),
                    indexed_count=int(prev.get("indexed_count") or 0),
                    use_vector=bool(self.hybrid_indexer.use_vector),
                    collection_name=self.hybrid_indexer.collection_name,
                    files_inspected=0,
                    db_path=str(self.graph_store.db_path),
                    api_endpoints=int(prev.get("api_endpoints") or 0),
                    services=int(prev.get("services") or 0),
                    entities=int(prev.get("entities") or 0),
                    tables=int(prev.get("tables") or 0),
                    api_calls=int(prev.get("api_calls") or 0),
                    field_mappings=int(prev.get("field_mappings") or 0),
                    skipped_unchanged=True,
                    changed_files=[],
                    stats={"skipped_unchanged": True, "incremental": summary},
                )
                self._last_result = result.to_dict()
                toolbox._indexed = True
                return result

        # Any change (or rebuild) → full reindex of current pipeline
        changed = [] if rebuild else manifest.changed_files()

        fe = FrontendIndexer(toolbox, self.graph_store)
        result = fe.index(rebuild=rebuild)

        be = BackendIndexer(toolbox, self.graph_store)
        be_info = be.index(rebuild=False)

        # Merge backend counts into the combined IndexResult
        result.api_endpoints = int(be_info.get("api_endpoints") or 0)
        result.services = int(be_info.get("services") or 0)
        result.entities = int(be_info.get("entities") or 0)
        result.tables = int(be_info.get("tables") or 0)
        result.backend_skipped = bool(be_info.get("skipped"))
        result.edges = int(result.edges or 0) + int(be_info.get("edges") or 0)
        result.indexed_count = int(result.indexed_count or 0) + int(be_info.get("indexed_count") or 0)
        result.duration_ms = round(
            float(result.duration_ms or 0) + float(be_info.get("duration_ms") or 0), 2
        )
        stats = dict(result.stats or {})
        stats["backend"] = be_info

        flow = FlowIndexer(toolbox, self.graph_store)
        flow_info = flow.index()
        result.api_calls = int(flow_info.get("api_calls_linked") or 0)
        result.field_mappings = int(flow_info.get("field_mappings") or 0)
        result.edges = int(result.edges or 0) + int(result.api_calls or 0) + int(result.field_mappings or 0)
        result.duration_ms = round(
            float(result.duration_ms or 0) + float(flow_info.get("duration_ms") or 0), 2
        )
        stats["flow"] = flow_info
        result.changed_files = changed
        stats["incremental"] = {
            "skipped_unchanged": False,
            "changed_files": changed,
            "changed_count": len(changed),
            "full_reindex": True,
        }
        result.stats = stats
        result.skipped_unchanged = False

        self.graph_store.mark_indexed(result.to_dict())
        if self.workspace_id:
            self.graph_store.set_meta("workspace_id", self.workspace_id)
            self.graph_store.set_meta("workspace_path", self.workspace_path)
            stats["workspace_id"] = self.workspace_id
            stats["knowledge_key"] = "workspace_id"
            result.stats = stats
        manifest.save()
        self._last_result = result.to_dict()
        toolbox._indexed = True
        return result


def get_index_manager(
    workspace_path: Optional[str] = None,
    hybrid_indexer: Optional[HybridIndexer] = None,
    *,
    workspace_id: Optional[str] = None,
    revision_id: Optional[str] = None,
) -> WorkspaceIndexManager:
    """Return (and cache) process-level manager. Prefer workspace_id as cache key."""
    ws = str(Path(workspace_path or settings.target_workspace_path).resolve())
    key = f"id:{workspace_id}" if workspace_id else f"path:{ws}"
    with _lock:
        mgr = _managers.get(key)
        if mgr is None:
            mgr = WorkspaceIndexManager(
                ws,
                hybrid_indexer=hybrid_indexer,
                workspace_id=workspace_id,
                revision_id=revision_id,
            )
            _managers[key] = mgr
        else:
            if workspace_id and mgr.workspace_path != ws:
                mgr.workspace_path = ws
                mgr.graph_store.workspace_path = ws
                try:
                    mgr.graph_store.set_meta("workspace_path", ws)
                except Exception:
                    pass
            if hybrid_indexer is not None:
                mgr.hybrid_indexer = hybrid_indexer
        return mgr


def reset_index_managers() -> None:
    """Test helper: drop cached managers."""
    with _lock:
        for mgr in _managers.values():
            try:
                mgr.graph_store.close()
            except Exception:
                pass
        _managers.clear()
