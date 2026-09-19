"""Trace frontend HTTP client calls (fetch / axios / React Query / RTK)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Optional, Set
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from src.parsers.stack_detector import DOTNET_SKIP_DIRS


class FrontendApiCall(BaseModel):
    """A discovered HTTP call in frontend source."""

    file_path: str
    method: str = "GET"
    url_raw: str = ""
    url_normalized: str = ""
    line_number: int = 1
    kind: str = "fetch"  # fetch | axios | react_query | rtk


class FrontendApiTracer:
    """Regex-based extraction of API calls from TS/JS sources."""

    SKIP = DOTNET_SKIP_DIRS | {"__tests__", "coverage"}
    EXTS = (".ts", ".tsx", ".js", ".jsx")

    def scan_workspace(self, workspace_path: str) -> List[FrontendApiCall]:
        root = Path(workspace_path).resolve()
        calls: List[FrontendApiCall] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in self.SKIP]
            for name in filenames:
                if not name.lower().endswith(self.EXTS):
                    continue
                path = Path(dirpath) / name
                try:
                    content = path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                try:
                    rel = str(path.relative_to(root)).replace("\\", "/")
                except ValueError:
                    continue
                calls.extend(self.parse_file(content, rel))
        return calls

    def parse_file(self, content: str, file_path: str = "") -> List[FrontendApiCall]:
        calls: List[FrontendApiCall] = []
        calls.extend(self._parse_fetch(content, file_path))
        calls.extend(self._parse_axios(content, file_path))
        calls.extend(self._parse_react_query_style(content, file_path))
        return calls

    def _parse_fetch(self, content: str, file_path: str) -> List[FrontendApiCall]:
        out: List[FrontendApiCall] = []
        # fetch('/api/...', { method: 'POST' })
        for m in re.finditer(
            r"""\bfetch\s*\(\s*(['"`])(?P<url>.*?)\1\s*(?:,\s*\{(?P<opts>[^{}]*(?:\{[^{}]*\}[^{}]*)*)\})?""",
            content,
            re.DOTALL,
        ):
            url_raw = m.group("url")
            opts = m.group("opts") or ""
            method = "GET"
            mm = re.search(r"""method\s*:\s*['"](\w+)['"]""", opts, re.I)
            if mm:
                method = mm.group(1).upper()
            elif re.search(r"""\bbody\s*:""", opts):
                method = "POST"
            line = content[: m.start()].count("\n") + 1
            out.append(
                FrontendApiCall(
                    file_path=file_path,
                    method=method,
                    url_raw=url_raw,
                    url_normalized=self.normalize_url(url_raw),
                    line_number=line,
                    kind="fetch",
                )
            )
        return out

    def _parse_axios(self, content: str, file_path: str) -> List[FrontendApiCall]:
        out: List[FrontendApiCall] = []
        for m in re.finditer(
            r"""\baxios\.(?P<method>get|post|put|delete|patch)\s*\(\s*(['"`])(?P<url>.*?)\2""",
            content,
            re.I,
        ):
            method = m.group("method").upper()
            url_raw = m.group("url")
            line = content[: m.start()].count("\n") + 1
            out.append(
                FrontendApiCall(
                    file_path=file_path,
                    method=method,
                    url_raw=url_raw,
                    url_normalized=self.normalize_url(url_raw),
                    line_number=line,
                    kind="axios",
                )
            )
        for m in re.finditer(
            r"""\baxios\s*\(\s*\{(?P<body>[^{}]*)\}""",
            content,
            re.DOTALL,
        ):
            body = m.group("body")
            url_m = re.search(r"""(?:url|baseURL)\s*:\s*['"`]([^'"`]+)['"`]""", body)
            method_m = re.search(r"""method\s*:\s*['"`](\w+)['"`]""", body, re.I)
            if not url_m:
                continue
            url_raw = url_m.group(1)
            method = (method_m.group(1).upper() if method_m else "GET")
            line = content[: m.start()].count("\n") + 1
            out.append(
                FrontendApiCall(
                    file_path=file_path,
                    method=method,
                    url_raw=url_raw,
                    url_normalized=self.normalize_url(url_raw),
                    line_number=line,
                    kind="axios",
                )
            )
        return out

    def _parse_react_query_style(self, content: str, file_path: str) -> List[FrontendApiCall]:
        out: List[FrontendApiCall] = []
        # query: () => fetch(...) already covered; also url: '/api/...'
        for m in re.finditer(
            r"""(?:query|mutation|url)\s*:\s*(?:\(\)\s*=>\s*)?(?:fetch\s*\()?\s*(['"`])(?P<url>/[^'"`]+)\1""",
            content,
        ):
            url_raw = m.group("url")
            # Skip if already captured as fetch nearby
            line = content[: m.start()].count("\n") + 1
            window = content[max(0, m.start() - 80) : m.end() + 80]
            method = "GET"
            if re.search(r"useMutation|mutation|method\s*:\s*['\"]POST", window, re.I):
                method = "POST"
            out.append(
                FrontendApiCall(
                    file_path=file_path,
                    method=method,
                    url_raw=url_raw,
                    url_normalized=self.normalize_url(url_raw),
                    line_number=line,
                    kind="react_query",
                )
            )
        return out

    @staticmethod
    def normalize_url(url: str) -> str:
        """Strip origin/query; convert ${id} / :id templates to {id}."""
        raw = (url or "").strip()
        if not raw:
            return ""
        # template literals leftovers
        raw = re.sub(r"\$\{[^}]+\}", "{id}", raw)
        raw = re.sub(r":([A-Za-z_][\w]*)", r"{\1}", raw)
        if "://" in raw:
            try:
                parsed = urlparse(raw)
                path = parsed.path or "/"
            except Exception:
                path = raw
        else:
            path = raw.split("?")[0].split("#")[0]
        if not path.startswith("/"):
            path = "/" + path
        path = re.sub(r"/{2,}", "/", path)
        # drop trailing slash except root
        if len(path) > 1 and path.endswith("/"):
            path = path.rstrip("/")
        return path

    @staticmethod
    def match_endpoint(
        method: str,
        url_normalized: str,
        api_nodes: List,
    ) -> Optional[str]:
        """Return api node id if method+path matches (case-insensitive path)."""
        method_u = (method or "GET").upper()
        target = (url_normalized or "").lower()
        target_pat = re.sub(r"\{[^}]+\}", "{id}", target)

        best_id = None
        best_score = -1
        for node in api_nodes:
            payload = getattr(node, "payload", None) or {}
            if isinstance(node, dict):
                payload = node.get("payload") or node.get("metadata") or {}
                nid = node.get("id")
                nmethod = (payload.get("method") or "").upper()
                npath = (payload.get("path") or "").lower()
            else:
                nid = node.id
                nmethod = (payload.get("method") or "").upper()
                npath = (payload.get("path") or "").lower()
            if nmethod and nmethod != method_u:
                continue
            npath_pat = re.sub(r"\{[^}]+\}", "{id}", npath)
            score = 0
            if npath_pat == target_pat:
                score = 10
            elif npath.rstrip("/") == target.rstrip("/"):
                score = 9
            elif npath_pat.endswith(target_pat) or target_pat.endswith(npath_pat):
                score = 5
            elif Path(npath).name.lower() == Path(target).name.lower() and Path(target).name:
                score = 3
            if score > best_score:
                best_score = score
                best_id = nid
        return best_id if best_score >= 3 else None
