"""Index CALLS_API edges and walk end-to-end front↔back flows."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

from src.knowledge.schema import EdgeType, GraphEdge, GraphNode, NodeType
from src.knowledge.store import GraphStore
from src.knowledge.field_linker import FieldLinker
from src.parsers.frontend_api_tracer import FrontendApiTracer

if TYPE_CHECKING:
    from src.agent.tools import Code2GuideToolbox


class FlowIndexer:
    """After FE+BE index: link UI files to APIs and map form fields."""

    def __init__(self, toolbox: "Code2GuideToolbox", store: GraphStore):
        self.toolbox = toolbox
        self.store = store
        self.workspace_path = toolbox.workspace_path

    def index(self) -> Dict[str, Any]:
        started = time.perf_counter()
        tracer = FrontendApiTracer()
        calls = tracer.scan_workspace(self.workspace_path)
        api_nodes = self.store.list_nodes(NodeType.API_ENDPOINT)

        # Build file → graph node ids (route/page/form/component)
        file_to_nodes: Dict[str, List[GraphNode]] = {}
        for nt in (
            NodeType.ROUTE,
            NodeType.PAGE,
            NodeType.FORM,
            NodeType.COMPONENT,
        ):
            for n in self.store.list_nodes(nt):
                fp = (n.file_path or "").replace("\\", "/")
                if fp:
                    file_to_nodes.setdefault(fp, []).append(n)

        edges: List[GraphEdge] = []
        linked = 0
        for call in calls:
            api_id = FrontendApiTracer.match_endpoint(
                call.method, call.url_normalized, api_nodes
            )
            if not api_id:
                continue
            sources = file_to_nodes.get(call.file_path.replace("\\", "/"), [])
            if not sources:
                # create a lightweight component node for the caller file
                cid = f"component:{call.file_path}"
                node = GraphNode(
                    id=cid,
                    node_type=NodeType.COMPONENT,
                    title=Path(call.file_path).stem,
                    file_path=call.file_path,
                    payload={"inferred": True},
                )
                self.store.upsert_nodes([node])
                sources = [node]
                file_to_nodes.setdefault(call.file_path, []).append(node)

            for src in sources:
                edges.append(
                    GraphEdge(
                        id=f"edge:calls_api:{src.id}:{api_id}:{call.line_number}",
                        edge_type=EdgeType.CALLS_API,
                        source_id=src.id,
                        target_id=api_id,
                        payload={
                            "method": call.method,
                            "url": call.url_normalized,
                            "url_raw": call.url_raw,
                            "line_number": call.line_number,
                            "kind": call.kind,
                        },
                    )
                )
                linked += 1
                # Also link forms in the same file
                if src.node_type != NodeType.FORM:
                    for form in file_to_nodes.get(call.file_path.replace("\\", "/"), []):
                        if form.node_type == NodeType.FORM and form.id != src.id:
                            edges.append(
                                GraphEdge(
                                    id=f"edge:calls_api:{form.id}:{api_id}:{call.line_number}",
                                    edge_type=EdgeType.CALLS_API,
                                    source_id=form.id,
                                    target_id=api_id,
                                    payload={
                                        "method": call.method,
                                        "url": call.url_normalized,
                                        "line_number": call.line_number,
                                        "via": src.id,
                                    },
                                )
                            )
                            linked += 1

            # Link matching routes by path keyword (tenders)
            for route in self.store.list_nodes(NodeType.ROUTE):
                rpath = ((route.payload or {}).get("path") or route.id or "").lower()
                url_l = call.url_normalized.lower()
                if "tender" in rpath and "tender" in url_l:
                    edges.append(
                        GraphEdge(
                            id=f"edge:calls_api:{route.id}:{api_id}:route",
                            edge_type=EdgeType.CALLS_API,
                            source_id=route.id,
                            target_id=api_id,
                            payload={
                                "method": call.method,
                                "url": call.url_normalized,
                                "strategy": "path_keyword",
                            },
                        )
                    )
                    linked += 1

        if edges:
            # dedupe by id
            by_id = {e.id: e for e in edges}
            self.store.upsert_edges(list(by_id.values()))

        linker = FieldLinker(self.store, self.workspace_path)
        link_info = linker.link()

        return {
            "api_calls_found": len(calls),
            "api_calls_linked": linked,
            "field_mappings": link_info.get("field_mappings", 0),
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "stats": {"calls": len(calls), "link": link_info},
        }


class FlowTracer:
    """Walk Route/Page/Form → API → Service → Entity → Table chains."""

    def __init__(self, store: GraphStore):
        self.store = store

    def trace(self, from_ref: str) -> Dict[str, Any]:
        start_nodes = self._resolve_start(from_ref)
        chains: List[Dict[str, Any]] = []
        missing: List[str] = []

        if not start_nodes:
            return {
                "from": from_ref,
                "chains": [],
                "missing_links": [f"Could not resolve start node for '{from_ref}'"],
            }

        for start in start_nodes:
            chain = self._walk_from(start)
            if chain.get("steps"):
                chains.append(chain)
            else:
                missing.append(f"No outbound flow from {start.id}")

        if chains and not any(
            any(s.get("node_type") == NodeType.TABLE.value for s in c.get("steps", []))
            for c in chains
        ):
            missing.append("No TABLE node reached in any chain")

        return {"from": from_ref, "chains": chains, "missing_links": missing}

    def _resolve_start(self, from_ref: str) -> List[GraphNode]:
        ref = (from_ref or "").strip()
        if not ref:
            return []
        # Exact node id
        node = self.store.get_node(ref)
        if node:
            return [node]
        if ref.startswith("route:") or ref.startswith("page:") or ref.startswith("form:"):
            node = self.store.get_node(ref)
            return [node] if node else []

        path = ref if ref.startswith("/") else "/" + ref.lstrip("/")
        # route by path
        matches: List[GraphNode] = []
        for r in self.store.list_nodes(NodeType.ROUTE):
            rpath = (r.payload or {}).get("path") or ""
            if rpath == path or rpath.rstrip("/") == path.rstrip("/"):
                matches.append(r)
            elif path.lstrip("/") and path.lstrip("/") in (rpath or ""):
                matches.append(r)
        if matches:
            return matches

        # search title/path
        return self.store.search_nodes(
            ref,
            node_types=[NodeType.ROUTE.value, NodeType.PAGE.value, NodeType.FORM.value],
            limit=5,
        )

    def _walk_from(self, start: GraphNode) -> Dict[str, Any]:
        steps: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        field_maps: List[Dict[str, Any]] = []

        def add(node: GraphNode, via: str = ""):
            if node.id in seen:
                return
            seen.add(node.id)
            steps.append(
                {
                    "id": node.id,
                    "node_type": node.node_type.value
                    if hasattr(node.node_type, "value")
                    else str(node.node_type),
                    "title": node.title,
                    "file_path": node.file_path,
                    "payload": node.payload or {},
                    "via": via,
                }
            )

        add(start)

        # Expand renders to page/form/component
        frontier = [start]
        apis: List[GraphNode] = []

        for _ in range(4):
            nxt: List[GraphNode] = []
            for n in frontier:
                for child in self.store.neighbors(n.id, EdgeType.RENDERS):
                    add(child, via=EdgeType.RENDERS.value)
                    nxt.append(child)
                for child in self.store.neighbors(n.id, EdgeType.CONTAINS_FIELD):
                    add(child, via=EdgeType.CONTAINS_FIELD.value)
                for api in self.store.neighbors(n.id, EdgeType.CALLS_API):
                    add(api, via=EdgeType.CALLS_API.value)
                    apis.append(api)
                    nxt.append(api)
            frontier = nxt
            if not frontier:
                break

        # If start is route and no CALLS_API yet, try forms in rendered files
        if not apis and start.node_type == NodeType.ROUTE:
            for page in self.store.neighbors(start.id, EdgeType.RENDERS):
                for api in self.store.neighbors(page.id, EdgeType.CALLS_API):
                    add(api, via=EdgeType.CALLS_API.value)
                    apis.append(api)

        for api in apis:
            for svc in self.store.neighbors(api.id, EdgeType.HANDLED_BY) + self.store.neighbors(
                api.id, EdgeType.USES_SERVICE
            ):
                add(svc, via=EdgeType.USES_SERVICE.value)
                for ent in self.store.neighbors(svc.id, EdgeType.PERSISTS_TO):
                    add(ent, via=EdgeType.PERSISTS_TO.value)
                    for tbl in self.store.neighbors(ent.id, EdgeType.PERSISTS_TO):
                        add(tbl, via=EdgeType.PERSISTS_TO.value)

        # Field mappings from form fields in chain
        for step in list(steps):
            if step["node_type"] != NodeType.FORM_FIELD.value:
                continue
            node = self.store.get_node(step["id"])
            if not node:
                continue
            for target in self.store.neighbors(node.id, EdgeType.MAPS_TO):
                field_maps.append(
                    {
                        "from_field": node.title or (node.payload or {}).get("name"),
                        "from_id": node.id,
                        "to_id": target.id,
                        "to_title": target.title,
                        "to_type": target.node_type.value
                        if hasattr(target.node_type, "value")
                        else str(target.node_type),
                    }
                )

        return {
            "start_id": start.id,
            "start_title": start.title,
            "steps": steps,
            "field_mappings": field_maps,
        }

    def format_markdown(self, trace_result: Dict[str, Any]) -> str:
        chains = trace_result.get("chains") or []
        if not chains:
            missing = "; ".join(trace_result.get("missing_links") or []) or "زنجیره‌ای یافت نشد"
            return f"### جریان کامل (Trace)\n\n{missing}\n"

        lines = ["### جریان کامل فرانت ↔ بک (Trace)", ""]
        for i, chain in enumerate(chains, 1):
            lines.append(
                f"**زنجیره {i}** — شروع: `{chain.get('start_title') or chain.get('start_id')}`"
            )
            for step in chain.get("steps") or []:
                ntype = step.get("node_type")
                title = step.get("title") or step.get("id")
                fpath = step.get("file_path") or ""
                cite = f" — فایل: `{fpath}`" if fpath else ""
                lines.append(f"- `{ntype}` → **{title}**{cite}")
            fmaps = chain.get("field_mappings") or []
            if fmaps:
                lines.append("  - نگاشت فیلدها:")
                for fm in fmaps[:20]:
                    lines.append(
                        f"    - `{fm.get('from_field')}` → `{fm.get('to_title')}` ({fm.get('to_type')})"
                    )
            lines.append("")
        missing = trace_result.get("missing_links") or []
        if missing:
            lines.append("**حلقه‌های ناقص:** " + "؛ ".join(missing))
        return "\n".join(lines)
