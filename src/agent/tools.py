"""ReAct Agent tools for codebase UX discovery.

Provides tools for lexical Persian label search, component AST inspection,
and routing hierarchy resolution.
"""

import os
from pathlib import Path
from typing import List, Dict, Any, Optional

from src.core.config import settings
from src.core.normalizer import default_normalizer
from src.search.lexical_engine import RipgrepLexicalEngine, SearchResult
from src.parsers.ast_visitor import JSXASTVisitor, ComponentInspection
from src.parsers.route_extractor import RouteExtractor, RouteTree, RouteNode

try:
    from langchain_core.tools import tool
    _has_langchain_tool = True
except ImportError:
    _has_langchain_tool = False
    def tool(fn):
        return fn


def dump_model(obj: Any) -> Dict[str, Any]:
    """Serializes pydantic model in both v1 and v2."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return obj.dict()


class Code2GuideToolbox:
    """Toolbox encapsulating workspace state and execution helpers."""

    def __init__(self, workspace_path: Optional[str] = None):
        self.workspace_path = workspace_path or settings.target_workspace_path
        self.normalizer = default_normalizer
        self.lexical_engine = RipgrepLexicalEngine(self.workspace_path, normalizer=self.normalizer)
        self.ast_visitor = JSXASTVisitor(normalizer=self.normalizer)
        self.route_extractor = RouteExtractor(normalizer=self.normalizer)
        self._cached_route_tree: Optional[RouteTree] = None

    def get_route_tree(self) -> RouteTree:
        """Caches and returns the workspace route tree."""
        if self._cached_route_tree is None:
            self._cached_route_tree = self.route_extractor.scan_workspace(self.workspace_path)
        return self._cached_route_tree

    def search_persian_labels(self, query: str, max_results: int = 15) -> Dict[str, Any]:
        """Searches localized Persian strings, buttons, and placeholders in the codebase."""
        res = self.lexical_engine.search(query, max_results=max_results)
        matches_data = [
            {
                "file_path": m.file_path,
                "line_number": m.line_number,
                "line_content": m.line_content,
                "context_before": m.context_before,
                "context_after": m.context_after,
            }
            for m in res.matches
        ]
        return {
            "query": query,
            "normalized_query": res.normalized_query,
            "matches_count": res.matches_count,
            "engine_used": res.engine_used,
            "matches": matches_data,
        }

    def inspect_component(
        self,
        file_path: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None
    ) -> Dict[str, Any]:
        """Reads and parses a JSX/TSX/Vue UI component into forms, fields, and buttons."""
        full_path = Path(self.workspace_path) / file_path
        if not full_path.exists():
            return {
                "file_path": file_path,
                "error": f"File not found: {file_path}",
                "forms": []
            }

        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            if start_line is not None and end_line is not None:
                start_idx = max(0, start_line - 1)
                end_idx = min(len(lines), end_line)
                snippet = "".join(lines[start_idx:end_idx])
            else:
                snippet = "".join(lines)

            inspection = self.ast_visitor.parse_source(snippet, file_path=file_path)
            forms_data = [dump_model(f) for f in inspection.forms]
            fields_data = [dump_model(f) for f in inspection.standalone_fields]
            buttons_data = [dump_model(b) for b in inspection.standalone_buttons]

            return {
                "file_path": file_path,
                "component_name": inspection.component_name,
                "forms": forms_data,
                "standalone_fields": fields_data,
                "standalone_buttons": buttons_data,
                "total_lines": len(lines)
            }
        except Exception as e:
            return {
                "file_path": file_path,
                "error": str(e),
                "forms": []
            }

    def get_route_hierarchy(self, component_or_title: str) -> Dict[str, Any]:
        """Finds the navigation path and breadcrumbs to a page or component."""
        tree = self.get_route_tree()
        matched_routes = self.route_extractor.find_route_by_query(tree, component_or_title)

        routes_data = [dump_model(r) for r in matched_routes]
        best_breadcrumbs = []
        if matched_routes:
            best_breadcrumbs = matched_routes[0].breadcrumbs

        return {
            "query": component_or_title,
            "matched_count": len(matched_routes),
            "best_breadcrumbs": best_breadcrumbs,
            "routes": routes_data
        }


_default_toolbox = Code2GuideToolbox()

@tool
def search_persian_labels(query: str, workspace_path: Optional[str] = None) -> Dict[str, Any]:
    """Searches localized Persian strings, buttons, and placeholders in the codebase."""
    tb = Code2GuideToolbox(workspace_path) if workspace_path else _default_toolbox
    return tb.search_persian_labels(query)

@tool
def inspect_component(
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    workspace_path: Optional[str] = None
) -> Dict[str, Any]:
    """Reads and parses a JSX/TSX/Vue UI component into forms, fields, and buttons."""
    tb = Code2GuideToolbox(workspace_path) if workspace_path else _default_toolbox
    return tb.inspect_component(file_path, start_line, end_line)

@tool
def get_route_hierarchy(component_name: str, workspace_path: Optional[str] = None) -> Dict[str, Any]:
    """Finds the navigation path and breadcrumbs to a page or component."""
    tb = Code2GuideToolbox(workspace_path) if workspace_path else _default_toolbox
    return tb.get_route_hierarchy(component_name)
