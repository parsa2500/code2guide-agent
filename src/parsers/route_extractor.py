"""Route & Menu Tree Extractor for React Router, Next.js, and SPA PageId apps.

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
    """Extracts enterprise routing trees from React Router, Next.js, and SPA PageId menus."""

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
                if any(
                    lower_name == pattern.lower()
                    or "route" in lower_name
                    or "menu" in lower_name
                    or "nav" in lower_name
                    for pattern in self.ROUTE_FILE_PATTERNS
                ):
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
                                if fr.file_path and self._is_page_component_path(fr.file_path):
                                    existing.file_path = fr.file_path

                            if fr.component_name:
                                comp_map[fr.component_name] = path_map[fr.path]
                    except Exception:
                        continue

        self._resolve_route_component_files(root, routes)
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

        def upsert(node: RouteNode):
            if node.path in by_path:
                existing = by_path[node.path]
                if node.title and not existing.title:
                    existing.title = node.title
                if node.component_name and not existing.component_name:
                    existing.component_name = node.component_name
                if node.file_path and (
                    not existing.file_path
                    or self._is_page_component_path(node.file_path)
                ):
                    existing.file_path = node.file_path
            else:
                results.append(node)
                by_path[node.path] = node

        # 1. Classic menu navigation configs (title/label + path/href)
        for mi in self._extract_nav_items(content, file_path):
            upsert(mi)

        # 2. SPA PageId menus (id + LabelFa / LabelEn)
        for mi in self._extract_label_fa_nav_items(content, file_path):
            upsert(mi)

        # 3. App.tsx / SPA switch (case "page-id": return <Component />)
        for page_id, comp_name in self._extract_page_switch_map(content).items():
            url_path = "/" + page_id.lstrip("/")
            upsert(
                RouteNode(
                    path=url_path,
                    title=None,
                    component_name=comp_name,
                    file_path=file_path,
                    breadcrumbs=["منوی اصلی", page_id],
                )
            )

        # 4. JSX <Route path="..." element={<Component />} />
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
                upsert(
                    RouteNode(
                        path=url_path,
                        component_name=comp_name,
                        file_path=file_path,
                        breadcrumbs=["منوی اصلی", url_path.strip("/")]
                    )
                )

        return results

    def _extract_label_fa_nav_items(self, content: str, file_path: str) -> List[RouteNode]:
        """Parse SPA sidebar items shaped like { id, LabelFa, LabelEn }."""
        nodes: List[RouteNode] = []
        seen_paths: set = set()

        patterns = [
            # id first, then LabelFa (LabelEn optional anywhere after id block start handled loosely)
            re.compile(
                r'\{\s*[^{}]*?\bid\s*:\s*["\'](?P<id>[^"\']+)["\']'
                r'[^{}]*?LabelFa\s*:\s*["\'](?P<fa>[^"\']+)["\']'
                r'(?:[^{}]*?LabelEn\s*:\s*["\'](?P<en>[^"\']+)["\'])?'
                r'[^{}]*?\}',
                re.MULTILINE | re.DOTALL,
            ),
            # LabelFa first, then id
            re.compile(
                r'\{\s*[^{}]*?LabelFa\s*:\s*["\'](?P<fa>[^"\']+)["\']'
                r'[^{}]*?\bid\s*:\s*["\'](?P<id>[^"\']+)["\']'
                r'(?:[^{}]*?LabelEn\s*:\s*["\'](?P<en>[^"\']+)["\'])?'
                r'[^{}]*?\}',
                re.MULTILINE | re.DOTALL,
            ),
            # id + LabelEn only (no LabelFa)
            re.compile(
                r'\{\s*[^{}]*?\bid\s*:\s*["\'](?P<id>[^"\']+)["\']'
                r'[^{}]*?LabelEn\s*:\s*["\'](?P<en>[^"\']+)["\']'
                r'[^{}]*?\}',
                re.MULTILINE | re.DOTALL,
            ),
        ]

        for pattern in patterns:
            for m in pattern.finditer(content):
                page_id = m.groupdict().get("id") or ""
                if not page_id:
                    continue
                # Skip commented-out blocks (simple heuristic)
                block_start = m.start()
                line_start = content.rfind("\n", 0, block_start) + 1
                prefix = content[line_start:block_start]
                if "//" in prefix:
                    continue

                fa = m.groupdict().get("fa")
                en = m.groupdict().get("en")
                raw_title = fa or en or page_id
                url_path = "/" + page_id.lstrip("/")
                if url_path in seen_paths:
                    continue
                seen_paths.add(url_path)
                norm_title = self.normalizer.normalize(raw_title)
                nodes.append(
                    RouteNode(
                        path=url_path,
                        title=norm_title,
                        file_path=file_path,
                        breadcrumbs=["منوی اصلی", norm_title],
                    )
                )

        return nodes

    def _extract_page_switch_map(self, content: str) -> Dict[str, str]:
        """Map PageId → component from `case "id": return <Component ...>` switches."""
        mapping: Dict[str, str] = {}
        for m in re.finditer(r'case\s+["\'](?P<id>[^"\']+)["\']\s*:', content):
            page_id = m.group("id")
            window = content[m.end(): m.end() + 800]
            # Stop at next case/default to avoid grabbing the wrong component
            next_case = re.search(r'\bcase\s+["\']|\bdefault\s*:', window)
            if next_case:
                window = window[: next_case.start()]

            comp_m = re.search(
                r'return\s*(?:\([\s\n]*)?<([A-Z][A-Za-z0-9_]*)',
                window,
                re.MULTILINE | re.DOTALL,
            )
            if not comp_m:
                continue
            mapping[page_id] = comp_m.group(1)
        return mapping

    def _is_page_component_path(self, file_path: str) -> bool:
        lower = file_path.replace("\\", "/").lower()
        return lower.endswith((".tsx", ".jsx", ".vue")) and (
            "/pages/" in lower or lower.endswith("page.tsx") or lower.endswith("page.jsx")
        )

    def _resolve_component_file(self, root: Path, component_name: str) -> Optional[str]:
        """Find ComponentName.tsx under workspace, preferring src/pages/ (skips heavy dirs)."""
        if not component_name:
            return None

        skip_dir_names = {"node_modules", ".git", ".next", "dist", "build", ".venv", "venv"}
        search_roots = []
        for candidate in (root / "src" / "pages", root / "src", root):
            if candidate.is_dir() and candidate not in search_roots:
                search_roots.append(candidate)

        candidates: List[Path] = []
        for search_root in search_roots:
            for dirpath, dirnames, filenames in os.walk(search_root):
                dirnames[:] = [d for d in dirnames if d not in skip_dir_names]
                for ext in (".tsx", ".jsx", ".ts", ".js"):
                    target = f"{component_name}{ext}"
                    if target in filenames:
                        candidates.append(Path(dirpath) / target)
            if candidates:
                break

        if not candidates:
            return None

        def sort_key(p: Path):
            norm = str(p).replace("\\", "/").lower()
            prefer_pages = 0 if "/pages/" in norm else 1
            prefer_src = 0 if "/src/" in norm else 1
            return (prefer_pages, prefer_src, len(norm))

        candidates.sort(key=sort_key)
        return str(candidates[0].relative_to(root)).replace("\\", "/")

    def _resolve_route_component_files(self, root: Path, routes: List[RouteNode]) -> None:
        for r in routes:
            if not r.component_name:
                continue
            if r.file_path and self._is_page_component_path(r.file_path):
                continue
            resolved = self._resolve_component_file(root, r.component_name)
            if resolved:
                r.file_path = resolved

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
