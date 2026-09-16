"""Route & Menu Tree Extractor for React Router and Next.js applications.

Scans codebase for route definitions, sidebar navigation structures, and page hierarchies,
mapping them into navigable breadcrumb paths (مسیر دسترسی).
Fully cross-platform compatible with Windows and Unix path separators.
"""

import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from src.core.normalizer import PersianNormalizer, default_normalizer


class RouteNode(BaseModel):
    """Represents a single route or navigation menu item."""
    path: str = Field(description="URL path, e.g. /tenders/create")
    title: Optional[str] = Field(default=None, description="Persian menu or page title")
    component_name: Optional[str] = Field(default=None, description="React component name")
    file_path: Optional[str] = Field(default=None, description="Relative file path")
    breadcrumbs: List[str] = Field(default_factory=list, description="Step-by-step UX breadcrumb trail")
    children: List["RouteNode"] = Field(default_factory=list)


# Self-referential model rebuild for Pydantic v2 and v1
if hasattr(RouteNode, "model_rebuild"):
    RouteNode.model_rebuild()
elif hasattr(RouteNode, "update_forward_refs"):
    RouteNode.update_forward_refs()


class RouteTree(BaseModel):
    """Collection of scanned routes and resolved navigation paths."""
    routes: List[RouteNode] = Field(default_factory=list)
    component_to_route: Dict[str, RouteNode] = Field(default_factory=dict)
    path_to_route: Dict[str, RouteNode] = Field(default_factory=dict)


