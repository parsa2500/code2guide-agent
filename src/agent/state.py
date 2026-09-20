"""State definition for LangGraph Code2Guide Agent."""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from src.parsers.ast_visitor import DiscoveredForm, ComponentInspection
from src.parsers.route_extractor import RouteNode
from src.parsers.openapi_parser import EndpointRequirement


class AgentState(BaseModel):
    """State container tracked across LangGraph execution cycles."""

    query: str = Field(description="Persian user question or goal")
    workspace_path: str = Field(description="Root directory of target codebase")
    normalized_query: str = Field(default="", description="Cleaned Persian query")
    audience: str = Field(
        default="technical",
        description="technical | end_user — controls synthesis style",
    )

    # Extracted UX entities
    extracted_breadcrumbs: List[str] = Field(default_factory=list, description="Resolved navigation path")
    identified_routes: List[RouteNode] = Field(default_factory=list, description="Matching routes")
    discovered_forms: List[DiscoveredForm] = Field(default_factory=list, description="Parsed forms and inputs")
    inspected_components: List[ComponentInspection] = Field(default_factory=list, description="Inspected JSX/TSX components")

    # RBAC / API / validation enrichment
    required_roles: List[str] = Field(default_factory=list, description="Permission/role strings required for the operation")
    validation_notes: List[str] = Field(default_factory=list, description="Human-readable validation constraints")
    api_endpoints: List[EndpointRequirement] = Field(default_factory=list, description="Related OpenAPI endpoints")
    hybrid_hits: List[Dict[str, Any]] = Field(default_factory=list, description="Hybrid search hits for route/file discovery")
    backend_hits: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Backend graph/hybrid hits (entity/service/api/table)",
    )
    is_backend_query: bool = Field(default=False, description="Query primarily about backend logic/data")
    is_flow_query: bool = Field(default=False, description="Query about end-to-end UI→API→DB flow")
    flow_trace: Optional[Dict[str, Any]] = Field(default=None, description="Trace result for flow questions")
    query_plan: Optional[Dict[str, Any]] = Field(default=None, description="QueryPlanner output")
    tool_evidence: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Cited evidence gathered from agent tools",
    )

    # Tracking & Messaging
    messages: List[Dict[str, Any]] = Field(default_factory=list, description="Interaction history")
    steps_taken: List[str] = Field(default_factory=list, description="Sequence of actions taken")
    iteration: int = Field(default=0, description="Graph loop count")
    status: str = Field(default="in_progress", description="in_progress, completed, failed")

    # Final synthesized answer
    final_persian_guide: Optional[str] = Field(default=None, description="Synthesized UX guide in Persian")
