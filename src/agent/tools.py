"""ReAct Agent tools for codebase UX discovery.

Provides tools for lexical Persian label search, component AST inspection,
and routing hierarchy resolution — plus alias/i18n/validation/OpenAPI helpers.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional

from src.core.config import settings
from src.core.normalizer import default_normalizer
from src.search.lexical_engine import RipgrepLexicalEngine
from src.parsers.ast_visitor import JSXASTVisitor, UIField, DiscoveredForm
from src.parsers.route_extractor import RouteExtractor, RouteTree
from src.parsers.alias_resolver import PathAliasResolver
from src.parsers.i18n_parser import I18nParser
from src.parsers.validation_parser import ValidationParser, ValidationRule
from src.parsers.openapi_parser import BackendContractExtractor, EndpointRequirement

try:
    from langchain_core.tools import tool
except ImportError:
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
        self.alias_resolver = PathAliasResolver(self.workspace_path)
        self.i18n_parser = I18nParser(self.workspace_path)
        self.contract_extractor = BackendContractExtractor(self.workspace_path)
        self._cached_route_tree: Optional[RouteTree] = None

    def get_route_tree(self) -> RouteTree:
        """Caches and returns the workspace route tree (enriched with pageLabels when missing)."""
        if self._cached_route_tree is None:
            tree = self.route_extractor.scan_workspace(self.workspace_path)
            for route in tree.routes:
                if not route.title:
                    page_id = (route.path or "").lstrip("/")
                    label = self.i18n_parser.label_for_page_id(page_id)
                    if label:
                        route.title = label
            self.route_extractor._enrich_breadcrumbs(tree.routes)
            self._cached_route_tree = tree
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
            # Try alias/relative resolution if a bare import-like path was passed
            resolved = self.alias_resolver.resolve_import(file_path, Path(self.workspace_path))
            if resolved and resolved.exists():
                full_path = resolved
                try:
                    file_path = str(resolved.relative_to(Path(self.workspace_path).resolve())).replace("\\", "/")
                except ValueError:
                    pass
            else:
                return {
                    "file_path": file_path,
                    "error": f"File not found: {file_path}",
                    "forms": [],
                    "validation_rules": [],
                    "validation_notes": [],
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

            # Expand i18n t('...') before AST so labels become Persian literals
            prepared = self.i18n_parser.replace_i18n_calls(snippet)
            validation_rules = ValidationParser.extract_all(prepared)
            inspection = self.ast_visitor.parse_source(prepared, file_path=file_path)

            # Merge schema/RHF required flags onto discovered fields
            self._merge_validation_into_forms(inspection.forms, validation_rules)
            if inspection.standalone_fields:
                self._merge_validation_into_fields(inspection.standalone_fields, validation_rules)

            forms_data = [dump_model(f) for f in inspection.forms]
            fields_data = [dump_model(f) for f in inspection.standalone_fields]
            buttons_data = [dump_model(b) for b in inspection.standalone_buttons]
            rules_data = [dump_model(r) for r in validation_rules.values()]
            notes = ValidationParser.as_notes(validation_rules)

            return {
                "file_path": file_path,
                "component_name": inspection.component_name,
                "forms": forms_data,
                "standalone_fields": fields_data,
                "standalone_buttons": buttons_data,
                "validation_rules": rules_data,
                "validation_notes": notes,
                "total_lines": len(lines),
            }
        except Exception as e:
            return {
                "file_path": file_path,
                "error": str(e),
                "forms": [],
                "validation_rules": [],
                "validation_notes": [],
            }

    @staticmethod
    def _merge_validation_into_fields(
        fields: List[UIField],
        rules: Dict[str, ValidationRule],
    ) -> None:
        for field in fields:
            key = field.name
            if not key or key not in rules:
                continue
            rule = rules[key]
            if rule.is_required:
                field.required = True
            if rule.error_message and not field.validation_message:
                field.validation_message = rule.error_message

    @classmethod
    def _merge_validation_into_forms(
        cls,
        forms: List[DiscoveredForm],
        rules: Dict[str, ValidationRule],
    ) -> None:
        for form in forms:
            cls._merge_validation_into_fields(form.fields, rules)
            # Add schema-only fields missing from JSX
            existing = {f.name for f in form.fields if f.name}
            for name, rule in rules.items():
                if name in existing:
                    continue
                form.fields.append(
                    UIField(
                        name=name,
                        field_type="text",
                        label=name,
                        required=rule.is_required,
                        validation_message=rule.error_message,
                    )
                )

    def resolve_import_path(self, import_str: str, from_file: str) -> Optional[str]:
        """Resolve TS/JS import to a workspace-relative path."""
        from_path = Path(self.workspace_path) / from_file
        return self.alias_resolver.resolve_to_relative(import_str, from_path)

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
            "routes": routes_data,
        }

    def roles_for_routes(self, route_paths: List[str]) -> List[str]:
        roles: List[str] = []
        seen = set()
        for path in route_paths:
            for role in self.contract_extractor.roles_for_page_id(path):
                if role not in seen:
                    seen.add(role)
                    roles.append(role)
        return roles

    def related_api_endpoints(self, query: str, limit: int = 8) -> List[EndpointRequirement]:
        """Pick OpenAPI endpoints loosely related to the query keywords."""
        endpoints = self.contract_extractor.scan_rbac_and_swagger()
        q = (query or "").lower()
        keywords = [w for w in self.normalizer.extract_keywords(query) if len(w) > 2]
        scored = []
        for ep in endpoints:
            blob = f"{ep.path} {ep.method} {ep.summary or ''} {' '.join(ep.request_dto_fields)}".lower()
            score = 0
            if q and q in blob:
                score += 5
            for kw in keywords:
                if kw.lower() in blob:
                    score += 2
            if score > 0:
                scored.append((score, ep))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [ep for _, ep in scored[:limit]]


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
