"""Workspace update / reindex service."""

from __future__ import annotations

from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from src.app.entities.update_job import UpdateJobEntity
from src.app.enums import LogLevel, LogSource, UpdateJobStatus, UpdateScope, WorkspaceStatus
from src.app.exceptions import NotFoundError, WorkspaceBusyError
from src.app.ids import new_update_job_id
from src.app.repositories.update_job_repo import UpdateJobRepository
from src.app.repositories.workspace_repo import WorkspaceRepository
from src.app.services.log_service import LogService
from src.app.services.workspace_service import WorkspaceService
from src.app.timeutil import utc_now_iso
from src.db.session import get_session_factory


class UpdateService:
    def __init__(self, db: Session):
        self.db = db
        self.jobs = UpdateJobRepository(db)
        self.workspaces = WorkspaceRepository(db)
        self.workspace_service = WorkspaceService(db)
        self.logs = LogService(db)

    def start(
        self,
        workspace_id: str,
        *,
        rebuild: bool = True,
        scope: UpdateScope = UpdateScope.FULL,
    ) -> UpdateJobEntity:
        ws = self.workspaces.get(workspace_id)
        if ws is None or ws.deleted_at is not None:
            raise NotFoundError("Workspace not found", code="WORKSPACE_NOT_FOUND")
        if self.jobs.has_running(workspace_id):
            raise WorkspaceBusyError()

        now = utc_now_iso()
        job = UpdateJobEntity(
            id=new_update_job_id(),
            workspace_id=workspace_id,
            started_at=now,
            finished_at=None,
            status=UpdateJobStatus.RUNNING,
            summary="",
            detail="",
            rebuild=rebuild,
            scope=scope,
        )
        self.jobs.create(job)
        self.workspace_service.set_status(workspace_id, WorkspaceStatus.INDEXING)
        self.logs.append(
            workspace_id,
            level=LogLevel.INFO,
            source=LogSource.INDEXER.value,
            message="ایندکس شروع شد",
        )
        self.db.commit()
        return job

    def list_jobs(
        self,
        workspace_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[UpdateJobEntity], int]:
        self._require_workspace(workspace_id)
        return self.jobs.list_by_workspace(workspace_id, limit=limit, offset=offset)

    def get_job(self, workspace_id: str, job_id: str) -> UpdateJobEntity:
        self._require_workspace(workspace_id)
        job = self.jobs.get(job_id)
        if job is None or job.workspace_id != workspace_id:
            raise NotFoundError("Update job not found", code="JOB_NOT_FOUND")
        return job

    def _require_workspace(self, workspace_id: str) -> None:
        ws = self.workspaces.get(workspace_id)
        if ws is None:
            raise NotFoundError("Workspace not found", code="WORKSPACE_NOT_FOUND")

    @staticmethod
    def run_index_job(
        job_id: str,
        workspace_path: str,
        *,
        rebuild: bool,
        workspace_id: str | None = None,
    ) -> None:
        """Background worker: run knowledge indexer and finalize job in a fresh session."""
        factory = get_session_factory()
        db = factory()
        try:
            jobs = UpdateJobRepository(db)
            workspaces = WorkspaceRepository(db)
            logs = LogService(db)
            workspace_service = WorkspaceService(db)

            job = jobs.get(job_id)
            if job is None:
                return

            try:
                from src.agent.tools import Code2GuideToolbox
                from src.knowledge.manager import get_index_manager

                wid = workspace_id or job.workspace_id
                toolbox = Code2GuideToolbox(workspace_path=workspace_path, workspace_id=wid)
                manager = get_index_manager(workspace_path, workspace_id=wid)
                result = manager.index_workspace(toolbox, rebuild=rebuild)
                summary = "ایندکس کامل شد"
                detail = (
                    f"Routes: {result.routes} · Forms: {result.forms} · "
                    f"APIs: {result.api_endpoints} · Edges: {result.edges}"
                )
                jobs.set_finished(
                    job_id,
                    status=UpdateJobStatus.SUCCESS,
                    finished_at=utc_now_iso(),
                    summary=summary,
                    detail=detail,
                )
                workspace_service.set_status(job.workspace_id, WorkspaceStatus.READY)
                logs.append(
                    job.workspace_id,
                    level=LogLevel.INFO,
                    source=LogSource.INDEXER.value,
                    message=summary,
                )
                db.commit()
            except Exception as exc:  # noqa: BLE001
                jobs.set_finished(
                    job_id,
                    status=UpdateJobStatus.FAILED,
                    finished_at=utc_now_iso(),
                    summary="ایندکس ناموفق بود",
                    detail=str(exc),
                )
                if job:
                    workspace_service.set_status(job.workspace_id, WorkspaceStatus.ERROR)
                    logs.append(
                        job.workspace_id,
                        level=LogLevel.ERROR,
                        source=LogSource.INDEXER.value,
                        message=f"خطای ایندکس: {exc}",
                    )
                db.commit()
        finally:
            db.close()
