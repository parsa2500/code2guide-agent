"""Deep frontend indexer: routes + AST forms + i18n → graph + hybrid vectors."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

from src.knowledge.schema import EdgeType, GraphEdge, GraphNode, NodeType
from src.knowledge.store import GraphStore
from src.search.hybrid_indexer import IndexedItem

if TYPE_CHECKING:
    from src.agent.tools import Code2GuideToolbox


@dataclass
class IndexResult:
    workspace_path: str
    duration_ms: float = 0.0
    routes: int = 0
    components: int = 0
    forms: int = 0
    form_fields: int = 0
    ui_buttons: int = 0
    i18n_strings: int = 0
    edges: int = 0
    indexed_count: int = 0
    use_vector: bool = False
    collection_name: str = ""
    files_inspected: int = 0
    db_path: str = ""
    # Phase 2 backend
    api_endpoints: int = 0
    services: int = 0
    entities: int = 0
    tables: int = 0
    backend_skipped: bool = False
    api_calls: int = 0
    field_mappings: int = 0
    skipped_unchanged: bool = False
    changed_files: List[str] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workspace_path": self.workspace_path,
            "duration_ms": self.duration_ms,
            "routes": self.routes,
            "components": self.components,
            "forms": self.forms,
            "form_fields": self.form_fields,
            "ui_buttons": self.ui_buttons,
            "i18n_strings": self.i18n_strings,
            "edges": self.edges,
            "indexed_count": self.indexed_count,
            "use_vector": self.use_vector,
            "collection_name": self.collection_name,
            "files_inspected": self.files_inspected,
            "db_path": self.db_path,
            "api_endpoints": self.api_endpoints,
            "services": self.services,
            "entities": self.entities,
            "tables": self.tables,
            "backend_skipped": self.backend_skipped,
            "api_calls": self.api_calls,
            "field_mappings": self.field_mappings,
            "skipped_unchanged": self.skipped_unchanged,
            "changed_files": self.changed_files,
            "stats": self.stats,
        }


class FrontendIndexer:
    """Full-workspace frontend deep index without artificial file caps."""

    UI_EXTS = (".tsx", ".jsx", ".vue")

    def __init__(self, toolbox: "Code2GuideToolbox", store: GraphStore):
        self.toolbox = toolbox
        self.store = store
        self.workspace_path = toolbox.workspace_path

    def index(self, *, rebuild: bool = True) -> IndexResult:
        started = time.perf_counter()
        if rebuild:
            self.store.clear()

        nodes: List[GraphNode] = []
        edges: List[GraphEdge] = []
        items: List[IndexedItem] = []

        tree = self.toolbox.get_route_tree()
        ui_files = self._collect_ui_files(tree.routes)

        # --- Routes / pages ---
        for route in tree.routes:
            route_id = f"route:{route.path}"
            title = route.title or (route.breadcrumbs[-1] if route.breadcrumbs else route.path)
            crumbs = list(route.breadcrumbs or [])
            payload = {
                "path": route.path,
                "component_name": route.component_name,
                "breadcrumbs": crumbs,
                "title": route.title,
            }
            nodes.append(
                GraphNode(
                    id=route_id,
                    node_type=NodeType.ROUTE,
                    title=title or route.path or "",
                    file_path=route.file_path or "",
                    payload=payload,
                )
            )
            crumb_str = " > ".join(crumbs)
            items.append(
                IndexedItem(
                    id=route_id,
                    title=title or route.path or "",
                    content=" ".join(p for p in [crumb_str, route.path or "", route.component_name or "", route.title or ""] if p),
                    file_path=route.file_path or "",
                    item_type="route",
                    metadata=payload,
                )
            )
            if route.file_path and route.file_path.endswith(self.UI_EXTS):
                page_id = f"page:{route.file_path}"
                nodes.append(
                    GraphNode(
                        id=page_id,
                        node_type=NodeType.PAGE,
                        title=title or route.file_path,
                        file_path=route.file_path,
                        payload={"route_path": route.path, "component_name": route.component_name},
                    )
                )
                edges.append(
                    GraphEdge(
                        id=f"edge:renders:{route_id}:{page_id}",
                        edge_type=EdgeType.RENDERS,
                        source_id=route_id,
                        target_id=page_id,
                    )
                )

        # --- Deep AST on all UI files ---
        files_inspected = 0
        form_count = field_count = button_count = component_count = 0
        for fpath in sorted(ui_files):
            inspection = self.toolbox.inspect_component(fpath)
            if "error" in inspection:
                continue
            files_inspected += 1
            comp_name = inspection.get("component_name") or Path(fpath).stem
            comp_id = f"component:{fpath}"
            nodes.append(
                GraphNode(
                    id=comp_id,
                    node_type=NodeType.COMPONENT,
                    title=comp_name,
                    file_path=fpath,
                    payload={"component_name": comp_name},
                )
            )
            component_count += 1
            items.append(
                IndexedItem(
                    id=comp_id,
                    title=comp_name,
                    content=f"{comp_name} {fpath}",
                    file_path=fpath,
                    item_type="component",
                    metadata={"component_name": comp_name},
                )
            )

            forms = inspection.get("forms") or []
            # Promote standalone fields/buttons into a synthetic form when present
            if not forms and (inspection.get("standalone_fields") or inspection.get("standalone_buttons")):
                forms = [
                    {
                        "form_name": comp_name,
                        "file_path": fpath,
                        "fields": inspection.get("standalone_fields") or [],
                        "buttons": inspection.get("standalone_buttons") or [],
                        "start_line": 1,
                        "end_line": 1,
                    }
                ]

            for idx, form in enumerate(forms):
                form_name = form.get("form_name") or f"{comp_name}_form_{idx}"
                form_id = f"form:{fpath}:{idx}"
                form_count += 1
                nodes.append(
                    GraphNode(
                        id=form_id,
                        node_type=NodeType.FORM,
                        title=form_name,
                        file_path=fpath,
                        payload={
                            "form_name": form_name,
                            "start_line": form.get("start_line", 1),
                            "end_line": form.get("end_line", 1),
                            "validation_notes": inspection.get("validation_notes") or [],
                        },
                    )
                )
                edges.append(
                    GraphEdge(
                        id=f"edge:renders:{comp_id}:{form_id}",
                        edge_type=EdgeType.RENDERS,
                        source_id=comp_id,
                        target_id=form_id,
                    )
                )
                field_labels: List[str] = []
                for f_idx, fld in enumerate(form.get("fields") or []):
                    fname = fld.get("name") or fld.get("label") or f"field_{f_idx}"
                    field_id = f"field:{fpath}:{idx}:{f_idx}"
                    label = fld.get("label") or fname
                    field_labels.append(str(label))
                    field_count += 1
                    nodes.append(
                        GraphNode(
                            id=field_id,
                            node_type=NodeType.FORM_FIELD,
                            title=str(label),
                            file_path=fpath,
                            payload={
                                "name": fld.get("name") or "",
                                "field_type": fld.get("field_type") or "text",
                                "label": fld.get("label"),
                                "placeholder": fld.get("placeholder"),
                                "required": bool(fld.get("required")),
                                "validation_message": fld.get("validation_message"),
                                "line_number": fld.get("line_number") or 1,
                                "form_id": form_id,
                            },
                        )
                    )
                    edges.append(
                        GraphEdge(
                            id=f"edge:contains:{form_id}:{field_id}",
                            edge_type=EdgeType.CONTAINS_FIELD,
                            source_id=form_id,
                            target_id=field_id,
                        )
                    )
                    items.append(
                        IndexedItem(
                            id=field_id,
                            title=str(label),
                            content=" ".join(
                                str(x)
                                for x in [
                                    label,
                                    fld.get("name"),
                                    fld.get("placeholder"),
                                    fld.get("validation_message"),
                                    form_name,
                                    fpath,
                                ]
                                if x
                            ),
                            file_path=fpath,
                            item_type="field",
                            metadata={
                                "form_id": form_id,
                                "name": fld.get("name"),
                                "required": bool(fld.get("required")),
                                "field_type": fld.get("field_type"),
                            },
                        )
                    )

                button_labels: List[str] = []
                for b_idx, btn in enumerate(form.get("buttons") or []):
                    blabel = btn.get("label") or btn.get("name") or f"button_{b_idx}"
                    button_id = f"button:{fpath}:{idx}:{b_idx}"
                    button_labels.append(str(blabel))
                    button_count += 1
                    nodes.append(
                        GraphNode(
                            id=button_id,
                            node_type=NodeType.UI_BUTTON,
                            title=str(blabel),
                            file_path=fpath,
                            payload={
                                "label": btn.get("label") or "",
                                "name": btn.get("name"),
                                "action_type": btn.get("action_type") or "button",
                                "is_submit": bool(btn.get("is_submit")),
                                "line_number": btn.get("line_number") or 1,
                                "form_id": form_id,
                            },
                        )
                    )
                    edges.append(
                        GraphEdge(
                            id=f"edge:has_button:{form_id}:{button_id}",
                            edge_type=EdgeType.HAS_BUTTON,
                            source_id=form_id,
                            target_id=button_id,
                        )
                    )
                    items.append(
                        IndexedItem(
                            id=button_id,
                            title=str(blabel),
                            content=f"{blabel} {form_name} {fpath}",
                            file_path=fpath,
                            item_type="button",
                            metadata={
                                "form_id": form_id,
                                "is_submit": bool(btn.get("is_submit")),
                                "action_type": btn.get("action_type"),
                            },
                        )
                    )

                items.append(
                    IndexedItem(
                        id=form_id,
                        title=form_name,
                        content=" ".join([form_name, fpath, *field_labels, *button_labels]),
                        file_path=fpath,
                        item_type="form",
                        metadata={"form_name": form_name, "field_count": len(field_labels)},
                    )
                )

        # --- i18n ---
        i18n_count = 0
        translations = getattr(self.toolbox.i18n_parser, "translations", {}) or {}
        for key, value in list(translations.items())[:5000]:
            i18n_id = f"i18n:{key}"
            i18n_count += 1
            nodes.append(
                GraphNode(
                    id=i18n_id,
                    node_type=NodeType.I18N_STRING,
                    title=str(value),
                    file_path="",
                    payload={"key": key, "locale": "fa", "value": value},
                )
            )
            items.append(
                IndexedItem(
                    id=i18n_id,
                    title=str(value),
                    content=f"{key} {value}",
                    file_path="",
                    item_type="i18n",
                    metadata={"key": key, "locale": "fa"},
                )
            )

        self.store.upsert_nodes(nodes)
        self.store.upsert_edges(edges)

        self.toolbox.hybrid_indexer.index_items(items, rebuild=rebuild)
        self.toolbox._indexed = True

        duration_ms = (time.perf_counter() - started) * 1000.0
        result = IndexResult(
            workspace_path=str(Path(self.workspace_path).resolve()),
            duration_ms=round(duration_ms, 2),
            routes=len(tree.routes),
            components=component_count,
            forms=form_count,
            form_fields=field_count,
            ui_buttons=button_count,
            i18n_strings=i18n_count,
            edges=len(edges),
            indexed_count=len(items),
            use_vector=bool(self.toolbox.hybrid_indexer.use_vector),
            collection_name=self.toolbox.hybrid_indexer.collection_name,
            files_inspected=files_inspected,
            db_path=str(self.store.db_path),
            stats={
                "ui_files": len(ui_files),
                "files_inspected": files_inspected,
                "hybrid_items": len(items),
            },
        )
        self.store.mark_indexed(result.to_dict())
        return result

    def _collect_ui_files(self, routes) -> Set[str]:
        ws_root = Path(self.workspace_path).resolve()
        files: Set[str] = set()

        for route in routes:
            fpath = (route.file_path or "").replace("\\", "/")
            if not fpath:
                continue
            if fpath.endswith(self.UI_EXTS):
                files.add(fpath)
                files.update(self._imports_from_file(fpath, ws_root))
            # Resolve component file if route points at a router file
            if route.component_name:
                resolved = self.toolbox.route_extractor._resolve_component_file(
                    ws_root, route.component_name
                )
                if resolved and resolved.endswith(self.UI_EXTS):
                    files.add(resolved)
                    files.update(self._imports_from_file(resolved, ws_root))

        # Also include all page/view UI files under common dirs (still no hard 6-cap)
        for pattern in ("**/pages/**/*.tsx", "**/pages/**/*.jsx", "**/views/**/*.tsx", "**/views/**/*.jsx"):
            for p in ws_root.glob(pattern):
                if any(skip in str(p) for skip in ("node_modules", ".git", "dist", "build")):
                    continue
                try:
                    files.add(str(p.relative_to(ws_root)).replace("\\", "/"))
                except ValueError:
                    pass

        return files

    def _imports_from_file(self, rel_path: str, ws_root: Path) -> Set[str]:
        found: Set[str] = set()
        full = ws_root / rel_path
        if not full.exists():
            return found
        try:
            code = full.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return found
        for m in re.finditer(r"""from\s+['"]([^'"]+)['"]""", code):
            import_path = m.group(1)
            if not (import_path.startswith(".") or import_path.startswith("@/") or import_path.startswith("~/")):
                continue
            resolved = self.toolbox.resolve_import_path(import_path, rel_path)
            if resolved and resolved.endswith(self.UI_EXTS):
                found.add(resolved.replace("\\", "/"))
        return found
