"""Link form fields to DTO properties, entity fields, and table columns."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from src.knowledge.schema import EdgeType, GraphEdge, GraphNode, NodeType
from src.knowledge.store import GraphStore


def _norm(name: str) -> str:
    s = (name or "").strip()
    s = re.sub(r"[_\-\s]+", "", s)
    return s.lower()


def _dto_props_from_cs(content: str, dto_name: str) -> List[str]:
    """Extract property/parameter names from a C# record or class named dto_name."""
    props: List[str] = []
    # record TenderCreateDto(string Title, string? Description);
    rec = re.search(
        rf"(?:public\s+)?record\s+{re.escape(dto_name)}\s*\((?P<body>[^)]*)\)",
        content,
    )
    if rec:
        for part in rec.group("body").split(","):
            part = part.strip()
            if not part:
                continue
            m = re.search(r"([\w.]+)\s+(\w+)\s*$", part)
            if m:
                props.append(m.group(2))
        return props
    # class TenderCreateDto { public string Title { get; set; } }
    cls = re.search(
        rf"(?:public\s+)?(?:class|record)\s+{re.escape(dto_name)}\b(?P<body>[\s\S]*?)(?:\n(?:public\s+|internal\s+)?(?:class|record|interface)\s+|\Z)",
        content,
    )
    if cls:
        body = cls.group("body")
        for m in re.finditer(r"public\s+[\w.<>,\?\s]+\s+(\w+)\s*\{\s*get", body):
            props.append(m.group(1))
    return props


