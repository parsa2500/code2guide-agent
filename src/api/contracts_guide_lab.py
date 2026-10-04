"""Loopback-only standalone phase-one UI. No legacy index or production routes."""
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from src.app.services.contracts_guide_lab import ContractsGuideLab, GeminiGuideWriter
from src.integrations.code_kb_client import CodeKbClient, CodeKbError
from src.app.services.guide_lab_settings import GuideSettings, GuideSettingsStore
from src.app.services.guide_lab_console import GuideLabConsole
from src.app.services.guide_lab_sessions import GuideSessionStore, sanitize_page_context


class Turn(BaseModel):
    question: str = Field(min_length=3, max_length=1200)
    session_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    page_context: dict[str, Any] = Field(default_factory=dict)


class SessionCreateRequest(BaseModel):
    page_context: dict[str, Any] = Field(default_factory=dict)


class SettingsUpdate(BaseModel):
    revision: str
    settings: GuideSettings


class JobRequest(BaseModel):
    kind: str
    version: str | None = Field(default=None,pattern=r'^[a-f0-9]{64}$')


class KnowledgeChange(BaseModel):
    version: str = Field(pattern=r'^[a-f0-9]{64}$')
    value: dict = Field(default_factory=dict)


class ReviewRequest(BaseModel):
    target: str
    reviewer: str = Field(min_length=2, max_length=120)
    decision: str = Field(pattern="^(approved|needs_changes|rejected)$")
    note: str = Field(default="", max_length=3000)


