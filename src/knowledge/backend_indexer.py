"""Index .NET backend API/service/entity/table into the knowledge graph + hybrid store."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, TYPE_CHECKING

from src.knowledge.schema import EdgeType, GraphEdge, GraphNode, NodeType
from src.knowledge.store import GraphStore
from src.parsers.stack_detector import StackDetector
from src.parsers.dotnet import (
    DotNetApiParser,
    DotNetEntityParser,
    DotNetMigrationParser,
    DotNetServiceParser,
    MvcApiParser,
)
from src.search.hybrid_indexer import IndexedItem

if TYPE_CHECKING:
    from src.agent.tools import Code2GuideToolbox
    from src.knowledge.indexer import IndexResult


class BackendIndexer:
    """Deep-index ASP.NET Core backends discovered under the workspace."""

    def __init__(self, toolbox: "Code2GuideToolbox", store: GraphStore):
        self.toolbox = toolbox
        self.store = store
        self.workspace_path = toolbox.workspace_path
        self.workspace_root = Path(self.workspace_path).resolve()

    def index(self, *, rebuild: bool = False) -> Dict[str, Any]:
        """Append backend nodes/edges/items. Never clears the store (caller owns rebuild)."""
        started = time.perf_counter()
        detection = StackDetector(self.workspace_path).detect()
        stats: Dict[str, Any] = {"stack_detection": detection.to_dict()}

        if detection.skipped or detection.stack != "dotnet":
            return {
                "api_endpoints": 0,
                "services": 0,
                "entities": 0,
                "tables": 0,
                "edges": 0,
                "indexed_count": 0,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "stats": stats,
                "skipped": True,
            }

        cs_files: List[Path] = []
        for root_rel in detection.backend_roots:
            root = self.workspace_root if root_rel in (".", "") else self.workspace_root / root_rel
            if not root.exists():
                continue
            cs_files.extend(StackDetector.iter_cs_files(root))

        # De-dupe
        seen = set()
        unique_files: List[Path] = []
        for f in cs_files:
            key = str(f.resolve())
            if key not in seen:
                seen.add(key)
                unique_files.append(f)

        api_parser = DotNetApiParser()
        mvc_parser = MvcApiParser()
        svc_parser = DotNetServiceParser()
        ent_parser = DotNetEntityParser()
        mig_parser = DotNetMigrationParser()

        endpoints = api_parser.parse_paths(unique_files, self.workspace_root)
        if detection.is_mvc_framework:
            mvc_eps = mvc_parser.parse_paths(unique_files, self.workspace_root)
            endpoints = self._merge_endpoints(endpoints, mvc_eps)
            stats["mvc_endpoints"] = len(mvc_eps)
        services = svc_parser.parse_paths(unique_files, self.workspace_root)
        entities = ent_parser.parse_paths(unique_files, self.workspace_root)
        tables = mig_parser.parse_paths(unique_files, self.workspace_root)

        # OpenAPI merge (existing extractor)
        try:
            openapi_eps = self.toolbox.contract_extractor.scan_rbac_and_swagger()
        except Exception:
            openapi_eps = []

        nodes: List[GraphNode] = []
        edges: List[GraphEdge] = []
        items: List[IndexedItem] = []

        # --- API endpoints from C# ---
        for ep in endpoints:
            eid = f"api:{ep.method}:{ep.path}"
            payload = {
                "method": ep.method,
                "path": ep.path,
                "action_name": ep.action_name,
                "controller_name": ep.controller_name,
                "roles": ep.roles,
                "from_body_type": ep.from_body_type,
                "line_number": ep.line_number,
            }
            nodes.append(
                GraphNode(
                    id=eid,
                    node_type=NodeType.API_ENDPOINT,
                    title=f"{ep.method} {ep.path}",
                    file_path=ep.file_path,
                    payload=payload,
                )
            )
            items.append(
                IndexedItem(
                    id=eid,
                    title=f"{ep.method} {ep.path}",
                    content=" ".join(
                        str(x)
                        for x in [
                            ep.method,
                            ep.path,
                            ep.controller_name,
                            ep.action_name,
                            ep.from_body_type,
                            " ".join(ep.roles),
                            ep.file_path,
                        ]
                        if x
                    ),
                    file_path=ep.file_path,
                    item_type="api",
                    metadata=payload,
                )
            )

            # Link controller action → matching *Service by name heuristic
            for svc in services:
                stem = ep.controller_name.replace("Controller", "")
                if stem and stem.lower() in svc.name.lower():
                    edges.append(
                        GraphEdge(
                            id=f"edge:handled_by:{eid}:{svc.name}",
                            edge_type=EdgeType.HANDLED_BY,
                            source_id=eid,
                            target_id=f"service:{svc.name}",
                        )
                    )
                    edges.append(
                        GraphEdge(
                            id=f"edge:uses_service:{eid}:{svc.name}",
                            edge_type=EdgeType.USES_SERVICE,
                            source_id=eid,
                            target_id=f"service:{svc.name}",
                        )
                    )

        # OpenAPI-only endpoints not already covered
        existing_keys = {(ep.method.upper(), ep.path) for ep in endpoints}
        for oep in openapi_eps:
            if oep.method == "BACKEND_ROLE":
                continue
            key = (oep.method.upper(), oep.path)
            if key in existing_keys:
                continue
            eid = f"api:{oep.method.upper()}:{oep.path}"
            payload = {
                "method": oep.method.upper(),
                "path": oep.path,
                "roles": oep.roles_required,
                "request_dto_fields": oep.request_dto_fields,
                "summary": oep.summary,
                "source": oep.source,
            }
            nodes.append(
                GraphNode(
                    id=eid,
                    node_type=NodeType.API_ENDPOINT,
                    title=f"{oep.method.upper()} {oep.path}",
                    file_path=oep.source or "",
                    payload=payload,
                )
            )
            items.append(
                IndexedItem(
                    id=eid,
                    title=f"{oep.method.upper()} {oep.path}",
                    content=f"{oep.method} {oep.path} {oep.summary or ''} {' '.join(oep.request_dto_fields)}",
                    file_path=oep.source or "",
                    item_type="api",
                    metadata=payload,
                )
            )

        # --- Services ---
        for svc in services:
            sid = f"service:{svc.name}"
            method_names = [m.name for m in svc.methods]
            payload = {
                "name": svc.name,
                "methods": [m.model_dump() if hasattr(m, "model_dump") else m.dict() for m in svc.methods],
                "injected_types": svc.injected_types,
            }
            nodes.append(
                GraphNode(
                    id=sid,
                    node_type=NodeType.SERVICE,
                    title=svc.name,
                    file_path=svc.file_path,
                    payload=payload,
                )
            )
            items.append(
                IndexedItem(
                    id=sid,
                    title=svc.name,
                    content=f"{svc.name} {' '.join(method_names)} {svc.file_path}",
                    file_path=svc.file_path,
                    item_type="service",
                    metadata={"name": svc.name, "methods": method_names},
                )
            )
            # Service → Entity by name overlap (TenderService → Tender)
            for ent in entities:
                base = svc.name
                for suf in ("Service", "Handler", "UseCase", "Manager", "Repository"):
                    if base.endswith(suf):
                        base = base[: -len(suf)]
                        break
                if base and (base.lower() == ent.name.lower() or base.lower() in ent.name.lower()):
                    edges.append(
                        GraphEdge(
                            id=f"edge:persists:{sid}:{ent.name}",
                            edge_type=EdgeType.PERSISTS_TO,
                            source_id=sid,
                            target_id=f"entity:{ent.name}",
                        )
                    )

        # --- Entities ---
        entity_by_name = {e.name: e for e in entities}
        for ent in entities:
            eid = f"entity:{ent.name}"
            field_names = [f.name for f in ent.fields]
            payload = {
                "name": ent.name,
                "table_name": ent.table_name,
                "dbset_name": ent.dbset_name,
                "fields": [f.model_dump() if hasattr(f, "model_dump") else f.dict() for f in ent.fields],
            }
            nodes.append(
                GraphNode(
                    id=eid,
                    node_type=NodeType.ENTITY,
                    title=ent.name,
                    file_path=ent.file_path,
                    payload=payload,
                )
            )
            items.append(
                IndexedItem(
                    id=eid,
                    title=ent.name,
                    content=f"entity {ent.name} table {ent.table_name or ''} fields {' '.join(field_names)} {ent.file_path}",
                    file_path=ent.file_path,
                    item_type="entity",
                    metadata={
                        "name": ent.name,
                        "table_name": ent.table_name,
                        "fields": field_names,
                    },
                )
            )
            if ent.table_name:
                tid = f"table:{ent.table_name}"
                edges.append(
                    GraphEdge(
                        id=f"edge:persists_entity:{eid}:{ent.table_name}",
                        edge_type=EdgeType.PERSISTS_TO,
                        source_id=eid,
                        target_id=tid,
                    )
                )
            for fld in ent.fields:
                if fld.foreign_key_to and fld.foreign_key_to in entity_by_name:
                    edges.append(
                        GraphEdge(
                            id=f"edge:fk:{ent.name}:{fld.name}:{fld.foreign_key_to}",
                            edge_type=EdgeType.FK_TO,
                            source_id=eid,
                            target_id=f"entity:{fld.foreign_key_to}",
                            payload={"field": fld.name},
                        )
                    )
                # Navigation typed as other entity
                nav_type = fld.clr_type.rstrip("?").split("<")[-1].rstrip(">")
                if fld.is_navigation and nav_type in entity_by_name and nav_type != ent.name:
                    edges.append(
                        GraphEdge(
                            id=f"edge:fk_nav:{ent.name}:{fld.name}:{nav_type}",
                            edge_type=EdgeType.FK_TO,
                            source_id=eid,
                            target_id=f"entity:{nav_type}",
                            payload={"field": fld.name, "navigation": True},
                        )
                    )

        # --- Tables from migrations ---
        table_names_from_entities = {e.table_name for e in entities if e.table_name}
        for table in tables:
            tid = f"table:{table.name}"
            col_names = [c.name for c in table.columns]
            payload = {
                "name": table.name,
                "columns": [c.model_dump() if hasattr(c, "model_dump") else c.dict() for c in table.columns],
            }
            nodes.append(
                GraphNode(
                    id=tid,
                    node_type=NodeType.TABLE,
                    title=table.name,
                    file_path=table.file_path,
                    payload=payload,
                )
            )
            items.append(
                IndexedItem(
                    id=tid,
                    title=table.name,
                    content=f"table {table.name} columns {' '.join(col_names)} {table.file_path}",
                    file_path=table.file_path,
                    item_type="table",
                    metadata={"name": table.name, "columns": col_names},
                )
            )

        # Ensure entity-linked tables exist even without migration
        for ent in entities:
            if not ent.table_name:
                continue
            tid = f"table:{ent.table_name}"
            if any(n.id == tid for n in nodes):
                continue
            if ent.table_name in {t.name for t in tables}:
                continue
            nodes.append(
                GraphNode(
                    id=tid,
                    node_type=NodeType.TABLE,
                    title=ent.table_name,
                    file_path=ent.file_path,
                    payload={
                        "name": ent.table_name,
                        "columns": [
                            {"name": f.name, "sql_type": f.clr_type, "nullable": not f.is_required}
                            for f in ent.fields
                            if not f.is_navigation
                        ],
                        "inferred_from_entity": ent.name,
                    },
                )
            )
            items.append(
                IndexedItem(
                    id=tid,
                    title=ent.table_name,
                    content=f"table {ent.table_name} from entity {ent.name}",
                    file_path=ent.file_path,
                    item_type="table",
                    metadata={"name": ent.table_name, "inferred_from_entity": ent.name},
                )
            )

        self.store.upsert_nodes(nodes)
        self.store.upsert_edges(edges)
        if items:
            # Append to hybrid (do not wipe frontend vectors)
            self.toolbox.hybrid_indexer.index_items(items, rebuild=False)

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        result = {
            "api_endpoints": len([n for n in nodes if n.node_type == NodeType.API_ENDPOINT]),
            "services": len([n for n in nodes if n.node_type == NodeType.SERVICE]),
            "entities": len([n for n in nodes if n.node_type == NodeType.ENTITY]),
            "tables": len([n for n in nodes if n.node_type == NodeType.TABLE]),
            "edges": len(edges),
            "indexed_count": len(items),
            "duration_ms": duration_ms,
            "cs_files": len(unique_files),
            "stats": stats,
            "skipped": False,
            "is_mvc_framework": detection.is_mvc_framework,
        }
        return result

    @staticmethod
    def _merge_endpoints(core_eps, mvc_eps):
        """Dedupe by (method, path, file_path); prefer Core entries when both exist."""
        seen_soft = set()
        out = []
        for ep in list(core_eps) + list(mvc_eps):
            soft = ((ep.method or "GET").upper(), ep.path or "", ep.file_path or "")
            if soft in seen_soft:
                continue
            seen_soft.add(soft)
            out.append(ep)
        return out
