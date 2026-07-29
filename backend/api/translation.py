"""Enhanced translation API routes with full job lifecycle management."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.session import get_session
from backend.models.manga import (
    Chapter,
    JobStatus,
    Manga,
    Page,
    TranslationJob,
)
from backend.queue.job_queue import JobQueueManager
from backend.schemas.translation import (
    BatchTranslationRequest,
    TranslationJobCreate,
    TranslationJobResponse,
    TranslationJobStatus,
    TranslationProgress,
    TranslationRequest,
    TranslationResponse,
)
from backend.translator.service import TranslationService

logger = logging.getLogger(__name__)

router = APIRouter()

# Global reference to the queue manager (set from main.py)
queue_manager: Optional[JobQueueManager] = None


def get_queue() -> Optional[JobQueueManager]:
    """Get the global queue manager instance, or None if not initialized."""
    return queue_manager


def _require_queue() -> JobQueueManager:
    """Get the queue manager or raise 503 if not available."""
    qm = queue_manager
    if qm is None:
        raise HTTPException(status_code=503, detail="Queue manager not available")
    return qm


@router.post("/text", response_model=TranslationResponse)
async def translate_text(data: TranslationRequest):
    """Translate a single text string."""
    service = TranslationService()
    try:
        result = await service.translate(
            text=data.text,
            source_language=data.source_language,
            target_language=data.target_language,
            context=data.context,
        )
        return TranslationResponse(
            translated_text=result.translated_text,
            source_language=result.source_language,
            target_language=result.target_language,
            confidence=result.confidence,
            processing_time_ms=result.processing_time_ms,
        )
    except Exception as e:
        logger.error("Translation failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")
    finally:
        await service.cleanup()


@router.post("/batch", response_model=list[TranslationResponse])
async def translate_batch(data: BatchTranslationRequest):
    """Translate multiple texts in batch."""
    service = TranslationService()
    try:
        results = await service.translate_batch(
            texts=data.texts,
            source_language=data.source_language,
            target_language=data.target_language,
            context=data.context,
        )
        return [
            TranslationResponse(
                translated_text=r.translated_text,
                source_language=r.source_language,
                target_language=r.target_language,
                confidence=r.confidence,
                processing_time_ms=r.processing_time_ms,
            )
            for r in results
        ]
    except Exception as e:
        logger.error("Batch translation failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Batch translation failed: {str(e)}")
    finally:
        await service.cleanup()


# ── Enhanced Job Management ──────────────────────────────────────────────


@router.post("/jobs", response_model=TranslationJobResponse, status_code=status.HTTP_201_CREATED)
async def create_translation_job(
    data: TranslationJobCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create a new translation job for a chapter and enqueue it for processing."""
    # Verify chapter exists
    chapter = await session.get(Chapter, data.chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    # Check if there's already a pending/processing job for this chapter
    existing = await session.execute(
        select(TranslationJob).where(
            TranslationJob.chapter_id == data.chapter_id,
            TranslationJob.status.in_([JobStatus.PENDING, JobStatus.QUEUED, JobStatus.PROCESSING]),
        )
    )
    if existing.scalar():
        raise HTTPException(
            status_code=409,
            detail="A job for this chapter is already pending or in progress",
        )

    # Count pages for progress tracking
    pages_count = (await session.execute(
        select(func.count(Page.id)).where(Page.chapter_id == data.chapter_id)
    )).scalar() or 0

    job_id = str(uuid.uuid4())
    now = datetime.utcnow()
    job = TranslationJob(
        id=job_id,
        chapter_id=data.chapter_id,
        status=JobStatus.PENDING,
        total_pages=pages_count,
        source_language=data.source_language or "ja",
        target_language=data.target_language or "en",
        options_json=data.options,
        created_at=now,
        updated_at=now,
    )
    session.add(job)
    await session.flush()

    # Enqueue in the job queue (best-effort if queue not ready)
    qm = get_queue()
    if qm is not None:
        await qm.enqueue(job_id, data.chapter_id)
    else:
        logger.warning("Queue manager not available, job %s created but not enqueued", job_id)

    logger.info(
        "Created translation job %s for chapter %s (%d pages)",
        job_id, data.chapter_id, pages_count,
    )

    return TranslationJobResponse(
        id=job.id,
        chapter_id=job.chapter_id,
        status=job.status.value,
        progress=0.0,
        total_pages=pages_count,
        completed_pages=0,
        failed_pages=0,
        source_language=job.source_language,
        target_language=job.target_language,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get("/jobs", response_model=list[TranslationJobResponse])
async def list_translation_jobs(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status_filter: Optional[str] = Query(None),
    chapter_id: Optional[str] = Query(None),
    manga_id: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """List translation jobs with comprehensive filtering."""
    query = select(TranslationJob).order_by(TranslationJob.created_at.desc())

    if status_filter:
        try:
            status_enum = JobStatus(status_filter)
            query = query.where(TranslationJob.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status_filter}")

    if chapter_id:
        query = query.where(TranslationJob.chapter_id == chapter_id)

    if manga_id:
        query = query.join(Chapter, TranslationJob.chapter_id == Chapter.id).where(
            Chapter.manga_id == manga_id
        )

    query = query.offset(offset).limit(limit)
    result = await session.execute(query)
    jobs = result.scalars().all()

    return [
        TranslationJobResponse(
            id=job.id,
            chapter_id=job.chapter_id,
            status=job.status.value,
            progress=job.progress,
            total_pages=job.total_pages,
            completed_pages=job.completed_pages,
            failed_pages=job.failed_pages,
            error_message=job.error_message,
            source_language=job.source_language,
            target_language=job.target_language,
            started_at=job.started_at,
            completed_at=job.completed_at,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
        for job in jobs
    ]


@router.get("/jobs/{job_id}", response_model=TranslationJobResponse)
async def get_translation_job(
    job_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get detailed information about a translation job."""
    job = await session.get(TranslationJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Translation job not found")

    return TranslationJobResponse(
        id=job.id,
        chapter_id=job.chapter_id,
        status=job.status.value,
        progress=job.progress,
        total_pages=job.total_pages,
        completed_pages=job.completed_pages,
        failed_pages=job.failed_pages,
        error_message=job.error_message,
        source_language=job.source_language,
        target_language=job.target_language,
        started_at=job.started_at,
        completed_at=job.completed_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get("/jobs/{job_id}/status", response_model=TranslationJobStatus)
async def get_job_status(
    job_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Lightweight status polling endpoint for a translation job."""
    job = await session.get(TranslationJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Translation job not found")

    return TranslationJobStatus(
        id=job.id,
        status=job.status.value,
        progress=job.progress,
        completed_pages=job.completed_pages,
        total_pages=job.total_pages,
        failed_pages=job.failed_pages,
        error_message=job.error_message,
    )


@router.post("/jobs/{job_id}/stop")
async def stop_translation_job(
    job_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Stop/pause a running translation job."""
    job = await session.get(TranslationJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Translation job not found")

    if job.status != JobStatus.PROCESSING:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot stop job with status: {job.status.value}. Only processing jobs can be stopped.",
        )

    qm = get_queue()
    if qm is not None:
        await qm.pause(job_id)

    job.status = JobStatus.PAUSED
    job.updated_at = datetime.utcnow()
    session.add(job)
    await session.flush()

    logger.info("Job %s stopped/paused", job_id)
    return {"message": "Job stopped/paused", "job_id": job_id, "status": "paused"}


@router.post("/jobs/{job_id}/resume")
async def resume_translation_job(
    job_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Resume a paused translation job."""
    job = await session.get(TranslationJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Translation job not found")

    qm = get_queue()
    if qm is not None:
        await qm.resume(job_id)

    job.status = JobStatus.QUEUED
    job.updated_at = datetime.utcnow()
    session.add(job)
    await session.flush()

    # Re-enqueue for processing
    if job.chapter_id:
        qm = get_queue()
        if qm is not None:
            await qm.retry(job_id, job.chapter_id)

    logger.info("Job %s resumed", job_id)
    return {"message": "Job resumed", "job_id": job_id, "status": "queued"}


@router.post("/jobs/{job_id}/cancel")
async def cancel_translation_job(
    job_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Cancel a translation job (can be pending, queued, or processing)."""
    job = await session.get(TranslationJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Translation job not found")

    if job.status in (JobStatus.COMPLETED, JobStatus.CANCELLED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job with status: {job.status.value}",
        )

    qm = get_queue()
    if qm is not None:
        await qm.cancel(job_id)

    job.status = JobStatus.CANCELLED
    job.completed_at = datetime.utcnow()
    job.updated_at = datetime.utcnow()
    session.add(job)
    await session.flush()

    logger.info("Job %s cancelled", job_id)
    return {"message": "Job cancelled", "job_id": job_id, "status": "cancelled"}


@router.post("/jobs/{job_id}/retry")
async def retry_translation_job(
    job_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Retry a failed or cancelled translation job."""
    job = await session.get(TranslationJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Translation job not found")

    if job.status not in (JobStatus.FAILED, JobStatus.CANCELLED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry job with status: {job.status.value}. Only failed or cancelled jobs can be retried.",
        )

    # Reset job status
    job.status = JobStatus.PENDING
    job.error_message = None
    job.progress = 0.0
    job.completed_pages = 0
    job.failed_pages = 0
    job.completed_at = None
    job.started_at = None
    job.updated_at = datetime.utcnow()
    session.add(job)
    await session.flush()

    # Re-enqueue
    if job.chapter_id:
        qm = get_queue()
        if qm is not None:
            await qm.retry(job_id, job.chapter_id)

    logger.info("Job %s queued for retry", job_id)
    return {"message": "Job queued for retry", "job_id": job_id, "status": "pending"}


@router.get("/queue/status")
async def get_queue_status():
    """Get the current status of the job queue."""
    qm = get_queue()
    if qm is None:
        return {
            "active_jobs": 0,
            "pending_queue_size": 0,
            "max_concurrent": 3,
            "paused_jobs": [],
            "healthy": False,
            "message": "Queue manager not yet initialized",
        }
    return {
        "active_jobs": qm.get_active_count(),
        "pending_queue_size": qm.get_queue_size(),
        "max_concurrent": 3,
        "paused_jobs": [],
        "healthy": True,
    }