class FieldLinker:
    """Create MAPS_TO edges between form fields and backend DTO/entity/table fields."""

    def __init__(self, store: GraphStore, workspace_path: str):
        self.store = store
        self.workspace_root = Path(workspace_path).resolve()

    def link(self) -> Dict[str, Any]:
        edges: List[GraphEdge] = []
        dto_nodes: List[GraphNode] = []
        api_nodes = self.store.list_nodes(NodeType.API_ENDPOINT)
        form_nodes = self.store.list_nodes(NodeType.FORM)
        entity_nodes = {n.title: n for n in self.store.list_nodes(NodeType.ENTITY)}
        # also by name in payload
        for n in self.store.list_nodes(NodeType.ENTITY):
            entity_nodes[(n.payload or {}).get("name") or n.title] = n
        table_nodes = {n.title: n for n in self.store.list_nodes(NodeType.TABLE)}

        # Build form file → forms and form → fields
        forms_by_file: Dict[str, List[GraphNode]] = {}
        for f in form_nodes:
            forms_by_file.setdefault(f.file_path.replace("\\", "/"), []).append(f)

        # API calls edges: source form/page/route → api
        call_edges = []
        # We need edges of type CALLS_API — query via scanning all edges isn't exposed;
        # use neighbors from forms/pages/routes/components
        callers = (
            self.store.list_nodes(NodeType.FORM)
            + self.store.list_nodes(NodeType.PAGE)
            + self.store.list_nodes(NodeType.ROUTE)
            + self.store.list_nodes(NodeType.COMPONENT)
        )
        form_to_apis: Dict[str, List[GraphNode]] = {}
        for caller in callers:
            for api in self.store.neighbors(caller.id, EdgeType.CALLS_API):
                if api.node_type != NodeType.API_ENDPOINT:
                    continue
                # Attach to forms in same file when caller is page/component
                targets = []
                if caller.node_type == NodeType.FORM:
                    targets = [caller]
                else:
                    targets = forms_by_file.get(caller.file_path.replace("\\", "/"), [])
                    if not targets and caller.node_type == NodeType.ROUTE:
                        page_path = caller.file_path.replace("\\", "/")
                        # resolve via renders
                        for page in self.store.neighbors(caller.id, EdgeType.RENDERS):
                            targets.extend(forms_by_file.get(page.file_path.replace("\\", "/"), []))
                        targets.extend(forms_by_file.get(page_path, []))
                for form in targets:
                    form_to_apis.setdefault(form.id, []).append(api)

        # Also: if no CALLS_API yet, match forms to APIs by path keyword (tender)
        if not form_to_apis:
            for form in form_nodes:
                blob = f"{form.title} {form.file_path}".lower()
                for api in api_nodes:
                    apath = ((api.payload or {}).get("path") or api.title or "").lower()
                    if any(tok in blob and tok in apath for tok in ("tender", "مناقصه", "user", "کاربر")):
                        form_to_apis.setdefault(form.id, []).append(api)

        dto_cache: Dict[str, List[str]] = {}
        mappings = 0

        for form_id, apis in form_to_apis.items():
            fields = self.store.neighbors(form_id, EdgeType.CONTAINS_FIELD)
            for api in apis:
                dto_name = (api.payload or {}).get("from_body_type") or ""
                dto_props = self._resolve_dto_props(dto_name, api, dto_cache)
                # Ensure a synthetic DTO node for citation
                if dto_name and dto_props:
                    dto_id = f"dto:{dto_name}"
                    dto_nodes.append(
                        GraphNode(
                            id=dto_id,
                            node_type=NodeType.DTO,
                            title=dto_name,
                            file_path=(api.file_path or ""),
                            payload={"kind": "dto", "name": dto_name, "properties": dto_props},
                        )
                    )

                # Linked entities via service chain
                entities = self._entities_for_api(api)
                tables = []
                for ent in entities:
                    tables.extend(self.store.neighbors(ent.id, EdgeType.PERSISTS_TO))

                for field in fields:
                    fname = (field.payload or {}).get("name") or field.title or ""
                    label = (field.payload or {}).get("label") or ""
                    candidates = [fname, label]
                    matched_dto = self._best_match(candidates, dto_props)
                    if matched_dto and dto_name:
                        dto_id = f"dto:{dto_name}"
                        edges.append(
                            GraphEdge(
                                id=f"edge:maps:{field.id}:dto:{matched_dto}",
                                edge_type=EdgeType.MAPS_TO,
                                source_id=field.id,
                                target_id=dto_id,
                                payload={
                                    "target_kind": "dto_property",
                                    "property": matched_dto,
                                    "confidence": 0.9,
                                    "strategy": "name_match",
                                },
                            )
                        )
                        mappings += 1

                    for ent in entities:
                        ent_fields = [
                            f.get("name") if isinstance(f, dict) else str(f)
                            for f in ((ent.payload or {}).get("fields") or [])
                        ]
                        # fields may be list of dicts
                        if ent_fields and isinstance((ent.payload or {}).get("fields", [None])[0], dict):
                            ent_fields = [f["name"] for f in ent.payload["fields"] if f.get("name")]
                        matched_ent = self._best_match(candidates, ent_fields)
                        if matched_ent:
                            edges.append(
                                GraphEdge(
                                    id=f"edge:maps:{field.id}:ent:{ent.id}:{matched_ent}",
                                    edge_type=EdgeType.MAPS_TO,
                                    source_id=field.id,
                                    target_id=ent.id,
                                    payload={
                                        "target_kind": "entity_field",
                                        "property": matched_ent,
                                        "confidence": 0.85,
                                        "strategy": "name_match",
                                    },
                                )
                            )
                            mappings += 1

                    for table in tables:
                        cols = (table.payload or {}).get("columns") or []
                        col_names = [
                            c.get("name") if isinstance(c, dict) else str(c) for c in cols
                        ]
                        matched_col = self._best_match(candidates, col_names)
                        if matched_col:
                            edges.append(
                                GraphEdge(
                                    id=f"edge:maps:{field.id}:tbl:{table.id}:{matched_col}",
                                    edge_type=EdgeType.MAPS_TO,
                                    source_id=field.id,
                                    target_id=table.id,
                                    payload={
                                        "target_kind": "table_column",
                                        "property": matched_col,
                                        "confidence": 0.8,
                                        "strategy": "name_match",
                                    },
                                )
                            )
                            mappings += 1

        if dto_nodes:
            # Dedupe dto nodes
            by_id = {n.id: n for n in dto_nodes}
            self.store.upsert_nodes(list(by_id.values()))
        if edges:
            self.store.upsert_edges(edges)

        return {"field_mappings": mappings, "edges": len(edges)}

    def _resolve_dto_props(
        self, dto_name: str, api: GraphNode, cache: Dict[str, List[str]]
    ) -> List[str]:
        if not dto_name:
            openapi_fields = (api.payload or {}).get("request_dto_fields") or []
            return list(openapi_fields)
        if dto_name in cache:
            return cache[dto_name]
        props: List[str] = []
        # Search .cs files for the DTO definition
        for cs in self.workspace_root.rglob("*.cs"):
            if any(p in cs.parts for p in ("bin", "obj", "node_modules")):
                continue
            try:
                text = cs.read_text(encoding="utf-8-sig", errors="replace")
            except Exception:
                continue
            if dto_name not in text:
                continue
            found = _dto_props_from_cs(text, dto_name)
            if found:
                props = found
                break
        if not props:
            props = list((api.payload or {}).get("request_dto_fields") or [])
        cache[dto_name] = props
        return props

    def _entities_for_api(self, api: GraphNode) -> List[GraphNode]:
        entities: List[GraphNode] = []
        seen: Set[str] = set()
        for svc in self.store.neighbors(api.id, EdgeType.HANDLED_BY) + self.store.neighbors(
            api.id, EdgeType.USES_SERVICE
        ):
            for ent in self.store.neighbors(svc.id, EdgeType.PERSISTS_TO):
                if ent.node_type == NodeType.ENTITY and ent.id not in seen:
                    seen.add(ent.id)
                    entities.append(ent)
        return entities

    @staticmethod
    def _best_match(candidates: List[str], targets: List[str]) -> Optional[str]:
        if not targets:
            return None
        norms = {_norm(t): t for t in targets if t}
        for c in candidates:
            if not c:
                continue
            key = _norm(c)
            if key in norms:
                return norms[key]
            # plural/singular light touch
            for nk, orig in norms.items():
                if key == nk + "s" or key + "s" == nk or key.rstrip("s") == nk.rstrip("s"):
                    return orig
        return None
