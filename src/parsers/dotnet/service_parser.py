"""Parse *Service / *Handler / *UseCase classes from C# sources."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field


class ParsedMethod(BaseModel):
    name: str
    return_type: str = ""
    parameters: List[str] = Field(default_factory=list)
    line_number: int = 1


class ParsedService(BaseModel):
    name: str
    file_path: str = ""
    methods: List[ParsedMethod] = Field(default_factory=list)
    injected_types: List[str] = Field(default_factory=list)
    summary: Optional[str] = None


class DotNetServiceParser:
    """Heuristic extraction of application/domain service classes."""

    NAME_SUFFIXES = ("Service", "Handler", "UseCase", "Manager", "Repository")

    def parse_file(self, content: str, file_path: str = "") -> List[ParsedService]:
        services: List[ParsedService] = []
        for m in re.finditer(
            r"(?:public\s+|internal\s+)?(?:sealed\s+|abstract\s+|partial\s+)*class\s+(?P<name>\w+)\b",
            content,
        ):
            name = m.group("name")
            if not any(name.endswith(suf) for suf in self.NAME_SUFFIXES):
                continue
            if name.endswith("Controller"):
                continue
            body_start = m.end()
            # Rough class body until next top-level class or EOF
            next_class = re.search(r"\n(?:public\s+|internal\s+)?(?:sealed\s+|partial\s+)*class\s+\w+", content[body_start:])
            body_end = body_start + next_class.start() if next_class else len(content)
            body = content[body_start:body_end]

            methods = self._parse_methods(body, content[:body_start].count("\n"))
            injected = self._parse_injections(body)
            services.append(
                ParsedService(
                    name=name,
                    file_path=file_path,
                    methods=methods,
                    injected_types=injected,
                    summary=f"{name} with {len(methods)} methods",
                )
            )
        return services

    def parse_paths(self, paths: List[Path], workspace_root: Path) -> List[ParsedService]:
        out: List[ParsedService] = []
        for path in paths:
            try:
                content = path.read_text(encoding="utf-8-sig", errors="replace")
            except Exception:
                continue
            try:
                rel = str(path.relative_to(workspace_root)).replace("\\", "/")
            except ValueError:
                rel = str(path).replace("\\", "/")
            out.extend(self.parse_file(content, rel))
        return out

    def _parse_methods(self, body: str, line_offset: int) -> List[ParsedMethod]:
        methods: List[ParsedMethod] = []
        for m in re.finditer(
            r"(?:public|internal)\s+(?:async\s+)?(?P<ret>[\w.<>,\s\[\]]+?)\s+(?P<name>\w+)\s*\((?P<params>[^)]*)\)",
            body,
        ):
            name = m.group("name")
            if name in ("if", "while", "for", "switch", "using", "get", "set"):
                continue
            # Skip properties mistaken as methods when followed by { get
            after = body[m.end() : m.end() + 40].lstrip()
            if after.startswith("{") and "get" in after[:30] and "(" not in body[m.start() : m.end()]:
                continue
            ret = re.sub(r"\s+", " ", m.group("ret")).strip()
            if ret in ("class", "interface", "enum", "struct", "record"):
                continue
            params_raw = m.group("params") or ""
            params = [p.strip() for p in params_raw.split(",") if p.strip()]
            line_number = line_offset + body[: m.start()].count("\n") + 1
            methods.append(
                ParsedMethod(
                    name=name,
                    return_type=ret,
                    parameters=params,
                    line_number=line_number,
                )
            )
        return methods

    def _parse_injections(self, body: str) -> List[str]:
        types: List[str] = []
        # ctor: public FooService(IBarRepo repo, IBaz x)
        ctor = re.search(r"(?:public|internal)\s+\w+\s*\((?P<params>[^)]*)\)", body)
        if ctor:
            for part in ctor.group("params").split(","):
                part = part.strip()
                if not part:
                    continue
                tm = re.match(r"(?:\[.*?\]\s*)?(?P<type>[\w.<>]+)\s+\w+", part)
                if tm:
                    types.append(tm.group("type"))
        return types
