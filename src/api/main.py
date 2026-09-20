"""FastAPI Entrypoint for Code2Guide Agent Service."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.core.config import settings
from src.api.routes import router

# Prefer the React+Vite FIDS shell; fall back to legacy static HTML.
REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
LEGACY_STATIC = Path(__file__).resolve().parent / "static"
UI_DIR = FRONTEND_DIST if (FRONTEND_DIST / "index.html").is_file() else LEGACY_STATIC

app = FastAPI(
    title="Code2Guide Agent API",
    description="Intelligent UX journey extractor & Persian assistant for enterprise codebases",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

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
