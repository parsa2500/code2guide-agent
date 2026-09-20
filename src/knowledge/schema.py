"""Shared knowledge-graph node and edge contracts for Code2Guide.

Phase 0/1 implements frontend nodes fully. Backend node types are stubs
reserved for Phase 2 so the schema stays stable across phases.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class NodeType(str, Enum):
    """Canonical node kinds stored in the knowledge graph."""

    ROUTE = "route"
    PAGE = "page"
    COMPONENT = "component"
    FORM = "form"
    FORM_FIELD = "form_field"
    UI_BUTTON = "ui_button"
    I18N_STRING = "i18n_string"
    UI_TEXT = "ui_text"
    # Phase 2 stubs
    API_ENDPOINT = "api_endpoint"
    SERVICE = "service"
    ENTITY = "entity"
    TABLE = "table"
    DTO = "dto"


class EdgeType(str, Enum):
    """Canonical edge kinds between knowledge nodes."""

    RENDERS = "renders"
    CONTAINS_FIELD = "contains_field"
    HAS_BUTTON = "has_button"
    USES_I18N = "uses_i18n"
    CONTAINS_TEXT = "contains_text"
    # Phase 2/3
    CALLS_API = "calls_api"
    HANDLED_BY = "handled_by"
    USES_SERVICE = "uses_service"
    PERSISTS_TO = "persists_to"
    FK_TO = "fk_to"
    MAPS_TO = "maps_to"


class GraphNode(BaseModel):
    """A typed node in the workspace knowledge graph."""

    id: str = Field(description="Stable node id, e.g. route:/tenders/create")
    node_type: NodeType
    title: str = Field(default="", description="Human-readable label")
    file_path: str = Field(default="", description="Workspace-relative source path")
    payload: Dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    """A directed edge between two knowledge nodes."""

    id: str = Field(description="Stable edge id")
    edge_type: EdgeType
    source_id: str
    target_id: str
    payload: Dict[str, Any] = Field(default_factory=dict)


# --- Convenience payload shapes (documentation / typing aids) ---


class RoutePayload(BaseModel):
    path: str = ""
    component_name: Optional[str] = None
    breadcrumbs: List[str] = Field(default_factory=list)
    title: Optional[str] = None


class FormFieldPayload(BaseModel):
    name: str = ""
    field_type: str = "text"
    label: Optional[str] = None
    placeholder: Optional[str] = None
    required: bool = False
    validation_message: Optional[str] = None
    line_number: int = 1


class UIButtonPayload(BaseModel):
    label: str = ""
    name: Optional[str] = None
    action_type: str = "button"
    is_submit: bool = False
    line_number: int = 1


class I18nPayload(BaseModel):
    key: str = ""
    locale: str = "fa"
    value: str = ""


class UiTextPayload(BaseModel):
    """Visible UI copy stored as a ui_text graph node."""

    kind: str = Field(
        default="static",
        description="heading | table_header | list_item | tab | static | script_ui | error",
    )
    text: str = ""
    line_number: int = 1
    context: Optional[str] = None
