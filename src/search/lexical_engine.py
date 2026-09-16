"""Fast Lexical Search Engine with Persian UTF-8, Windows compatibility, and Ripgrep integration.

Searches target repositories (.tsx, .jsx, .vue, .json, .ts, .js) for localized
Persian UI labels, placeholders, buttons, routes, and validation messages.
Includes automatic fallback to high-speed Python scanning if ripgrep binary is missing.
"""

import os
import re
import json
import shutil
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from src.core.normalizer import PersianNormalizer, default_normalizer


class SearchMatch(BaseModel):
    """Represents a single match within a source code file."""
    file_path: str = Field(description="Relative path to matched file (POSIX-standard)")
    line_number: int = Field(description="1-based line number")
    line_content: str = Field(description="Exact line content from file")
    matched_term: str = Field(description="Search term that matched")
    context_before: List[str] = Field(default_factory=list, description="Lines preceding match")
    context_after: List[str] = Field(default_factory=list, description="Lines following match")


class SearchResult(BaseModel):
    """Aggregate search result for a query."""
    query: str
    normalized_query: str
    matches_count: int
    matches: List[SearchMatch] = Field(default_factory=list)
    engine_used: str = Field(default="ripgrep")


class RipgrepLexicalEngine:
    """Enterprise lexical search engine integrating Ripgrep and Persian normalization.
    Fully cross-platform supporting Windows (CRLF, backslashes, rg.exe) and Linux/macOS.
    """

    SUPPORTED_EXTENSIONS = {".tsx", ".jsx", ".vue", ".json", ".ts", ".js"}
    IGNORE_DIRS = {
        "node_modules", ".git", ".next", "dist", "build",
        ".venv", "venv", "__pycache__", ".turbo", "coverage"
    }

    def __init__(
        self,
        workspace_path: str,
        rg_binary_path: str = "rg",
        normalizer: Optional[PersianNormalizer] = None
    ):
        self.workspace_path = Path(workspace_path).resolve()
        self.rg_path = self._locate_rg(rg_binary_path)
        self.normalizer = normalizer or default_normalizer
        self._has_rg = bool(self.rg_path)

    def _locate_rg(self, rg_candidate: str) -> Optional[str]:
        """Locates ripgrep binary on Windows (.exe) or Unix."""
        # 1. Direct which lookup
        found = shutil.which(rg_candidate)
        if found:
            return found

        # 2. Windows specific candidate check
        if os.name == "nt" or not rg_candidate.lower().endswith(".exe"):
            found_exe = shutil.which(f"{rg_candidate}.exe")
            if found_exe:
                return found_exe

        # 3. Check common Windows install locations
        if os.name == "nt":
            common_paths = [
                r"C:\ProgramData\chocolatey\bin\rg.exe",
                r"C:\Program Files\ripgrep\rg.exe",
                os.path.expandvars(r"%USERPROFILE%\scoop\shims\rg.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\rg.exe"),
            ]
            for cp in common_paths:
                if os.path.isfile(cp):
                    return cp

        return None

    def _build_rg_command(
        self,
        pattern: str,
        case_sensitive: bool = False,
        context_lines: int = 2
    ) -> List[str]:
        """Constructs ripgrep CLI invocation arguments."""
        cmd = [
            self.rg_path,
            "--json",
            "-C", str(context_lines),
            "--glob", "*.{tsx,jsx,vue,json,ts,js}",
            "--glob", "!node_modules/**",
            "--glob", "!.git/**",
            "--glob", "!.next/**",
            "--glob", "!dist/**",
            "--glob", "!build/**",
        ]
        if not case_sensitive:
            cmd.append("-i")
        cmd.extend(["--", pattern, str(self.workspace_path)])
        return cmd

    def search(
        self,
        query: str,
        max_results: int = 50,
        context_lines: int = 2,
        normalize_query: bool = True
    ) -> SearchResult:
        """Executes Persian lexical search across target codebase."""
        if not self.workspace_path.exists():
            return SearchResult(
                query=query,
                normalized_query=query,
                matches_count=0,
                matches=[],
                engine_used="none"
            )

        norm_query = self.normalizer.clean_search_query(query) if normalize_query else query
        if not norm_query:
            return SearchResult(
                query=query,
                normalized_query="",
                matches_count=0,
                matches=[],
                engine_used="none"
            )

        if self._has_rg:
            try:
                return self._search_with_ripgrep(query, norm_query, max_results, context_lines)
            except Exception:
                return self._search_with_python_fallback(query, norm_query, max_results, context_lines)
        else:
            return self._search_with_python_fallback(query, norm_query, max_results, context_lines)

    def _search_with_ripgrep(
        self,
        original_query: str,
        search_query: str,
        max_results: int,
        context_lines: int
    ) -> SearchResult:
        """Parses ripgrep JSON output."""
        cmd = self._build_rg_command(search_query, context_lines=context_lines)
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        matches: List[SearchMatch] = []

        for line in process.stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = event.get("type")
            data = event.get("data", {})

            if event_type == "match":
                path = data.get("path", {}).get("text", "")
                rel_path = os.path.relpath(path, self.workspace_path).replace("\\", "/")
                line_num = data.get("line_number", 0)
                content = data.get("lines", {}).get("text", "").rstrip("\r\n")

                match_obj = SearchMatch(
                    file_path=rel_path,
                    line_number=line_num,
                    line_content=content,
                    matched_term=search_query,
                    context_before=[],
                    context_after=[]
                )
                matches.append(match_obj)
                if len(matches) >= max_results:
                    break

            elif event_type == "context" and matches:
                content = data.get("lines", {}).get("text", "").rstrip("\r\n")
                line_num = data.get("line_number", 0)
                last_match = matches[-1]
                if line_num < last_match.line_number:
                    last_match.context_before.append(content)
                elif line_num > last_match.line_number:
                    last_match.context_after.append(content)

        return SearchResult(
            query=original_query,
            normalized_query=search_query,
            matches_count=len(matches),
            matches=matches,
            engine_used="ripgrep"
        )

    def _search_with_python_fallback(
        self,
        original_query: str,
        search_query: str,
        max_results: int,
        context_lines: int
    ) -> SearchResult:
        """High-speed Python fallback scanner with Persian normalization aware matching.
        Guarantees UTF-8 encoding and POSIX relative paths across Windows and Unix.
        """
        matches: List[SearchMatch] = []
        pattern = re.compile(re.escape(search_query), re.IGNORECASE)
        norm_words = search_query.split()

        for root, dirs, files in os.walk(self.workspace_path):
            dirs[:] = [d for d in dirs if d not in self.IGNORE_DIRS and not d.startswith(".")]

            for file in files:
                file_ext = os.path.splitext(file)[1].lower()
                if file_ext not in self.SUPPORTED_EXTENSIONS:
                    continue

                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, self.workspace_path).replace("\\", "/")

                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()
                except Exception:
                    continue

                for idx, line in enumerate(lines):
                    line_clean = line.rstrip("\r\n")
                    normalized_line = self.normalizer.normalize(line_clean)

                    matched = False
                    if pattern.search(line_clean):
                        matched = True
                    elif all(w in normalized_line for w in norm_words if len(w) > 1):
                        matched = True

                    if matched:
                        start_ctx = max(0, idx - context_lines)
                        end_ctx = min(len(lines), idx + context_lines + 1)

                        ctx_before = [lines[i].rstrip("\r\n") for i in range(start_ctx, idx)]
                        ctx_after = [lines[i].rstrip("\r\n") for i in range(idx + 1, end_ctx)]

                        matches.append(
                            SearchMatch(
                                file_path=rel_path,
                                line_number=idx + 1,
                                line_content=line_clean,
                                matched_term=search_query,
                                context_before=ctx_before,
                                context_after=ctx_after
                            )
                        )

                        if len(matches) >= max_results:
                            return SearchResult(
                                query=original_query,
                                normalized_query=search_query,
                                matches_count=len(matches),
                                matches=matches,
                                engine_used="python-lexical-fallback"
                            )

        return SearchResult(
            query=original_query,
            normalized_query=search_query,
            matches_count=len(matches),
            matches=matches,
            engine_used="python-lexical-fallback"
        )
