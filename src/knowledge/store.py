"""SQLite-backed explicit knowledge graph store."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from src.knowledge.schema import EdgeType, GraphEdge, GraphNode, NodeType


def workspace_hash(workspace_path: str) -> str:
    resolved = str(Path(workspace_path).resolve())
    return hashlib.sha1(resolved.encode("utf-8")).hexdigest()[:12]


def default_db_path(
    workspace_path: str,
    index_root: Optional[str] = None,
    *,
    workspace_id: Optional[str] = None,
    revision_id: Optional[str] = None,
) -> Path:
    """Resolve graph DB path. Prefer workspace_id key; dual-read legacy path-hash."""
    from src.knowledge.contract import resolve_graph_db_path

    path, _mode = resolve_graph_db_path(
        workspace_path=workspace_path,
        workspace_id=workspace_id,
        revision_id=revision_id,
        index_root=index_root,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


class GraphStore:
    """Persists nodes/edges and index metadata for one workspace."""

    def __init__(
        self,
        workspace_path: str,
        db_path: Optional[Path] = None,
        *,
        workspace_id: Optional[str] = None,
        revision_id: Optional[str] = None,
        index_root: Optional[str] = None,
    ):
        self.workspace_path = str(Path(workspace_path).resolve())
        self.workspace_id = workspace_id
        self.revision_id = revision_id
        if db_path is not None:
            self.db_path = Path(db_path)
            self.storage_mode = "explicit"
        else:
            from src.knowledge.contract import resolve_graph_db_path

            self.db_path, self.storage_mode = resolve_graph_db_path(
                workspace_path=self.workspace_path,
                workspace_id=workspace_id,
                revision_id=revision_id,
                index_root=index_root,
            )
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        if workspace_id:
            self.set_meta("workspace_id", workspace_id)
        if revision_id:
            self.set_meta("revision_id", revision_id)

    def _init_schema(self) -> None:
        cur = self._conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                node_type TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                file_path TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS edges (
                id TEXT PRIMARY KEY,
                edge_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                payload TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(source_id) REFERENCES nodes(id),
                FOREIGN KEY(target_id) REFERENCES nodes(id)
            );
            CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(node_type);
            CREATE INDEX IF NOT EXISTS idx_nodes_file ON nodes(file_path);
            CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
            CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
            CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(edge_type);
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def clear(self) -> None:
        cur = self._conn.cursor()
        cur.execute("DELETE FROM edges")
        cur.execute("DELETE FROM nodes")
        self._conn.commit()

    def set_meta(self, key: str, value: Any) -> None:
        cur = self._conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            (key, json.dumps(value, ensure_ascii=False)),
        )
        self._conn.commit()

    def get_meta(self, key: str, default: Any = None) -> Any:
        cur = self._conn.cursor()
        cur.execute("SELECT value FROM meta WHERE key = ?", (key,))
        row = cur.fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except Exception:
            return row["value"]

    def upsert_nodes(self, nodes: Sequence[GraphNode]) -> int:
        if not nodes:
            return 0
        cur = self._conn.cursor()
        cur.executemany(
            """
            INSERT OR REPLACE INTO nodes(id, node_type, title, file_path, payload)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    n.id,
                    n.node_type.value if isinstance(n.node_type, NodeType) else str(n.node_type),
                    n.title or "",
                    n.file_path or "",
                    json.dumps(n.payload or {}, ensure_ascii=False),
                )
                for n in nodes
            ],
        )
        self._conn.commit()
        return len(nodes)

    def upsert_edges(self, edges: Sequence[GraphEdge]) -> int:
        if not edges:
            return 0
        cur = self._conn.cursor()
        cur.executemany(
            """
            INSERT OR REPLACE INTO edges(id, edge_type, source_id, target_id, payload)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    e.id,
                    e.edge_type.value if isinstance(e.edge_type, EdgeType) else str(e.edge_type),
                    e.source_id,
                    e.target_id,
                    json.dumps(e.payload or {}, ensure_ascii=False),
                )
                for e in edges
            ],
        )
        self._conn.commit()
        return len(edges)

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM nodes WHERE id = ?", (node_id,))
        row = cur.fetchone()
        return self._row_to_node(row) if row else None

    def list_nodes(
        self,
        node_type: Optional[NodeType | str] = None,
        file_path: Optional[str] = None,
        limit: int = 5000,
    ) -> List[GraphNode]:
        cur = self._conn.cursor()
        clauses: List[str] = []
        params: List[Any] = []
        if node_type is not None:
            clauses.append("node_type = ?")
            params.append(node_type.value if isinstance(node_type, NodeType) else str(node_type))
        if file_path is not None:
            clauses.append("file_path = ?")
            params.append(file_path.replace("\\", "/"))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        cur.execute(f"SELECT * FROM nodes {where} LIMIT ?", [*params, limit])
        return [self._row_to_node(r) for r in cur.fetchall()]

    def neighbors(
        self,
        node_id: str,
        edge_type: Optional[EdgeType | str] = None,
        direction: str = "out",
    ) -> List[GraphNode]:
        cur = self._conn.cursor()
        et = None
        if edge_type is not None:
            et = edge_type.value if isinstance(edge_type, EdgeType) else str(edge_type)

        if direction == "in":
            sql = "SELECT n.* FROM edges e JOIN nodes n ON n.id = e.source_id WHERE e.target_id = ?"
            params: List[Any] = [node_id]
        else:
            sql = "SELECT n.* FROM edges e JOIN nodes n ON n.id = e.target_id WHERE e.source_id = ?"
            params = [node_id]
        if et:
            sql += " AND e.edge_type = ?"
            params.append(et)
        cur.execute(sql, params)
        return [self._row_to_node(r) for r in cur.fetchall()]

    def search_nodes(self, query: str, node_types: Optional[Sequence[str]] = None, limit: int = 30) -> List[GraphNode]:
        """Simple lexical search over title + payload JSON text."""
        q = (query or "").strip().lower()
        if not q:
            return []
        nodes = self.list_nodes(limit=10000)
        scored: List[tuple] = []
        allowed = set(node_types) if node_types else None
        for n in nodes:
            if allowed and n.node_type.value not in allowed and str(n.node_type) not in allowed:
                continue
            blob = f"{n.title} {n.file_path} {json.dumps(n.payload, ensure_ascii=False)}".lower()
            score = 0
            if q in blob:
                score += 5
            for token in q.split():
                if len(token) > 1 and token in blob:
                    score += 1
            if score:
                scored.append((score, n))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [n for _, n in scored[:limit]]

    def count_nodes(self, node_type: Optional[NodeType | str] = None) -> int:
        cur = self._conn.cursor()
        if node_type is None:
            cur.execute("SELECT COUNT(*) AS c FROM nodes")
        else:
            nt = node_type.value if isinstance(node_type, NodeType) else str(node_type)
            cur.execute("SELECT COUNT(*) AS c FROM nodes WHERE node_type = ?", (nt,))
        return int(cur.fetchone()["c"])

    def count_edges(self) -> int:
        cur = self._conn.cursor()
        cur.execute("SELECT COUNT(*) AS c FROM edges")
        return int(cur.fetchone()["c"])

    def mark_indexed(self, stats: Dict[str, Any]) -> None:
        self.set_meta("workspace_path", self.workspace_path)
        self.set_meta("workspace_hash", workspace_hash(self.workspace_path))
        self.set_meta("last_indexed_at", time.time())
        self.set_meta("stats", stats)

    def status(self) -> Dict[str, Any]:
        last = self.get_meta("last_indexed_at")
        stats = self.get_meta("stats") or {}
        counts = {
            "routes": self.count_nodes(NodeType.ROUTE),
            "pages": self.count_nodes(NodeType.PAGE),
            "components": self.count_nodes(NodeType.COMPONENT),
            "forms": self.count_nodes(NodeType.FORM),
            "form_fields": self.count_nodes(NodeType.FORM_FIELD),
            "ui_buttons": self.count_nodes(NodeType.UI_BUTTON),
            "i18n_strings": self.count_nodes(NodeType.I18N_STRING),
            "ui_texts": self.count_nodes(NodeType.UI_TEXT),
            "api_endpoints": self.count_nodes(NodeType.API_ENDPOINT),
            "services": self.count_nodes(NodeType.SERVICE),
            "entities": self.count_nodes(NodeType.ENTITY),
            "tables": self.count_nodes(NodeType.TABLE),
            "edges": self.count_edges(),
            "total_nodes": self.count_nodes(),
        }
        return {
            "exists": last is not None and counts["total_nodes"] > 0,
            "workspace_path": self.workspace_path,
            "workspace_hash": workspace_hash(self.workspace_path),
            "db_path": str(self.db_path),
            "last_indexed_at": last,
            "counts": counts,
            "stats": stats,
        }

    def forms_for_files(self, file_paths: Sequence[str]) -> List[GraphNode]:
        wanted = {p.replace("\\", "/") for p in file_paths}
        return [n for n in self.list_nodes(NodeType.FORM) if n.file_path in wanted]

    def form_details(self, form_node: GraphNode) -> Dict[str, Any]:
        fields = self.neighbors(form_node.id, EdgeType.CONTAINS_FIELD)
        buttons = self.neighbors(form_node.id, EdgeType.HAS_BUTTON)
        return {
            "form": form_node,
            "fields": fields,
            "buttons": buttons,
        }

    @staticmethod
    def _row_to_node(row: sqlite3.Row) -> GraphNode:
        payload = {}
        try:
            payload = json.loads(row["payload"] or "{}")
        except Exception:
            payload = {}
        return GraphNode(
            id=row["id"],
            node_type=NodeType(row["node_type"]),
            title=row["title"] or "",
            file_path=row["file_path"] or "",
            payload=payload,
        )
