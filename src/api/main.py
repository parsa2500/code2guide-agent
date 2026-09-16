"""FastAPI Entrypoint for Code2Guide Agent Service."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import settings
from src.api.routes import router

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


@app.get("/", tags=["Root"])
def root():
    return {
        "service": settings.app_name,
        "status": "online",
        "docs_url": "/docs",
        "message": "به سامانه راهنمای تجربه کاربری سورس‌کد خوش آمدید."
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host=settings.host, port=settings.port, reload=settings.debug)
