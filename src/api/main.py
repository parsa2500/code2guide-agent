"""FastAPI Entrypoint for Code2Guide Agent Service."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.core.config import settings
from src.api.routes import router

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Code2Guide Agent API",
    description="Intelligent UX journey extractor & Persian assistant for enterprise codebases",
    version="0.1.0"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API endpoints
app.include_router(router)

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", tags=["Root"], include_in_schema=False)
def root():
    """Persian Markdown viewer UI for UX guides."""
    index = STATIC_DIR / "index.html"
    if index.is_file():
        return FileResponse(index)
    return {
        "service": settings.app_name,
        "status": "online",
        "docs_url": "/docs",
        "message": "به سامانه راهنمای تجربه کاربری سورس‌کد خوش آمدید."
    }


@app.get("/api", tags=["Root"])
def api_info():
    return {
        "service": settings.app_name,
        "status": "online",
        "docs_url": "/docs",
        "ui_url": "/",
        "message": "به سامانه راهنمای تجربه کاربری سورس‌کد خوش آمدید."
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host=settings.host, port=settings.port, reload=settings.debug)