def create_app(service: ContractsGuideLab, console: GuideLabConsole | None = None) -> FastAPI:
    app = FastAPI(title="Contracts Guide Lab", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        if request.url.hostname not in {"127.0.0.1", "localhost", "testserver"}:
            return JSONResponse({"error": "loopback_only"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            return JSONResponse({"error": "same_origin_required"}, status_code=403)
        if request.url.path.startswith("/api/console/") and request.method not in {"GET", "HEAD"} and request.headers.get("X-Guide-Console") != "1":
            return JSONResponse({"error": "console_header_required"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def index():
        return FileResponse(Path(__file__).parent / "static" / ("contracts-guide-console.html" if console else "contracts-guide-lab.html"))

    @app.get("/chat")
    def chat_page():
        return FileResponse(Path(__file__).parent / "static" / "contracts-guide-chat.html")

    @app.get('/console-editor.js')
    def console_editor():
        return FileResponse(Path(__file__).parent/'static/contracts-guide-editor.js',media_type='text/javascript')

    @app.get("/api/status")
    def status():
        settings = service.settings_store.get() if service.settings_store else None
        return {"workspace": service.workspace, "revision": service.revision,
            "provider": settings["settings"]["provider"] if settings else ("gemini" if service.writer else "none"),
            "review_status": "pending-human", "model": (settings["settings"]["model"] if settings["settings"]["provider"] == "gemini" else "none") if settings else (service.writer.model if service.writer else "none"),
            "settings_revision": settings["revision"] if settings else "defaults"}

    @app.post("/api/chat")
    def chat(turn: Turn):
        return service.answer(
            turn.question.strip(),
            session_id=turn.session_id,
            page_context=sanitize_page_context(turn.page_context),
        )

    @app.get("/api/evidence/{trace_id}/{citation_id}")
    def evidence(trace_id: str, citation_id: str):
        item = service.evidence(trace_id, citation_id)
        if item is None:
            raise HTTPException(404)
        return item

    if console:
        @app.get("/api/console/overview")
        def overview():
            return console.health()

        @app.get("/api/console/settings")
        def settings():
            return service.settings_store.get()

        @app.get("/api/sessions")
        def sessions():
            if not service.session_store:
                return {"items": []}
            return {"items": service.session_store.list()}

        @app.post("/api/sessions")
        def create_session(request: SessionCreateRequest | None = None):
            context = sanitize_page_context(request.page_context if request else {})
            if not service.session_store:
                raise HTTPException(503, "sessions_unavailable")
            return service.session_store.create(context)

        @app.get("/api/sessions/{session_id}")
        def get_session(session_id: str):
            if not service.session_store:
                raise HTTPException(503, "sessions_unavailable")
            session = service.session_store.get(session_id)
            if session is None:
                raise HTTPException(404, "session_not_found")
            return session

        @app.put("/api/console/settings")
        def save_settings(update: SettingsUpdate):
            with console.lock:
                if console.current:
                    raise HTTPException(409, "job_running")
                if update.settings.provider == "gemini" and not service.provider_key:
                    raise HTTPException(422, "provider_key_not_configured")
                try:
                    return service.settings_store.save(update.revision, update.settings)
                except ValueError:
                    raise HTTPException(409, "settings_conflict")

        @app.get("/api/console/knowledge")
        def knowledge():
            try:
                return console.knowledge()
            except Exception:
                raise HTTPException(503, "brain_unavailable")

        def knowledge_change(method, path, body):
            try:
                return console.edit_knowledge(method,path,body.model_dump())
            except ValueError as exc:
                raise HTTPException(409,str(exc))
            except CodeKbError as exc:
                code=exc.body.get('error') if isinstance(exc.body,dict) else None
                safe_code=code if isinstance(code,str) and re.fullmatch(r'[a-z_]+',code) else 'knowledge_operation_failed'
                raise HTTPException(exc.status if exc.status in {404,409,422} else 503,safe_code)

        @app.api_route('/api/console/knowledge/documents/{name}',methods=['POST','PUT','DELETE'])
        def document_change(name: str, change: KnowledgeChange, request: Request):
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\.md',name):raise HTTPException(422,'invalid_document_name')
            return knowledge_change(request.method,'documents/'+name,change)

        @app.api_route('/api/console/knowledge/graph/{collection}/{entity_id}',methods=['POST','PUT','DELETE'])
        def graph_change(collection: str,entity_id: str,change: KnowledgeChange,request: Request):
            if collection not in {'nodes','edges','observations'} or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}',entity_id):raise HTTPException(422,'invalid_graph_target')
            return knowledge_change(request.method,'graph/'+collection+'/'+entity_id,change)

        @app.get('/api/console/pipeline/runs')
        def pipeline_runs():
            return console.pipeline.list()

        @app.get('/api/console/pipeline/runs/{run_id}')
        def pipeline_run(run_id: str):
            try:return console.pipeline.get(run_id)
            except (ValueError,FileNotFoundError):raise HTTPException(404)

        @app.post('/api/console/pipeline/start',status_code=202)
        def pipeline_start(turn: Turn):
            try:return console.start_answer(turn.question.strip())
            except ValueError as exc:raise HTTPException(409,str(exc))

        @app.get('/api/console/pipeline/publish')
        def pipeline_publish():
            try:return service.client._request_json('GET','/api/lab/publish-status')
            except Exception:raise HTTPException(503,'brain_unavailable')

        @app.get("/api/console/traces")
        def traces():
            return console.traces()

        @app.get("/api/console/traces/{workspace}/{trace_id}")
        def trace(workspace: str, trace_id: str):
            try:
                return console.trace(workspace, trace_id)
            except (ValueError, FileNotFoundError):
                raise HTTPException(404)

        @app.get("/api/console/evaluations")
        def evaluations():
            return console.evaluations()

        @app.get("/api/console/jobs")
        def jobs():
            return console.jobs()

        @app.post("/api/console/jobs", status_code=202)
        def job(data: JobRequest):
            try:
                return console.start_job(data.kind,data.version)
            except ValueError as exc:
                raise HTTPException(409 if str(exc) == "job_running" else 422, str(exc))

        @app.get("/api/console/reviews")
        def reviews():
            return console.reviews()

        @app.post("/api/console/reviews")
        def review(data: ReviewRequest):
            try:
                return console.save_review(data.target, data.reviewer, data.decision, data.note)
            except ValueError:
                raise HTTPException(422, "invalid_target")

    return app


def app_factory():
    load_dotenv(override=False)
    key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    provider = os.environ.get("GUIDE_LAB_PROVIDER", "none")
    if provider not in {"none", "gemini"}:
        raise ValueError("Unsupported guide lab provider")
    if provider == "gemini" and not key:
        raise ValueError("Gemini key is required")
    project_dir = Path(os.environ["GUIDE_LAB_PROJECT_DIR"]) if os.environ.get("GUIDE_LAB_PROJECT_DIR") else None
    state_dir = Path(".code2guide/guide-console").resolve()
    store = GuideSettingsStore(state_dir, provider=provider, model=os.environ.get("GUIDE_LAB_MODEL", "gemini-3.1-flash-lite")) if project_dir else None
    sessions = GuideSessionStore(state_dir / "sessions") if project_dir else None
    service = ContractsGuideLab(
        CodeKbClient(base_url=os.environ["CODE_KB_BASE_URL"], token=os.environ["CODE_KB_TOKEN"]),
        os.environ["GUIDE_LAB_WORKSPACE"], os.environ["GUIDE_LAB_REVISION"],
        Path(os.environ.get("GUIDE_LAB_TRACE_DIR", ".code2guide/guide-lab-traces")),
        GeminiGuideWriter(key, os.environ.get("GUIDE_LAB_MODEL", "gemini-3.1-flash-lite")) if provider == "gemini" else None,
        settings_store=store, provider_key=key, managed_knowledge=os.environ.get('GUIDE_LAB_MANAGED_KNOWLEDGE')=='1',
        session_store=sessions)
    return create_app(service, GuideLabConsole(service, project_dir, state_dir) if project_dir else None)
