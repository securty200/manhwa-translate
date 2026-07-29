"""FastAPI application entry point for the AI Manga Translator.

Performance-optimized with:
- Profiling middleware for CPU/RAM/GPU monitoring
- Multi-tier caching (OCR, translation, images, models, detection)
- Background system monitoring
- Optimized connection pooling
- Lazy initialization for heavy services
"""

from __future__ import annotations

import asyncio
import gc
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import psutil
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.api import api_router
from backend.config import settings
from backend.config.logging import setup_logging
from backend.database.session import create_tables
from backend.middleware.cors import setup_cors
from backend.middleware.error_handler import setup_error_handlers
from backend.queue.job_queue import JobQueueManager
from backend.workers.translation_worker import TranslationWorker

# Setup logging early
setup_logging()
logger = logging.getLogger(__name__)

# Global instances
worker = TranslationWorker()
job_queue = JobQueueManager(process_callback=worker.process_job)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan managing startup and shutdown tasks."""
    # ── Startup ──────────────────────────────────────────────────────────
    logger.info("Starting %s v%s", settings.PROJECT_NAME, settings.VERSION)

    # Create database tables
    await create_tables()
    logger.info("Database tables created")

    # Set up queue manager reference in translation routes
    import backend.api.translation as translation_module
    translation_module.queue_manager = job_queue

    # Mount entire cache directory for static file serving
    # Serves both cache/uploads/ and cache/output/ from a single mount
    settings.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (settings.CACHE_DIR / "output").mkdir(parents=True, exist_ok=True)
    (settings.CACHE_DIR / "uploads").mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(settings.CACHE_DIR)), name="static")

    # ── Performance Initialization ───────────────────────────────────────

    # Configure thread pool for CPU-bound operations
    import concurrent.futures
    loop = asyncio.get_event_loop()
    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=settings.MAX_THREAD_POOL_WORKERS,
        thread_name_prefix="worker",
    )
    loop.set_default_executor(executor)
    logger.info("Thread pool configured: %d workers", settings.MAX_THREAD_POOL_WORKERS)

    # Set PyTorch thread settings if available
    if settings.TORCH_NUM_THREADS > 1:
        try:
            import torch
            torch.set_num_threads(settings.TORCH_NUM_THREADS)
            logger.info("PyTorch threads: %d", settings.TORCH_NUM_THREADS)
        except ImportError:
            pass

    # Start cache instances
    from backend.services.cache_service import start_all_caches, ocr_cache, translation_cache
    await start_all_caches()
    logger.info("Cache instances started")

    # Warm caches from Redis (non-blocking)
    asyncio.create_task(ocr_cache.warm_from_redis(max_entries=20))
    asyncio.create_task(translation_cache.warm_from_redis(max_entries=20))

    # Start system monitoring (profiling middleware)
    if settings.PROFILE_ENABLED:
        from backend.middleware.profiling import system_monitor
        await system_monitor.start()
        logger.info("System monitor started")

    # Register profiling API routes
    if settings.PROFILE_ENABLED:
        @app.get("/api/v1/profile", tags=["Performance"])
        async def get_profile():
            """Get current performance profiling data."""
            from backend.middleware.profiling import get_performance_dashboard
            return await get_performance_dashboard()

        @app.get("/api/v1/profile/history", tags=["Performance"])
        async def get_profile_history(seconds: int = 60):
            """Get profiling history for the last N seconds."""
            from backend.middleware.profiling import system_monitor
            return {"snapshots": system_monitor.get_history(seconds=seconds)}

        @app.get("/api/v1/cache/stats", tags=["Performance"])
        async def get_cache_stats():
            """Get cache statistics for all cache instances."""
            from backend.services.cache_service import get_all_cache_stats
            return await get_all_cache_stats()

        logger.info("Performance API routes registered")

    # Start background worker
    worker_task = asyncio.create_task(worker.start())
    logger.info("Background worker started")

    # Start job queue
    queue_task = asyncio.create_task(job_queue.start())
    logger.info("Job queue manager started")

    # Periodic GC task
    async def _periodic_gc():
        """Force garbage collection periodically to prevent memory leaks."""
        while True:
            await asyncio.sleep(settings.GC_INTERVAL_SECONDS)
            before = gc.get_count()
            collected = gc.collect()
            if collected > 0:
                process = psutil.Process(os.getpid())
                mem = process.memory_info().rss / (1024 * 1024)
                logger.debug(
                    "Periodic GC: collected %d objects (gen counts: %s), mem=%.0fMB",
                    collected, before, mem,
                )

    gc_task = asyncio.create_task(_periodic_gc())

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────
    logger.info("Shutting down %s", settings.PROJECT_NAME)

    # Stop monitoring
    if settings.PROFILE_ENABLED:
        from backend.middleware.profiling import system_monitor
        await system_monitor.stop()

    # Stop caches
    from backend.services.cache_service import stop_all_caches
    await stop_all_caches()

    # Stop worker and queue in order
    await worker.stop()
    await job_queue.stop()

    worker_task.cancel()
    queue_task.cancel()
    gc_task.cancel()
    try:
        await asyncio.gather(worker_task, queue_task, gc_task, return_exceptions=True)
    except asyncio.CancelledError:
        pass

    # Shutdown executor
    executor.shutdown(wait=False, cancel_futures=True)

    logger.info("Shutdown complete")


# Create the FastAPI application
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    redirect_slashes=False,
    description="AI-powered manga translation system with OCR, text detection, "
    "LLM translation, inpainting, and rendering capabilities.\n\n"
    "## Features\n"
    "- **Project Management** — Create and manage manga translation projects\n"
    "- **File Upload** — Upload page images with validation and processing\n"
    "- **OCR** — Automatic Japanese text extraction from bubbles\n"
    "- **AI Translation** — Translate using OpenAI, Anthropic, Google, DeepSeek, or local models\n"
    "- **Image Inpainting** — Remove original text with state-of-the-art models\n"
    "- **Text Rendering** — Render translated text with proper formatting\n"
    "- **Job Queue** — Async job processing with pause/resume/cancel/retry\n"
    "- **Real-time Updates** — WebSocket progress tracking\n"
    "- **Export** — Download translated chapters as CBZ/ZIP/PDF",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    contact={
        "name": "AI Manga Translator Team",
        "url": "https://github.com/ai-manga-translator",
    },
    license_info={
        "name": "MIT",
    },
)

# Setup CORS
setup_cors(app)

# Setup global error handlers
setup_error_handlers(app)

# Include API router
app.include_router(api_router)


# ── Root endpoint ────────────────────────────────────────────────────────
@app.get("/")
async def root():
    """Root endpoint with basic info and available endpoints."""
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs": "/docs" if settings.DEBUG else None,
        "redoc": "/redoc" if settings.DEBUG else None,
        "api": {
            "health": "/api/v1/health",
            "info": "/api/v1/info",
            "manga": "/api/v1/manga",
            "translate": "/api/v1/translate",
            "upload": "/api/v1/upload",
            "export": "/api/v1/export",
            "history": "/api/v1/history",
            "websocket": "/api/v1/ws/progress/{job_id}",
        },
    }


# ── Exception for direct run ─────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
