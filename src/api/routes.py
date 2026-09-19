"""API routes for Code2Guide Agent."""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from src.core.config import settings
from src.core.markdown_guide import normalize_guide_markdown
from src.agent.workflow import Code2GuideAgent
from src.agent.tools import Code2GuideToolbox, dump_model

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


@router.post("/scan-workspace", response_model=ScanWorkspaceResponse, summary="Scan routes and components in workspace")
def scan_workspace(payload: ScanWorkspaceRequest):
    """Scans and indexes menu trees, React Router, and Next.js routes across workspace."""
    target_ws = payload.workspace_path or settings.target_workspace_path
    try:
        toolbox = Code2GuideToolbox(workspace_path=target_ws)
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
                f"Workspace scanned successfully: {len(route_tree.routes)} routes discovered, "
                f"{index_info.get('indexed_count', 0)} indexed "
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
