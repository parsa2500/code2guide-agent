"""Brain-as-tools helpers keyed by workspace_id (not raw path)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.app.exceptions import NotFoundError
from src.app.repositories.workspace_repo import WorkspaceRepository
from sqlalchemy.orm import Session


def _resolve_manager(db: Session, workspace_id: str):
    """Load workspace path for file resolution; cache/index keyed by workspace_id."""
    ws = WorkspaceRepository(db).get(workspace_id)
    if ws is None or ws.deleted_at is not None:
        raise NotFoundError("Workspace not found", code="WORKSPACE_NOT_FOUND")
    from src.knowledge.manager import get_index_manager

    return get_index_manager(ws.path, workspace_id=workspace_id), ws


def search(db: Session, workspace_id: str, query: str, k: int = 5) -> List[Dict[str, Any]]:
    """Hybrid search over the workspace brain."""
    manager, _ws = _resolve_manager(db, workspace_id)
    hits = manager.hybrid_indexer.search(query, limit=max(1, min(k, 50)))
    out: List[Dict[str, Any]] = []
    for hit in hits:
        out.append(
            {
                "id": getattr(hit, "id", ""),
                "title": getattr(hit, "title", ""),
                "content": getattr(hit, "content", ""),
                "file_path": getattr(hit, "file_path", ""),
                "item_type": getattr(hit, "item_type", ""),
                "score": float(getattr(hit, "score", 0.0)),
                "metadata": dict(getattr(hit, "metadata", {}) or {}),
            }
        )
    return out


def graph_get(
    db: Session,
    workspace_id: str,
    *,
    node_id: Optional[str] = None,
    filter_query: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Fetch graph node(s) by id or text filter."""
    manager, _ws = _resolve_manager(db, workspace_id)
    store = manager.graph_store
    nodes = []
    if node_id:
        node = store.get_node(node_id)
        if node is not None:
            nodes = [node]
    elif filter_query:
        nodes = store.search_nodes(filter_query, limit=limit)
    else:
        return []

    result: List[Dict[str, Any]] = []
    for n in nodes:
        if hasattr(n, "model_dump"):
            result.append(n.model_dump())
        elif isinstance(n, dict):
            result.append(n)
        else:
            result.append(
                {
                    "id": getattr(n, "id", ""),
                    "type": getattr(n, "type", getattr(n, "node_type", "")),
                    "label": getattr(n, "label", getattr(n, "title", "")),
                    "data": getattr(n, "data", getattr(n, "payload", {})),
                }
            )
    return result


def embed(text: str) -> List[float]:
    """Embed a single text via the process HybridIndexer embedder when available."""
    from src.search.hybrid_indexer import HybridIndexer

    indexer = HybridIndexer(collection_name="code2guide_brain_embed")
    if getattr(indexer, "_embedder", None) is None and hasattr(indexer, "ensure_ready"):
        try:
            indexer.ensure_ready()  # type: ignore[attr-defined]
        except Exception:
            pass
    embedder = getattr(indexer, "_embedder", None)
    if embedder is None:
        # Deterministic tiny stub vector when embeddings unavailable (tests/offline).
        return [float((sum(ord(c) for c in text) % 97) + 1) / 100.0]
    vectors = embedder.embed([text])
    return list(vectors[0]) if vectors else []
