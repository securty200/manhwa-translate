"""API routes for the Manga Translator application."""

from fastapi import APIRouter

from backend.api.manga import router as manga_router
from backend.api.translation import router as translation_router
from backend.api.upload import router as upload_router
from backend.api.export import router as export_router
from backend.api.history import router as history_router
from backend.api.websocket import router as ws_router
from backend.api.project import router as project_router
from backend.api.import_api import router as import_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(manga_router, prefix="/manga", tags=["Manga / Projects"])
api_router.include_router(project_router, prefix="/projects", tags=["Projects (alternative)"])
api_router.include_router(upload_router, prefix="/upload", tags=["Upload"])
api_router.include_router(translation_router, prefix="/translate", tags=["Translation"])
api_router.include_router(export_router, prefix="/export", tags=["Export"])
api_router.include_router(history_router, prefix="/history", tags=["History"])
api_router.include_router(import_router, prefix="/import", tags=["Import"])
api_router.include_router(ws_router, prefix="/ws", tags=["WebSocket"])


@api_router.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "version": "1.0.0",
        "service": "AI Manga Translator",
    }


@api_router.get("/info", tags=["Info"])
async def api_info():
    """Get API information and available endpoints."""
    return {
        "name": "AI Manga Translator API",
        "version": "1.0.0",
        "endpoints": {
            "manga": "/api/v1/manga",
            "projects": "/api/v1/projects",
            "upload": "/api/v1/upload",
            "translate": "/api/v1/translate",
            "export": "/api/v1/export",
            "history": "/api/v1/history",
            "websocket": "/api/v1/ws",
            "docs": "/docs",
            "health": "/api/v1/health",
        },
    }