class RouteExtractor:
    """Extracts enterprise routing trees from React Router, Next.js, and sidebar config files."""

    ROUTE_FILE_PATTERNS = [
        "routes.tsx", "routes.ts", "routes.jsx", "routes.js",
        "App.tsx", "App.jsx", "router.tsx", "router.ts",
        "navigation.ts", "navigation.tsx", "menu.ts", "menu.tsx",
        "sidebar.ts", "sidebar.tsx", "nav.ts", "nav.tsx"
    ]

    def __init__(self, normalizer: Optional[PersianNormalizer] = None):
        self.normalizer = normalizer or default_normalizer

    def scan_workspace(self, workspace_path: str) -> RouteTree:
        """Discovers routes and menu trees across the entire target workspace."""
        root = Path(workspace_path).resolve()
        if not root.exists():
            return RouteTree()

        routes: List[RouteNode] = []
        path_map: Dict[str, RouteNode] = {}
        comp_map: Dict[str, RouteNode] = {}

        next_routes = self._scan_nextjs_routes(root)
        for r in next_routes:
            routes.append(r)
            path_map[r.path] = r
            if r.component_name:
                comp_map[r.component_name] = r

        for dirpath, _, filenames in os.walk(root):
            norm_dir = dirpath.replace("\\", "/")
            if any(p in norm_dir for p in ["/node_modules", "/.git", "/.next", "/dist", "/build"]):
                continue

            for fname in filenames:
                lower_name = fname.lower()
                if any(lower_name == pattern.lower() or "route" in lower_name or "menu" in lower_name or "nav" in lower_name for pattern in self.ROUTE_FILE_PATTERNS):
                    fpath = os.path.join(dirpath, fname)
                    rel_path = os.path.relpath(fpath, root).replace("\\", "/")
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="replace") as f_in:
                            file_content = f_in.read()

                        file_routes = self._parse_route_file(file_content, rel_path)
                        for fr in file_routes:
                            if fr.path not in path_map:
                                routes.append(fr)
                                path_map[fr.path] = fr
                            else:
                                existing = path_map[fr.path]
                                if fr.title and not existing.title:
                                    existing.title = fr.title
                                if fr.component_name and not existing.component_name:
                                    existing.component_name = fr.component_name

                            if fr.component_name:
                                comp_map[fr.component_name] = path_map[fr.path]
                    except Exception:
                        continue

        self._enrich_breadcrumbs(routes)

        return RouteTree(
            routes=routes,
            component_to_route=comp_map,
            path_to_route=path_map
        )

    def _scan_nextjs_routes(self, root: Path) -> List[RouteNode]:
        routes: List[RouteNode] = []
        app_dir = root / "app"
        if app_dir.is_dir():
            for p in app_dir.rglob("page.[jt]sx"):
                rel_parts = p.relative_to(app_dir).parts[:-1]
                url_path = "/" + "/".join(rel_parts) if rel_parts else "/"
                comp = p.parent.name.capitalize() + "Page"
                rel_file = str(p.relative_to(root)).replace("\\", "/")
                routes.append(
                    RouteNode(
                        path=url_path,
                        title=None,
                        component_name=comp,
                        file_path=rel_file,
                        breadcrumbs=["صفحه اصلی"] + [part.capitalize() for part in rel_parts]
                    )
                )

        pages_dir = root / "pages"
        if pages_dir.is_dir():
            for p in pages_dir.rglob("*.[jt]sx"):
                if p.name.startswith("_") or p.name.startswith("api"):
                    continue
                rel_parts = list(p.relative_to(pages_dir).parts)
                rel_parts[-1] = os.path.splitext(rel_parts[-1])[0]
                if rel_parts[-1] == "index":
                    rel_parts.pop()
                url_path = "/" + "/".join(rel_parts) if rel_parts else "/"
                comp = (rel_parts[-1].capitalize() if rel_parts else "Index") + "Page"
                rel_file = str(p.relative_to(root)).replace("\\", "/")
                routes.append(
                    RouteNode(
                        path=url_path,
                        title=None,
                        component_name=comp,
                        file_path=rel_file,
                        breadcrumbs=["صفحه اصلی"] + [part.capitalize() for part in rel_parts]
                    )
                )

        return routes

    def _parse_route_file(self, content: str, file_path: str) -> List[RouteNode]:
        results: List[RouteNode] = []
        by_path: Dict[str, RouteNode] = {}

        # 1. Parse menu navigation configs
        menu_items = self._extract_nav_items(content, file_path)
        for mi in menu_items:
            results.append(mi)
            by_path[mi.path] = mi

        # 2. JSX <Route path="..." element={<Component />} />
        route_jsx = re.finditer(
            r'<Route\b(?P<attrs>[^>]*)>',
            content,
            re.IGNORECASE
        )
        for m in route_jsx:
            attrs = m.group("attrs")
            path_m = re.search(r'path\s*=\s*["\']([^"\']+)["\']', attrs)
            elem_m = re.search(r'element\s*=\s*\{<([A-Za-z0-9_]+)', attrs)
            comp_m = re.search(r'component\s*=\s*\{?([A-Za-z0-9_]+)\}?', attrs)

            url_path = path_m.group(1) if path_m else None
            comp_name = (elem_m.group(1) if elem_m else None) or (comp_m.group(1) if comp_m else None)

            if url_path:
                if url_path in by_path:
                    if comp_name:
                        by_path[url_path].component_name = comp_name
                else:
                    rn = RouteNode(
                        path=url_path,
                        component_name=comp_name,
                        file_path=file_path,
                        breadcrumbs=["منوی اصلی", url_path.strip("/")]
                    )
                    results.append(rn)
                    by_path[url_path] = rn

        return results

    def _extract_nav_items(self, content: str, file_path: str) -> List[RouteNode]:
        nodes: List[RouteNode] = []
        seen_paths: set = set()

        leaf_pattern = re.finditer(
            r'\{\s*[^{}]*?(?:title|label|name)\s*:\s*(?:["\'](?P<title>[^"\']+)["\']|t\(["\'](?P<i18n>[^"\']+)["\']\))[^{}]*?(?:path|href|url|to)\s*:\s*["\'](?P<path>[^"\']+)["\'][^{}]*?\}',
            content,
            re.MULTILINE | re.DOTALL
        )
        for m in leaf_pattern:
            raw_title = m.group("title") or m.group("i18n") or ""
            path = m.group("path")
            norm_title = self.normalizer.normalize(raw_title)
            if path not in seen_paths:
                seen_paths.add(path)
                nodes.append(
                    RouteNode(
                        path=path,
                        title=norm_title,
                        file_path=file_path,
                        breadcrumbs=["منوی اصلی", norm_title]
                    )
                )

        leaf_rev_pattern = re.finditer(
            r'\{\s*[^{}]*?(?:path|href|url|to)\s*:\s*["\'](?P<path>[^"\']+)["\'][^{}]*?(?:title|label|name)\s*:\s*(?:["\'](?P<title>[^"\']+)["\']|t\(["\'](?P<i18n>[^"\']+)["\']\))[^{}]*?\}',
            content,
            re.MULTILINE | re.DOTALL
        )
        for m in leaf_rev_pattern:
            raw_title = m.group("title") or m.group("i18n") or ""
            path = m.group("path")
            norm_title = self.normalizer.normalize(raw_title)
            if path not in seen_paths:
                seen_paths.add(path)
                nodes.append(
                    RouteNode(
                        path=path,
                        title=norm_title,
                        file_path=file_path,
                        breadcrumbs=["منوی اصلی", norm_title]
                    )
                )

        parent_pattern = re.finditer(
            r'(?:title|label|name)\s*:\s*["\'](?P<title>[^"\']+)["\'].*?(?:path|href|url|to)\s*:\s*["\'](?P<path>[^"\']+)["\']',
            content,
            re.MULTILINE | re.DOTALL
        )
        for m in parent_pattern:
            raw_title = m.group("title")
            path = m.group("path")
            norm_title = self.normalizer.normalize(raw_title)
            if path not in seen_paths:
                seen_paths.add(path)
                nodes.append(
                    RouteNode(
                        path=path,
                        title=norm_title,
                        file_path=file_path,
                        breadcrumbs=["منوی اصلی", norm_title]
                    )
                )

        return nodes

    def _enrich_breadcrumbs(self, routes: List[RouteNode]):
        titles_by_path: Dict[str, str] = {
            r.path.rstrip("/"): r.title for r in routes if r.title
        }

        for r in routes:
            segments = [s for s in r.path.strip("/").split("/") if s]
            crumbs = ["منوی اصلی"]
            cur_p = ""
            for seg in segments:
                cur_p += "/" + seg
                if cur_p in titles_by_path and titles_by_path[cur_p]:
                    crumbs.append(titles_by_path[cur_p])
                else:
                    crumbs.append(seg)
            if r.title and r.title not in crumbs:
                crumbs.append(r.title)
            r.breadcrumbs = crumbs

    def find_route_by_query(self, tree: RouteTree, query: str) -> List[RouteNode]:
        norm_q = self.normalizer.clean_search_query(query).lower()
        q_words = set(w for w in norm_q.split() if len(w) > 1)
        scored_routes: List[tuple[int, RouteNode]] = []

        for r in tree.routes:
            score = 0
            t_clean = (r.title or "").lower()
            p_clean = (r.path or "").lower()
            c_clean = (r.component_name or "").lower()

            if t_clean and norm_q in t_clean:
                score += 10
            if c_clean and norm_q in c_clean:
                score += 8
            if p_clean and norm_q in p_clean:
                score += 5

            if t_clean:
                t_words = set(t_clean.split())
                common = q_words.intersection(t_words)
                score += len(common) * 4

            if any(q_words.intersection(set(b.lower().split())) for b in r.breadcrumbs):
                score += 2

            if score > 0:
                scored_routes.append((score, r))

        scored_routes.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored_routes]
