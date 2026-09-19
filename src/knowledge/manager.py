"""Process-level workspace index manager (shared graph + hybrid indexer)."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Dict, Optional, TYPE_CHECKING

from src.core.config import settings
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
    ):
        self.workspace_path = str(Path(workspace_path).resolve())
        index_root = getattr(settings, "index_storage_path", None) or ".code2guide/index"
        db_path = default_db_path(self.workspace_path, index_root=index_root)
        self.graph_store = graph_store or GraphStore(self.workspace_path, db_path=db_path)
        self.hybrid_indexer = hybrid_indexer or HybridIndexer(
            collection_name=collection_name_for_workspace(self.workspace_path),
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
        if self._last_result:
            st["last_result"] = self._last_result
        return st

    def attach_toolbox(self, toolbox: "Code2GuideToolbox") -> "Code2GuideToolbox":
        """Point toolbox at this manager's hybrid indexer and mark indexed if graph exists."""
        toolbox.hybrid_indexer = self.hybrid_indexer
        toolbox._graph_store = self.graph_store
        toolbox._index_manager = self
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
        from src.knowledge.indexer import FrontendIndexer
        from src.knowledge.backend_indexer import BackendIndexer

        toolbox.hybrid_indexer = self.hybrid_indexer
        toolbox._graph_store = self.graph_store
        toolbox._index_manager = self

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
        result.stats = stats
        self.graph_store.mark_indexed(result.to_dict())
        self._last_result = result.to_dict()
        toolbox._indexed = True
        return result


def get_index_manager(
    workspace_path: Optional[str] = None,
    hybrid_indexer: Optional[HybridIndexer] = None,
) -> WorkspaceIndexManager:
    """Return (and cache) the process-level manager for a workspace."""
    ws = str(Path(workspace_path or settings.target_workspace_path).resolve())
    with _lock:
        mgr = _managers.get(ws)
        if mgr is None:
            mgr = WorkspaceIndexManager(ws, hybrid_indexer=hybrid_indexer)
            _managers[ws] = mgr
        elif hybrid_indexer is not None:
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
