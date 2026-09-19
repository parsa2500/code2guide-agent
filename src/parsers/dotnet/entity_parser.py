"""Parse EF Core entities, DbSet declarations, and relations."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field


class ParsedField(BaseModel):
    name: str
    clr_type: str = "string"
    is_navigation: bool = False
    is_required: bool = False
    foreign_key_to: Optional[str] = None


class ParsedEntity(BaseModel):
    name: str
    table_name: Optional[str] = None
    file_path: str = ""
    fields: List[ParsedField] = Field(default_factory=list)
    dbset_name: Optional[str] = None
    summary: Optional[str] = None


class DotNetEntityParser:
    """Extract entity classes and DbContext DbSet<> mappings."""

    def parse_file(self, content: str, file_path: str = "") -> List[ParsedEntity]:
        entities: List[ParsedEntity] = []
        # Prefer files under Entities/Models or [Table] attribute
        lower_path = file_path.replace("\\", "/").lower()
        likely = any(p in lower_path for p in ("/entities/", "/models/", "/domain/"))
        has_table = "[Table" in content or "DbSet<" in content

        for m in re.finditer(
            r"(?:\[Table\s*\(\s*[\"'](?P<table>[^\"']+)[\"']\s*\)\]\s*)?"
            r"(?:public\s+|internal\s+)?(?:partial\s+)?class\s+(?P<name>\w+)\b",
            content,
        ):
            name = m.group("name")
            if name.endswith(("Controller", "Service", "Handler", "Context", "Migration")):
                continue
            if name.endswith(("Dto", "Request", "Response", "Command", "Query", "ViewModel")):
                continue
            table = m.group("table")
            # Only keep if looks like entity
            if not likely and not table and not has_table:
                # Require at least one public property with get;set
                snippet = content[m.start() : m.start() + 800]
                if "get;" not in snippet and "{ get" not in snippet:
                    continue
                if not re.search(r"public\s+\w+", snippet):
                    continue

            body_start = m.end()
            next_class = re.search(
                r"\n(?:public\s+|internal\s+)?(?:partial\s+)?class\s+\w+",
                content[body_start:],
            )
            body_end = body_start + next_class.start() if next_class else len(content)
            body = content[body_start:body_end]
            fields = self._parse_properties(body)
            if not fields and not table:
                continue
            entities.append(
                ParsedEntity(
                    name=name,
                    table_name=table or self._pluralize(name),
                    file_path=file_path,
                    fields=fields,
                    summary=f"Entity {name} ({len(fields)} fields)",
                )
            )

        # Attach DbSet names from same file (DbContext)
        dbsets = re.findall(r"DbSet\s*<\s*(\w+)\s*>\s+(\w+)", content)
        by_type = {t: n for t, n in dbsets}
        for ent in entities:
            if ent.name in by_type:
                ent.dbset_name = by_type[ent.name]

        return entities

    def parse_dbsets(self, content: str) -> List[tuple]:
        """Return list of (EntityType, DbSetPropertyName)."""
        return re.findall(r"DbSet\s*<\s*(\w+)\s*>\s+(\w+)", content)

    def parse_paths(self, paths: List[Path], workspace_root: Path) -> List[ParsedEntity]:
        out: List[ParsedEntity] = []
        dbset_map: dict = {}
        for path in paths:
            try:
                content = path.read_text(encoding="utf-8-sig", errors="replace")
            except Exception:
                continue
            try:
                rel = str(path.relative_to(workspace_root)).replace("\\", "/")
            except ValueError:
                rel = str(path).replace("\\", "/")
            for t, n in self.parse_dbsets(content):
                dbset_map[t] = n
            out.extend(self.parse_file(content, rel))

        for ent in out:
            if ent.name in dbset_map:
                ent.dbset_name = dbset_map[ent.name]
        # Deduplicate by name preferring richer field lists
        by_name: dict = {}
        for ent in out:
            prev = by_name.get(ent.name)
            if prev is None or len(ent.fields) > len(prev.fields):
                by_name[ent.name] = ent
        return list(by_name.values())

    def _parse_properties(self, body: str) -> List[ParsedField]:
        fields: List[ParsedField] = []
        for m in re.finditer(
            r"(?:\[ForeignKey\s*\(\s*[\"']?(?P<fk>[^\"'\)]+)[\"']?\s*\)\]\s*)?"
            r"(?:\[Required\]\s*)?"
            r"public\s+(?:virtual\s+)?(?P<type>[\w.<>,\s\?]+?)\s+(?P<name>\w+)\s*\{\s*get",
            body,
        ):
            clr = re.sub(r"\s+", " ", m.group("type")).strip()
            name = m.group("name")
            if name in ("get", "set"):
                continue
            is_nav = bool(re.match(r"^(ICollection|IList|List|HashSet)<", clr)) or (
                clr[0].isupper()
                and not clr.rstrip("?").lower()
                in (
                    "string",
                    "int",
                    "long",
                    "bool",
                    "decimal",
                    "double",
                    "float",
                    "datetime",
                    "datetimeoffset",
                    "guid",
                    "byte",
                    "short",
                )
                and "<" not in clr
            )
            required = "[Required]" in body[max(0, m.start() - 80) : m.start()] or (
                not clr.endswith("?") and clr.lower() not in ("string",)
            )
            fields.append(
                ParsedField(
                    name=name,
                    clr_type=clr,
                    is_navigation=is_nav,
                    is_required=required,
                    foreign_key_to=(m.group("fk") if m.group("fk") else None),
                )
            )
        return fields

    @staticmethod
    def _pluralize(name: str) -> str:
        if name.endswith("y"):
            return name[:-1] + "ies"
        if name.endswith("s"):
            return name + "es"
        return name + "s"
