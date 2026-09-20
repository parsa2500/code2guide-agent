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
    is_mvc_framework: bool = False

    def to_dict(self) -> dict:
        return {
            "stack": self.stack,
            "backend_roots": list(self.backend_roots),
            "markers": list(self.markers),
            "skipped": self.skipped,
            "message": self.message,
            "is_mvc_framework": self.is_mvc_framework,
        }


class StackDetector:
    """Heuristic stack detection (.NET Core and ASP.NET MVC Framework)."""

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
        is_mvc = False

        for root, dirnames, filenames in os.walk(self.workspace_root):
            dirnames[:] = [d for d in dirnames if d not in DOTNET_SKIP_DIRS]
            root_path = Path(root)
            dir_lower = {d.lower() for d in dirnames}

            for name in filenames:
                lower = name.lower()
                if lower.endswith(".csproj"):
                    rel = str((root_path / name).relative_to(self.workspace_root)).replace("\\", "/")
                    markers.append(rel)
                    csproj_dirs.append(root_path)
                    if self._csproj_looks_mvc(root_path / name):
                        is_mvc = True
                        markers.append(f"{rel} (mvc)")
                elif lower.endswith(".sln"):
                    markers.append(str((root_path / name).relative_to(self.workspace_root)).replace("\\", "/"))
                    sln_dirs.append(root_path)
                elif lower in ("program.cs", "startup.cs"):
                    markers.append(str((root_path / name).relative_to(self.workspace_root)).replace("\\", "/"))
                elif lower in ("global.asax", "global.asax.cs", "packages.config"):
                    is_mvc = True
                    markers.append(str((root_path / name).relative_to(self.workspace_root)).replace("\\", "/"))

            for folder in ("controllers", "entities", "migrations", "views"):
                if folder in dir_lower:
                    special_dirs.append(root_path)
                    folder_name = next(d for d in dirnames if d.lower() == folder)
                    markers.append(
                        str((root_path / folder_name).relative_to(self.workspace_root)).replace("\\", "/")
                    )
                    if folder == "views":
                        is_mvc = True

        if not markers and not csproj_dirs and not special_dirs:
            for cand in ("backend", "api", "server", "src", "mvc_portal"):
                p = self.workspace_root / cand
                if p.is_dir() and any(p.rglob("*.cs")):
                    markers.append(f"{cand}/ (*.cs)")
                    special_dirs.append(p)
                    if (p / "Views").is_dir() or (p / "Global.asax").exists() or (p / "Global.asax.cs").exists():
                        is_mvc = True
                    break

        if not markers and not any(self.workspace_root.rglob("*.cs")):
            return StackDetection(
                skipped=True,
                message="No .NET markers (.sln/.csproj/Program.cs/Controllers) found; backend index skipped.",
            )

        roots = self._choose_roots(csproj_dirs, sln_dirs, special_dirs, prefer_models=is_mvc)
        if not roots:
            if any(self.workspace_root.rglob("*.cs")):
                roots = ["."]
            else:
                return StackDetection(
                    skipped=True,
                    message="Detected markers but could not resolve backend roots.",
                    markers=markers[:20],
                    is_mvc_framework=is_mvc,
                )

        # Ensure Models / BussinessEntities sibling roots are included for MVC
        if is_mvc:
            roots = self._ensure_models_roots(roots, csproj_dirs)

        msg = f"Detected .NET backend at: {', '.join(roots)}"
        if is_mvc:
            msg += " (ASP.NET MVC Framework)"

        return StackDetection(
            stack="dotnet",
            backend_roots=roots,
            markers=markers[:40],
            skipped=False,
            message=msg,
            is_mvc_framework=is_mvc,
        )

    def _csproj_looks_mvc(self, csproj: Path) -> bool:
        try:
            text = csproj.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return False
        lower = text.lower()
        if "system.web.mvc" in lower or "microsoft.aspnet.mvc" in lower:
            return True
        if "<targetframeworkversion>" in lower and "net4" in lower.replace(" ", ""):
            # Classic framework project; treat as MVC candidate when Views or Global.asax nearby
            parent = csproj.parent
            if (parent / "Views").is_dir() or (parent / "Global.asax").exists() or (parent / "Global.asax.cs").exists():
                return True
        return False

    def _ensure_models_roots(self, roots: List[str], csproj_dirs: List[Path]) -> List[str]:
        """Add *Models* / BussinessEntities project dirs when present under workspace."""
        seen = set(roots)
        out = list(roots)

        def _add(rel: str) -> None:
            if rel not in seen and len(out) < 8:
                seen.add(rel)
                out.append(rel)

        for p in csproj_dirs:
            try:
                rel = str(p.relative_to(self.workspace_root)).replace("\\", "/")
            except ValueError:
                continue
            name = p.name.lower()
            if "models" in name or rel.lower().endswith("models"):
                _add(rel if rel != "." else ".")

        # Named folders anywhere under workspace (one level of project dirs)
        for cand in ("Contracts.Models", "Models"):
            p = self.workspace_root / cand
            if p.is_dir() and any(p.rglob("*.cs")):
                _add(cand)

        for dirpath, dirnames, _ in os.walk(self.workspace_root):
            dirnames[:] = [d for d in dirnames if d not in DOTNET_SKIP_DIRS]
            for d in list(dirnames):
                if d.lower() in ("bussinessentities", "businessentities", "baseentities"):
                    parent = Path(dirpath)
                    # Prefer the project root above the entities folder
                    proj = parent
                    if parent.name.lower() in ("bussinessentities", "businessentities", "baseentities"):
                        proj = parent.parent
                    try:
                        rel = str(proj.relative_to(self.workspace_root)).replace("\\", "/")
                    except ValueError:
                        continue
                    _add(rel if rel else ".")
        return out

    def _choose_roots(
        self,
        csproj_dirs: List[Path],
        sln_dirs: List[Path],
        special_dirs: List[Path],
        prefer_models: bool = False,
    ) -> List[str]:
        candidates: List[Path] = []
        candidates.extend(csproj_dirs)
        if not candidates:
            candidates.extend(special_dirs)
        if not candidates:
            candidates.extend(sln_dirs)

        scored: List[tuple] = []
        for p in candidates:
            try:
                rel = p.relative_to(self.workspace_root)
            except ValueError:
                continue
            parts = [x.lower() for x in rel.parts]
            score = 0
            if any(x in ("backend", "api", "server", "webapi", "src", "mvc_portal") for x in parts):
                score += 5
            if (p / "Controllers").is_dir() or (p / "controllers").is_dir():
                score += 3
            if (p / "Views").is_dir() or (p / "Global.asax").exists() or (p / "Global.asax.cs").exists():
                score += 4
            if list(p.glob("*.csproj")):
                score += 2
            if prefer_models and "models" in p.name.lower():
                score += 3
            scored.append((score, len(rel.parts), p))

        scored.sort(key=lambda t: (-t[0], t[1], str(t[2]).lower()))
        roots: List[str] = []
        seen = set()
        max_roots = 8 if prefer_models else 5
        for _, __, p in scored:
            try:
                rel = str(p.relative_to(self.workspace_root)).replace("\\", "/")
            except ValueError:
                continue
            key = rel if rel else "."
            if key in seen:
                continue
            if any(key == r or key.startswith(r.rstrip("/") + "/") for r in seen if r != "."):
                continue
            seen.add(key)
            roots.append(key)
            if len(roots) >= max_roots:
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
