"""FastAPI Entrypoint for Code2Guide Agent Service."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.app.exceptions import AppError
from src.api.routes import router
from src.api.schemas.common import ErrorBody
from src.api.shell import shell_router
from src.core.config import settings
from src.db.base import reset_engine
from src.db.init_db import init_db
from src.db.session import get_session_factory, reset_session_factory


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Path(settings.app_db_path).parent.mkdir(parents=True, exist_ok=True)
    init_db()
    get_session_factory(force_new=True)
    yield
    reset_session_factory()
    reset_engine()


# Prefer the React+Vite FIDS shell; fall back to legacy static HTML.
REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
LEGACY_STATIC = Path(__file__).resolve().parent / "static"
UI_DIR = FRONTEND_DIST if (FRONTEND_DIST / "index.html").is_file() else LEGACY_STATIC

app = FastAPI(
    title="Code2Guide Agent API",
    description="Intelligent UX journey extractor & Persian assistant for enterprise codebases",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    body = ErrorBody(code=exc.code, message=exc.message, detail=exc.detail)
    return JSONResponse(status_code=exc.status_code, content=body.model_dump())


app.include_router(router)
app.include_router(shell_router)

if UI_DIR.is_dir():
    assets = UI_DIR / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")
    # Legacy /static mount still useful for older links
    if LEGACY_STATIC.is_dir():
        app.mount("/static", StaticFiles(directory=str(LEGACY_STATIC)), name="static")


@app.get("/", tags=["Root"], include_in_schema=False)
def root():
    """Code2Guide operator UI (FIDS shell or legacy viewer)."""
    index = UI_DIR / "index.html"
    if index.is_file():
        return FileResponse(index)
    return {
        "service": settings.app_name,
        "status": "online",
        "docs_url": "/docs",
        "message": "به سامانه راهنمای تجربه کاربری سورس‌کد خوش آمدید. "
        "برای UI جدید: cd frontend && npm install && npm run build",
    }


@app.get("/favicon.svg", include_in_schema=False)
def favicon():
    icon = UI_DIR / "favicon.svg"
    if icon.is_file():
        return FileResponse(icon)
    legacy = LEGACY_STATIC / "favicon.svg"
    if legacy.is_file():
        return FileResponse(legacy)
    return FileResponse(REPO_ROOT / "frontend" / "public" / "favicon.svg")


@app.get("/api", tags=["Root"])
def api_info():
    return {
        "service": settings.app_name,
        "status": "online",
        "docs_url": "/docs",
        "ui_url": "/",
        "message": "به سامانه راهنمای تجربه کاربری سورس‌کد خوش آمدید.",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.api.main:app", host=settings.host, port=settings.port, reload=settings.debug)
