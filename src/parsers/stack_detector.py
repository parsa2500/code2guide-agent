"""Detect backend stacks and candidate roots inside a workspace."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


DOTNET_SKIP_DIRS = frozenset(
    {
        "node_modules",
        ".git",
        ".next",
        "dist",
        "build",
        ".venv",
        "venv",
        "coverage",
        "bin",
        "obj",
        ".vs",
        "packages",
        "TestResults",
        "__pycache__",
        ".code2guide",
        "qdrant_storage",
    }
)


@dataclass
class StackDetection:
    """Result of scanning a workspace for backend technology."""

    stack: Optional[str] = None
    backend_roots: List[str] = field(default_factory=list)
    markers: List[str] = field(default_factory=list)
    skipped: bool = False
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "stack": self.stack,
            "backend_roots": list(self.backend_roots),
            "markers": list(self.markers),
            "skipped": self.skipped,
            "message": self.message,
        }


class StackDetector:
    """Heuristic stack detection (Phase 2: .NET / ASP.NET Core)."""

    def __init__(self, workspace_path: str):
        self.workspace_root = Path(workspace_path).resolve()

    def detect(self) -> StackDetection:
        if not self.workspace_root.is_dir():
            return StackDetection(
                skipped=True,
                message=f"Workspace not found: {self.workspace_root}",
            )

        markers: List[str] = []
        csproj_dirs: List[Path] = []
        sln_dirs: List[Path] = []
        special_dirs: List[Path] = []

        for root, dirnames, filenames in os.walk(self.workspace_root):
            dirnames[:] = [d for d in dirnames if d not in DOTNET_SKIP_DIRS]
            root_path = Path(root)
            lower_names = {f.lower() for f in filenames}
            dir_lower = {d.lower() for d in dirnames}

            for name in filenames:
                lower = name.lower()
                if lower.endswith(".csproj"):
                    markers.append(str((root_path / name).relative_to(self.workspace_root)).replace("\\", "/"))
                    csproj_dirs.append(root_path)
                elif lower.endswith(".sln"):
                    markers.append(str((root_path / name).relative_to(self.workspace_root)).replace("\\", "/"))
                    sln_dirs.append(root_path)
                elif lower in ("program.cs", "startup.cs"):
                    markers.append(str((root_path / name).relative_to(self.workspace_root)).replace("\\", "/"))

            for folder in ("controllers", "entities", "migrations"):
                if folder in dir_lower:
                    special_dirs.append(root_path)
                    markers.append(
                        str((root_path / next(d for d in dirnames if d.lower() == folder)).relative_to(self.workspace_root)).replace("\\", "/")
                    )

        if not markers and not csproj_dirs and not special_dirs:
            # Also accept a backend/ folder that only has .cs sources (sample fixture)
            for cand in ("backend", "api", "server", "src"):
                p = self.workspace_root / cand
                if p.is_dir() and any(p.rglob("*.cs")):
                    markers.append(f"{cand}/ (*.cs)")
                    special_dirs.append(p)
                    break

        if not markers and not any(self.workspace_root.rglob("*.cs")):
            return StackDetection(
                skipped=True,
                message="No .NET markers (.sln/.csproj/Program.cs/Controllers) found; backend index skipped.",
            )

        roots = self._choose_roots(csproj_dirs, sln_dirs, special_dirs)
        if not roots:
            # Fallback: workspace root itself if it contains .cs files
            if any(self.workspace_root.rglob("*.cs")):
                roots = ["."]
            else:
                return StackDetection(
                    skipped=True,
                    message="Detected markers but could not resolve backend roots.",
                    markers=markers[:20],
                )

        return StackDetection(
            stack="dotnet",
            backend_roots=roots,
            markers=markers[:40],
            skipped=False,
            message=f"Detected .NET backend at: {', '.join(roots)}",
        )

    def _choose_roots(
        self,
        csproj_dirs: List[Path],
        sln_dirs: List[Path],
        special_dirs: List[Path],
    ) -> List[str]:
        candidates: List[Path] = []
        candidates.extend(csproj_dirs)
        if not candidates:
            candidates.extend(special_dirs)
        if not candidates:
            candidates.extend(sln_dirs)

        # Prefer paths under backend/api/server naming
        scored: List[tuple] = []
        for p in candidates:
            try:
                rel = p.relative_to(self.workspace_root)
            except ValueError:
                continue
            parts = [x.lower() for x in rel.parts]
            score = 0
            if any(x in ("backend", "api", "server", "webapi", "src") for x in parts):
                score += 5
            if (p / "Controllers").is_dir() or (p / "controllers").is_dir():
                score += 3
            if list(p.glob("*.csproj")):
                score += 2
            scored.append((score, len(rel.parts), p))

        scored.sort(key=lambda t: (-t[0], t[1], str(t[2]).lower()))
        roots: List[str] = []
        seen = set()
        for _, __, p in scored:
            try:
                rel = str(p.relative_to(self.workspace_root)).replace("\\", "/")
            except ValueError:
                continue
            if rel == ".":
                key = "."
            else:
                key = rel
            if key in seen:
                continue
            # Skip nested roots under an already chosen parent
            if any(key == r or key.startswith(r.rstrip("/") + "/") for r in seen if r != "."):
                continue
            seen.add(key)
            roots.append(key)
            if len(roots) >= 5:
                break
        return roots

    @staticmethod
    def iter_cs_files(root: Path) -> List[Path]:
        found: List[Path] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in DOTNET_SKIP_DIRS]
            for name in filenames:
                if name.lower().endswith(".cs"):
                    found.append(Path(dirpath) / name)
        return found
