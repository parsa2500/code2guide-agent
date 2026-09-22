"""App shell HTTP routers (separate from legacy src.api.routes module)."""

from fastapi import APIRouter

from . import (
    agents,
    brain_settings,
    workspace_agents,
    workspace_chat,
    workspace_logs,
    workspace_settings,
    workspace_updates,
    workspaces,
)

shell_router = APIRouter(prefix="/api/v1")
shell_router.include_router(workspaces.router)
shell_router.include_router(workspace_settings.router)
shell_router.include_router(workspace_updates.router)
shell_router.include_router(workspace_logs.router)
shell_router.include_router(workspace_chat.router)
shell_router.include_router(agents.router)
shell_router.include_router(workspace_agents.router)
shell_router.include_router(brain_settings.router)
