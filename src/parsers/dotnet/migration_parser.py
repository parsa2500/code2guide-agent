"""Parse EF Core migration CreateTable calls into Table nodes."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field


class ParsedColumn(BaseModel):
    name: str
    sql_type: str = ""
    nullable: bool = True


class ParsedTable(BaseModel):
    name: str
    columns: List[ParsedColumn] = Field(default_factory=list)
    file_path: str = ""
    summary: Optional[str] = None


class DotNetMigrationParser:
    """Extract tables from MigrationBuilder.CreateTable blocks."""

    def parse_file(self, content: str, file_path: str = "") -> List[ParsedTable]:
        tables: List[ParsedTable] = []
        if "CreateTable" not in content and "migrationBuilder" not in content:
            return tables

        for m in re.finditer(
            r'CreateTable\s*\(\s*name:\s*["\'](?P<name>[^"\']+)["\']\s*,\s*columns:\s*table\s*=>\s*new\s*\{(?P<body>.*?)\}\s*,',
            content,
            re.DOTALL,
        ):
            name = m.group("name")
            body = m.group("body")
            columns = self._parse_columns(body)
            tables.append(
                ParsedTable(
                    name=name,
                    columns=columns,
                    file_path=file_path,
                    summary=f"Table {name} ({len(columns)} columns)",
                )
            )

        # Alternate compact form: name: "Tenders"
        if not tables:
            for m in re.finditer(
                r'CreateTable\s*\(\s*name:\s*["\'](?P<name>[^"\']+)["\']',
                content,
            ):
                tables.append(
                    ParsedTable(
                        name=m.group("name"),
                        columns=[],
                        file_path=file_path,
                        summary=f"Table {m.group('name')}",
                    )
                )
        return tables

    def parse_paths(self, paths: List[Path], workspace_root: Path) -> List[ParsedTable]:
        out: List[ParsedTable] = []
        for path in paths:
            # Prefer Migration files
            lower = str(path).replace("\\", "/").lower()
            if "migration" not in lower and path.name.lower() != "modelsnapshot.cs":
                # Still allow if CreateTable present
                pass
            try:
                content = path.read_text(encoding="utf-8-sig", errors="replace")
            except Exception:
                continue
            if "CreateTable" not in content:
                continue
            try:
                rel = str(path.relative_to(workspace_root)).replace("\\", "/")
            except ValueError:
                rel = str(path).replace("\\", "/")
            out.extend(self.parse_file(content, rel))
        # Dedupe by table name
        by_name: dict = {}
        for t in out:
            prev = by_name.get(t.name)
            if prev is None or len(t.columns) > len(prev.columns):
                by_name[t.name] = t
        return list(by_name.values())

    def _parse_columns(self, body: str) -> List[ParsedColumn]:
        columns: List[ParsedColumn] = []
        for m in re.finditer(
            r"(?P<name>\w+)\s*=\s*table\.Column<\s*(?P<type>[^>]+)\s*>\s*\((?P<args>[^)]*)\)",
            body,
        ):
            args = m.group("args") or ""
            nullable = "nullable: true" in args.replace(" ", "").lower() or "nullable:true" in args.replace(" ", "").lower()
            if "nullable: false" in args.replace(" ", "").lower() or "nullable:false" in args.replace(" ", "").lower():
                nullable = False
            columns.append(
                ParsedColumn(
                    name=m.group("name"),
                    sql_type=m.group("type").strip(),
                    nullable=nullable,
                )
            )
        return columns
