"""API routes for Code2Guide Agent."""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, status, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from src.core.config import settings
from src.core.markdown_guide import normalize_guide_markdown
from src.agent.workflow import Code2GuideAgent
from src.agent.tools import Code2GuideToolbox, dump_model
from src.knowledge.manager import get_index_manager

router = APIRouter(prefix="/api/v1", tags=["Code2Guide Agent"])


class AskRequest(BaseModel):
    """Payload for user queries."""
    query: str = Field(..., example="چگونه یک مناقصه جدید ثبت کنم؟", description="User question in Persian")
    workspace_path: Optional[str] = Field(default=None, description="Optional path to target codebase")


class AskResponse(BaseModel):
    """Structured response containing Persian UX guide."""
    query: str
    guide: str
    breadcrumbs: List[str]
    routes_found: int
    forms_found: int
    steps_taken: List[str]


class ScanWorkspaceRequest(BaseModel):
    """Request to index and scan a workspace."""
    workspace_path: Optional[str] = Field(default=None, description="Target workspace root")


class ScanWorkspaceResponse(BaseModel):
    """Summary of workspace route and component scanning."""
    workspace_path: str
    total_routes: int
    routes: List[Dict[str, Any]]
    indexed_count: int = 0
    use_vector: bool = False
    message: str


class IndexWorkspaceRequest(BaseModel):
    """Request a full deep frontend index of a workspace."""
    workspace_path: Optional[str] = Field(default=None, description="Target workspace root")
    rebuild: bool = Field(default=True, description="Clear and rebuild graph + vectors")


class IndexWorkspaceResponse(BaseModel):
    """Summary of deep frontend indexing."""
    workspace_path: str
    duration_ms: float = 0.0
    routes: int = 0
    components: int = 0
    forms: int = 0
    form_fields: int = 0
    ui_buttons: int = 0
    i18n_strings: int = 0
    edges: int = 0
    indexed_count: int = 0
    files_inspected: int = 0
    use_vector: bool = False
    collection_name: str = ""
    db_path: str = ""
    message: str = ""


def _toolbox_for(workspace_path: Optional[str]) -> Code2GuideToolbox:
    target = workspace_path or settings.target_workspace_path
    return Code2GuideToolbox(workspace_path=target)


@router.post("/ask", response_model=AskResponse, summary="Generate Persian UX Guide for codebase operation")
def ask_codebase(payload: AskRequest):
    """Analyzes codebase AST, routes, and forms to generate a step-by-step Persian user guide."""
    target_ws = payload.workspace_path or settings.target_workspace_path
    try:
        agent = Code2GuideAgent(workspace_path=target_ws)
        state = agent.ask(query=payload.query, workspace_path=target_ws)

        guide = normalize_guide_markdown(
            state.final_persian_guide or "راهنمایی یافت نشد."
        )
        return AskResponse(
            query=state.query,
            guide=guide,
            breadcrumbs=state.extracted_breadcrumbs,
            routes_found=len(state.identified_routes),
            forms_found=len(state.discovered_forms),
            steps_taken=state.steps_taken
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error executing Code2Guide agent: {str(e)}"
        )


@router.post(
    "/ask.md",
    response_class=PlainTextResponse,
    summary="Generate Persian UX Guide as downloadable Markdown",
)
def ask_codebase_markdown(payload: AskRequest):
    """Same as /ask, but returns raw Markdown with correct newlines for MD viewers."""
    target_ws = payload.workspace_path or settings.target_workspace_path
    try:
        agent = Code2GuideAgent(workspace_path=target_ws)
        state = agent.ask(query=payload.query, workspace_path=target_ws)
        guide = normalize_guide_markdown(
            state.final_persian_guide or "راهنمایی یافت نشد."
        )
        return PlainTextResponse(
            content=guide,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": 'inline; filename="code2guide.md"',
            },
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error executing Code2Guide agent: {str(e)}"
        )


@router.post(
    "/index-workspace",
    response_model=IndexWorkspaceResponse,
    summary="Deep-index all frontend routes, forms, fields, buttons, and i18n",
)
def index_workspace(payload: IndexWorkspaceRequest):
    """Full frontend index into SQLite graph + hybrid/Qdrant vectors (no 6-file cap)."""
    target_ws = payload.workspace_path or settings.target_workspace_path
    try:
        toolbox = _toolbox_for(target_ws)
        manager = get_index_manager(target_ws)
        manager.hybrid_indexer = toolbox.hybrid_indexer
        result = manager.index_workspace(toolbox, rebuild=payload.rebuild)
        d = result.to_dict()
        return IndexWorkspaceResponse(
            workspace_path=d["workspace_path"],
            duration_ms=d.get("duration_ms", 0.0),
            routes=d.get("routes", 0),
            components=d.get("components", 0),
            forms=d.get("forms", 0),
            form_fields=d.get("form_fields", 0),
            ui_buttons=d.get("ui_buttons", 0),
            i18n_strings=d.get("i18n_strings", 0),
            edges=d.get("edges", 0),
            indexed_count=d.get("indexed_count", 0),
            files_inspected=d.get("files_inspected", 0),
            use_vector=bool(d.get("use_vector")),
            collection_name=d.get("collection_name") or "",
            db_path=d.get("db_path") or "",
            message=(
                f"Indexed {d.get('routes', 0)} routes, {d.get('forms', 0)} forms, "
                f"{d.get('form_fields', 0)} fields, {d.get('files_inspected', 0)} UI files "
                f"in {d.get('duration_ms', 0)}ms."
            ),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error indexing workspace: {str(e)}"
        )


@router.get("/index/status", summary="Status of the persisted workspace knowledge index")
def index_status(workspace_path: Optional[str] = Query(default=None)):
    """Return whether a deep index exists, node counts, and last indexed time."""
    target_ws = workspace_path or settings.target_workspace_path
    try:
        toolbox = _toolbox_for(target_ws)
        return toolbox.index_status()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error reading index status: {str(e)}"
        )


@router.post("/scan-workspace", response_model=ScanWorkspaceResponse, summary="Scan routes and components in workspace")
def scan_workspace(payload: ScanWorkspaceRequest):
    """Alias for deep index-workspace (kept for backward compatibility)."""
    target_ws = payload.workspace_path or settings.target_workspace_path
    try:
        toolbox = _toolbox_for(target_ws)
        route_tree = toolbox.get_route_tree()
        routes_data = [dump_model(r) for r in route_tree.routes]
        index_info = toolbox.index_workspace()

        return ScanWorkspaceResponse(
            workspace_path=target_ws,
            total_routes=len(route_tree.routes),
            routes=routes_data,
            indexed_count=index_info.get("indexed_count", 0),
            use_vector=bool(index_info.get("use_vector")),
            message=(
                f"[deprecated: prefer POST /index-workspace] "
                f"Workspace indexed: {len(route_tree.routes)} routes, "
                f"{index_info.get('forms', 0)} forms, "
                f"{index_info.get('indexed_count', 0)} hybrid items "
                f"(use_vector={index_info.get('use_vector')})."
            ),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error scanning workspace: {str(e)}"
        )


@router.get("/health", summary="Service Health Check")
def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "app_name": settings.app_name,
        "environment": settings.app_env
    }
