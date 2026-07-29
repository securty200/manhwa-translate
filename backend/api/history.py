"""History and activity tracking API routes."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.session import get_session
from backend.models.manga import (
    JobStatus,
    Manga,
    TranslationJob,
    Chapter,
)
from backend.schemas.history import (
    ActivitySummary,
    HistoryEntry,
    HistoryFilter,
    HistoryPage,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _map_status_to_action(status: str) -> str:
    """Map job status to a human-readable action."""
    mapping = {
        "pending": "created",
        "queued": "queued",
        "processing": "started",
        "completed": "completed",
        "failed": "failed",
        "cancelled": "cancelled",
    }
    return mapping.get(status, "updated")


@router.get("", response_model=HistoryPage)
async def list_history(
    manga_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    source_language: Optional[str] = Query(None),
    target_language: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    search: Optional[str] = Query(None, max_length=100),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    """List translation history with filters and pagination."""
    query = (
        select(
            TranslationJob.id,
            Manga.title.label("manga_title"),
            Chapter.chapter_number,
            Chapter.title.label("chapter_title"),
            TranslationJob.status,
            TranslationJob.progress,
            TranslationJob.total_pages,
            TranslationJob.completed_pages,
            TranslationJob.failed_pages,
            TranslationJob.source_language,
            TranslationJob.target_language,
            TranslationJob.error_message,
            TranslationJob.started_at,
            TranslationJob.completed_at,
            TranslationJob.created_at,
        )
        .select_from(TranslationJob)
        .outerjoin(Chapter, TranslationJob.chapter_id == Chapter.id)
        .outerjoin(Manga, Chapter.manga_id == Manga.id)
    )

    # Apply filters
    if manga_id:
        query = query.where(Manga.id == manga_id)
    if status:
        try:
            status_enum = JobStatus(status)
            query = query.where(TranslationJob.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    if source_language:
        query = query.where(TranslationJob.source_language == source_language)
    if target_language:
        query = query.where(TranslationJob.target_language == target_language)
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from)
            query = query.where(TranslationJob.created_at >= dt_from)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date_from format (use ISO 8601)")
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to)
            query = query.where(TranslationJob.created_at <= dt_to)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date_to format (use ISO 8601)")
    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                Manga.title.ilike(search_term),
                Chapter.title.ilike(search_term),
            )
        )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_query)).scalar() or 0

    # Apply pagination
    query = query.order_by(desc(TranslationJob.created_at)).offset(offset).limit(limit)
    result = await session.execute(query)
    rows = result.all()

    items = []
    for row in rows:
        status_val = row.status.value if isinstance(row.status, JobStatus) else str(row.status)
        items.append(HistoryEntry(
            id=row.id,
            job_id=row.id,
            manga_title=row.manga_title or "Unknown",
            chapter_number=row.chapter_number or 0,
            chapter_title=row.chapter_title,
            action=_map_status_to_action(status_val),
            status=status_val,
            pages_total=row.total_pages or 0,
            pages_completed=row.completed_pages or 0,
            pages_failed=row.failed_pages or 0,
            processing_time_ms=(
                (row.completed_at - row.started_at).total_seconds() * 1000
                if row.started_at and row.completed_at else None
            ),
            error_message=row.error_message,
            source_language=row.source_language,
            target_language=row.target_language,
            created_at=row.created_at,
            completed_at=row.completed_at,
        ))

    return HistoryPage(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )


@router.get("/activity/summary", response_model=ActivitySummary)
async def get_activity_summary(
    days: int = Query(7, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
):
    """Get a summary of translation activity over the specified period."""
    since = datetime.utcnow() - timedelta(days=days)

    # Count jobs by status
    jobs_query = select(TranslationJob).where(TranslationJob.created_at >= since)
    jobs_result = await session.execute(jobs_query)
    jobs = jobs_result.scalars().all()

    total_jobs = len(jobs)
    completed_jobs = sum(1 for j in jobs if j.status == JobStatus.COMPLETED)
    failed_jobs = sum(1 for j in jobs if j.status == JobStatus.FAILED)

    total_pages = sum(j.total_pages or 0 for j in jobs)
    total_time = sum(
        (j.completed_at - j.started_at).total_seconds() * 1000
        for j in jobs
        if j.started_at and j.completed_at
    )

    avg_time = total_time / total_pages if total_pages > 0 else 0.0

    # Pages by language pair
    pages_by_lang: dict[str, int] = {}
    for j in jobs:
        lang_key = f"{j.source_language}→{j.target_language}"
        pages_by_lang[lang_key] = pages_by_lang.get(lang_key, 0) + (j.total_pages or 0)

    # Recent activity
    recent_query = (
        select(
            TranslationJob.id,
            Manga.title.label("manga_title"),
            Chapter.chapter_number,
            Chapter.title.label("chapter_title"),
            TranslationJob.status,
            TranslationJob.created_at,
            TranslationJob.completed_at,
        )
        .select_from(TranslationJob)
        .outerjoin(Chapter, TranslationJob.chapter_id == Chapter.id)
        .outerjoin(Manga, Chapter.manga_id == Manga.id)
        .where(TranslationJob.created_at >= since)
        .order_by(desc(TranslationJob.created_at))
        .limit(10)
    )
    recent_result = await session.execute(recent_query)
    recent_rows = recent_result.all()

    recent_activity = []
    for row in recent_rows:
        status_val = row.status.value if isinstance(row.status, JobStatus) else str(row.status)
        recent_activity.append(HistoryEntry(
            id=row.id,
            job_id=row.id,
            manga_title=row.manga_title or "Unknown",
            chapter_number=row.chapter_number or 0,
            chapter_title=row.chapter_title,
            action="completed" if status_val == "completed" else "updated",
            status=status_val,
            created_at=row.created_at,
            completed_at=row.completed_at,
        ))

    return ActivitySummary(
        total_jobs=total_jobs,
        completed_jobs=completed_jobs,
        failed_jobs=failed_jobs,
        total_pages_translated=total_pages,
        total_time_ms=total_time,
        average_time_per_page_ms=avg_time,
        pages_by_language=pages_by_lang,
        recent_activity=recent_activity,
    )
