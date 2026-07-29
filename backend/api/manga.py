"""Enhanced manga CRUD API routes with project management features."""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select, func, delete, or_, case
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.session import get_session
from backend.models.manga import Chapter, Manga, Page, TranslationJob, JobStatus, Bubble
from backend.schemas.project import (
    ProjectCreate,
    ProjectResponse,
    ProjectStats,
    ProjectSummary,
    ProjectUpdate,
)
from backend.schemas.manga import (
    ChapterCreate,
    ChapterResponse,
    MangaCreate,
    MangaResponse,
    MangaUpdate,
    PageResponse,
)
from backend.services.upload_service import UploadService

logger = logging.getLogger(__name__)

router = APIRouter()
upload_service = UploadService()


# ── Enhanced Manga (Project) Endpoints ───────────────────────────────────


@router.get("", response_model=list[ProjectSummary])
async def list_projects(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    sort_by: str = Query("updated_at", pattern="^(title|created_at|updated_at|chapter_count)$"),
    sort_desc: bool = Query(True),
    language: Optional[str] = Query(None, description="Filter by source or target language"),
    session: AsyncSession = Depends(get_session),
):
    """List all manga projects with pagination, search, and filtering."""
    query = select(Manga)

    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                Manga.title.ilike(search_term),
                Manga.title_original.ilike(search_term),
                Manga.author.ilike(search_term),
            )
        )

    if language:
        query = query.where(
            or_(
                Manga.source_language == language,
                Manga.target_language == language,
            )
        )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_count = (await session.execute(count_query)).scalar() or 0

    # Apply sorting
    sort_col = getattr(Manga, sort_by, Manga.updated_at)
    query = query.order_by(sort_col.desc() if sort_desc else sort_col.asc())

    # Apply pagination
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)
    result = await session.execute(query)
    mangas = result.scalars().all()

    # Build responses with computed stats
    responses = []
    for manga in mangas:
        # Count pages and translation progress
        from sqlalchemy import select as sel_select
        pages_result = await session.execute(
            sel_select(func.count(), func.sum(case((Page.is_translated == True, 1), else_=0)))
            .select_from(Page)
            .join(Chapter, Page.chapter_id == Chapter.id)
            .where(Chapter.manga_id == manga.id)
        )
        row = pages_result.one()
        total_pages = row[0] or 0
        translated_pages = row[1] or 0
        progress = (translated_pages / total_pages * 100) if total_pages > 0 else 0.0

        # Last activity
        last_job = await session.execute(
            select(TranslationJob.created_at)
            .join(Chapter, TranslationJob.chapter_id == Chapter.id)
            .where(Chapter.manga_id == manga.id)
            .order_by(TranslationJob.created_at.desc())
            .limit(1)
        )
        last_activity = last_job.scalar() or manga.updated_at

        # Count chapters directly (avoid async lazy-load)
        chapter_count = (await session.execute(
            select(func.count(Chapter.id)).where(Chapter.manga_id == manga.id)
        )).scalar() or 0

        responses.append(ProjectSummary(
            id=manga.id,
            title=manga.title,
            title_original=manga.title_original,
            author=manga.author,
            cover_image_path=manga.cover_image_path,
            source_language=manga.source_language,
            target_language=manga.target_language,
            chapter_count=chapter_count,
            total_pages=total_pages,
            translated_pages=translated_pages,
            translation_progress=round(progress, 1),
            last_activity=last_activity,
            created_at=manga.created_at,
        ))

    return responses


@router.get("/{manga_id}", response_model=ProjectResponse)
async def get_project(manga_id: str, session: AsyncSession = Depends(get_session)):
    """Get a manga project with full details and stats."""
    manga = await session.get(Manga, manga_id)
    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")

    # Count pages and translation progress
    pages_result = await session.execute(
        select(func.count(), func.sum(case((Page.is_translated == True, 1), else_=0)))
        .select_from(Page)
        .join(Chapter, Page.chapter_id == Chapter.id)
        .where(Chapter.manga_id == manga.id)
    )
    row = pages_result.one()
    total_pages = row[0] or 0
    translated_pages = row[1] or 0
    progress = (translated_pages / total_pages * 100) if total_pages > 0 else 0.0

    # Last translated at
    last_translated = await session.execute(
        select(TranslationJob.completed_at)
        .join(Chapter, TranslationJob.chapter_id == Chapter.id)
        .where(Chapter.manga_id == manga.id, TranslationJob.status == JobStatus.COMPLETED)
        .order_by(TranslationJob.completed_at.desc())
        .limit(1)
    )

    # Count chapters directly (avoid async lazy-load)
    chapter_count = (await session.execute(
        select(func.count(Chapter.id)).where(Chapter.manga_id == manga.id)
    )).scalar() or 0

    resp = ProjectResponse(
        id=manga.id,
        title=manga.title,
        title_original=manga.title_original,
        author=manga.author,
        artist=manga.artist,
        description=manga.description,
        cover_image_path=manga.cover_image_path,
        source_language=manga.source_language,
        target_language=manga.target_language,
        tags=manga.tags,
        chapter_count=chapter_count,
        total_pages=total_pages,
        translated_pages=translated_pages,
        translation_progress=round(progress, 1),
        last_translated_at=last_translated.scalar(),
        created_at=manga.created_at,
        updated_at=manga.updated_at,
    )
    return resp


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create a new manga translation project."""
    manga = Manga(
        id=str(uuid.uuid4()),
        title=data.title,
        title_original=data.title_original,
        author=data.author,
        artist=data.artist,
        description=data.description,
        source_language=data.source_language,
        target_language=data.target_language,
        tags=data.tags,
    )
    session.add(manga)
    await session.flush()
    logger.info("Created project: %s (ID: %s)", manga.title, manga.id)

    return ProjectResponse(
        id=manga.id,
        title=manga.title,
        title_original=manga.title_original,
        author=manga.author,
        artist=manga.artist,
        description=manga.description,
        source_language=manga.source_language,
        target_language=manga.target_language,
        tags=manga.tags,
        chapter_count=0,
        total_pages=0,
        translated_pages=0,
        translation_progress=0.0,
        created_at=manga.created_at,
        updated_at=manga.updated_at,
    )


@router.put("/{manga_id}", response_model=ProjectResponse)
async def update_project(
    manga_id: str,
    data: ProjectUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update an existing manga project."""
    manga = await session.get(Manga, manga_id)
    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(manga, key, value)

    session.add(manga)
    await session.flush()
    await session.refresh(manga)
    logger.info("Updated project: %s (ID: %s)", manga.title, manga.id)

    # Return response with counts from fresh query
    chapter_count = (await session.execute(
        select(func.count(Chapter.id)).where(Chapter.manga_id == manga.id)
    )).scalar() or 0

    return ProjectResponse(
        id=manga.id,
        title=manga.title,
        title_original=manga.title_original,
        author=manga.author,
        artist=manga.artist,
        description=manga.description,
        cover_image_path=manga.cover_image_path,
        source_language=manga.source_language,
        target_language=manga.target_language,
        tags=manga.tags,
        chapter_count=chapter_count,
        total_pages=0,
        translated_pages=0,
        translation_progress=0.0,
        created_at=manga.created_at,
        updated_at=manga.updated_at,
    )


@router.delete("/{manga_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(manga_id: str, session: AsyncSession = Depends(get_session)):
    """Delete a manga project and all associated data (chapters, pages, uploads)."""
    manga = await session.get(Manga, manga_id)
    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")

    # Delete uploaded files
    upload_service.delete_manga_files(manga_id)

    # Delete database records (cascades to chapters, pages, bubbles)
    await session.delete(manga)
    await session.flush()
    logger.info("Deleted project: %s (ID: %s)", manga.title, manga_id)


@router.get("/{manga_id}/stats", response_model=ProjectStats)
async def get_project_stats(manga_id: str, session: AsyncSession = Depends(get_session)):
    """Get detailed statistics for a manga project."""
    manga = await session.get(Manga, manga_id)
    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")

    # Chapters
    chapters_result = await session.execute(
        select(func.count(Chapter.id)).where(Chapter.manga_id == manga_id)
    )
    total_chapters = chapters_result.scalar() or 0

    translated_chapters_result = await session.execute(
        select(func.count(Chapter.id)).where(
            Chapter.manga_id == manga_id, Chapter.is_translated == True
        )
    )
    translated_chapters = translated_chapters_result.scalar() or 0

    # Pages
    pages_result = await session.execute(
        select(func.count(), func.sum(case((Page.is_translated == True, 1), else_=0)))
        .select_from(Page)
        .join(Chapter, Page.chapter_id == Chapter.id)
        .where(Chapter.manga_id == manga_id)
    )
    row = pages_result.one()
    total_pages = row[0] or 0
    translated_pages = row[1] or 0

    # Bubbles
    bubbles_result = await session.execute(
        select(func.count())
        .select_from(Bubble)
        .join(Page, Bubble.page_id == Page.id)
        .join(Chapter, Page.chapter_id == Chapter.id)
        .where(Chapter.manga_id == manga_id)
    )
    total_bubbles = bubbles_result.scalar() or 0

    # Jobs
    jobs_query = (
        select(func.count(TranslationJob.id))
        .select_from(TranslationJob)
        .join(Chapter, TranslationJob.chapter_id == Chapter.id)
        .where(Chapter.manga_id == manga_id)
    )
    total_jobs = (await session.execute(jobs_query)).scalar() or 0

    completed_jobs_query = (
        select(func.count(TranslationJob.id))
        .select_from(TranslationJob)
        .join(Chapter, TranslationJob.chapter_id == Chapter.id)
        .where(
            Chapter.manga_id == manga_id,
            TranslationJob.status == JobStatus.COMPLETED,
        )
    )
    completed_jobs = (await session.execute(completed_jobs_query)).scalar() or 0

    failed_jobs_query = (
        select(func.count(TranslationJob.id))
        .select_from(TranslationJob)
        .join(Chapter, TranslationJob.chapter_id == Chapter.id)
        .where(
            Chapter.manga_id == manga_id,
            TranslationJob.status == JobStatus.FAILED,
        )
    )
    failed_jobs = (await session.execute(failed_jobs_query)).scalar() or 0

    # Total processing time
    time_result = await session.execute(
        select(func.sum(Page.processing_time_ms))
        .select_from(Page)
        .join(Chapter, Page.chapter_id == Chapter.id)
        .where(Chapter.manga_id == manga_id)
    )
    total_time = time_result.scalar() or 0.0

    storage_bytes = upload_service.get_storage_size(manga_id)
    progress = (translated_pages / total_pages * 100) if total_pages > 0 else 0.0

    return ProjectStats(
        project_id=manga_id,
        title=manga.title,
        total_chapters=total_chapters,
        total_pages=total_pages,
        translated_chapters=translated_chapters,
        translated_pages=translated_pages,
        translation_progress=round(progress, 1),
        total_bubbles=total_bubbles,
        total_jobs=total_jobs,
        completed_jobs=completed_jobs,
        failed_jobs=failed_jobs,
        total_processing_time_ms=total_time,
        storage_size_bytes=storage_bytes,
    )


@router.post("/{manga_id}/duplicate")
async def duplicate_project(
    manga_id: str,
    new_title: Optional[str] = Query(None, description="Title for the duplicated project"),
    session: AsyncSession = Depends(get_session),
):
    """Duplicate a project including its chapters structure (but not page files)."""
    original = await session.get(Manga, manga_id)
    if not original:
        raise HTTPException(status_code=404, detail="Manga not found")

    # Create duplicate
    duplicate = Manga(
        id=str(uuid.uuid4()),
        title=new_title or f"{original.title} (Copy)",
        title_original=original.title_original,
        author=original.author,
        artist=original.artist,
        description=original.description,
        source_language=original.source_language,
        target_language=original.target_language,
        tags=original.tags,
    )
    session.add(duplicate)
    await session.flush()

    # Duplicate chapters (structure only, no page files)
    chapters_result = await session.execute(
        select(Chapter).where(Chapter.manga_id == manga_id).order_by(Chapter.chapter_number)
    )
    for ch in chapters_result.scalars().all():
        dup_chapter = Chapter(
            id=str(uuid.uuid4()),
            manga_id=duplicate.id,
            chapter_number=ch.chapter_number,
            title=ch.title,
        )
        session.add(dup_chapter)

    await session.flush()
    logger.info("Duplicated project %s -> %s", manga_id, duplicate.id)

    return {"message": "Project duplicated", "new_id": duplicate.id, "new_title": duplicate.title}


# ── Chapter Endpoints (Enhanced) ─────────────────────────────────────────


@router.get("/{manga_id}/chapters", response_model=list[ChapterResponse])
async def list_chapters(
    manga_id: str,
    include_pages: bool = Query(False, description="Include page count info"),
    translated_only: bool = Query(False, description="Only show translated chapters"),
    session: AsyncSession = Depends(get_session),
):
    """List all chapters for a manga."""
    manga = await session.get(Manga, manga_id)
    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")

    query = (
        select(Chapter)
        .where(Chapter.manga_id == manga_id)
        .order_by(Chapter.chapter_number)
    )

    if translated_only:
        query = query.where(Chapter.is_translated == True)

    result = await session.execute(query)
    chapters = result.scalars().all()

    responses = []
    for c in chapters:
        resp = ChapterResponse.model_validate(c)

        if include_pages:
            pages_result = await session.execute(
                select(func.count(), func.sum(case((Page.is_translated == True, 1), else_=0)))
                .where(Page.chapter_id == c.id)
            )
            row = pages_result.one()
            resp.page_count = row[0] or 0

        responses.append(resp)

    return responses


@router.post(
    "/{manga_id}/chapters",
    response_model=ChapterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_chapter(
    manga_id: str,
    data: ChapterCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create a new chapter for a manga."""
    manga = await session.get(Manga, manga_id)
    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")

    # Check for duplicate chapter number
    existing = await session.execute(
        select(Chapter).where(
            Chapter.manga_id == manga_id,
            Chapter.chapter_number == data.chapter_number,
        )
    )
    if existing.scalar():
        raise HTTPException(
            status_code=409,
            detail=f"Chapter {data.chapter_number} already exists for this manga",
        )

    chapter = Chapter(
        id=str(uuid.uuid4()),
        manga_id=manga_id,
        chapter_number=data.chapter_number,
        title=data.title,
        page_count=data.page_count,
    )
    session.add(chapter)
    await session.flush()
    logger.info("Created chapter %s for manga %s", chapter.chapter_number, manga_id)

    return ChapterResponse.model_validate(chapter)


@router.put("/{manga_id}/chapters/{chapter_id}", response_model=ChapterResponse)
async def update_chapter(
    manga_id: str,
    chapter_id: str,
    data: ChapterCreate,
    session: AsyncSession = Depends(get_session),
):
    """Update a chapter."""
    chapter = await session.get(Chapter, chapter_id)
    if not chapter or chapter.manga_id != manga_id:
        raise HTTPException(status_code=404, detail="Chapter not found")

    chapter.chapter_number = data.chapter_number
    if data.title is not None:
        chapter.title = data.title
    chapter.page_count = data.page_count
    session.add(chapter)
    await session.flush()

    return ChapterResponse.model_validate(chapter)


@router.delete(
    "/{manga_id}/chapters/{chapter_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_chapter(
    manga_id: str,
    chapter_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Delete a chapter and its pages."""
    chapter = await session.get(Chapter, chapter_id)
    if not chapter or chapter.manga_id != manga_id:
        raise HTTPException(status_code=404, detail="Chapter not found")

    # Delete uploaded files
    upload_service.delete_chapter_files(manga_id, chapter_id)

    await session.delete(chapter)
    await session.flush()
    logger.info("Deleted chapter %s from manga %s", chapter_id, manga_id)


# ── Page Endpoints ────────────────────────────────────────────────────────


@router.get("/{manga_id}/chapters/{chapter_id}/pages", response_model=list[PageResponse])
async def list_pages(
    manga_id: str,
    chapter_id: str,
    session: AsyncSession = Depends(get_session),
):
    """List all pages for a chapter, ordered by page number."""
    chapter = await session.get(Chapter, chapter_id)
    if not chapter or chapter.manga_id != manga_id:
        raise HTTPException(status_code=404, detail="Chapter not found")

    result = await session.execute(
        select(Page)
        .where(Page.chapter_id == chapter_id)
        .order_by(Page.page_number)
    )
    pages = result.scalars().all()

    responses = []
    for page in pages:
        # Count bubbles for this page
        bubble_count = (await session.execute(
            select(func.count(Bubble.id)).where(Bubble.page_id == page.id)
        )).scalar() or 0

        responses.append(PageResponse(
            id=page.id,
            chapter_id=page.chapter_id,
            page_number=page.page_number,
            original_image_path=page.original_image_path,
            translated_image_path=page.translated_image_path,
            width=page.width,
            height=page.height,
            is_translated=page.is_translated,
            bubble_count=bubble_count,
        ))

    return responses


@router.get("/{manga_id}/chapters/{chapter_id}/pages/{page_id}", response_model=PageResponse)
async def get_page(
    manga_id: str,
    chapter_id: str,
    page_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get a single page with bubble count."""
    chapter = await session.get(Chapter, chapter_id)
    if not chapter or chapter.manga_id != manga_id:
        raise HTTPException(status_code=404, detail="Chapter not found")

    page = await session.get(Page, page_id)
    if not page or page.chapter_id != chapter_id:
        raise HTTPException(status_code=404, detail="Page not found")

    bubble_count = (await session.execute(
        select(func.count(Bubble.id)).where(Bubble.page_id == page.id)
    )).scalar() or 0

    return PageResponse(
        id=page.id,
        chapter_id=page.chapter_id,
        page_number=page.page_number,
        original_image_path=page.original_image_path,
        translated_image_path=page.translated_image_path,
        width=page.width,
        height=page.height,
        is_translated=page.is_translated,
        bubble_count=bubble_count,
    )


@router.get("/{manga_id}/chapters/{chapter_id}/bubbles")
async def list_chapter_bubbles(
    manga_id: str,
    chapter_id: str,
    session: AsyncSession = Depends(get_session),
):
    """List all bubbles for all pages in a chapter."""
    chapter = await session.get(Chapter, chapter_id)
    if not chapter or chapter.manga_id != manga_id:
        raise HTTPException(status_code=404, detail="Chapter not found")

    result = await session.execute(
        select(Bubble)
        .join(Page, Bubble.page_id == Page.id)
        .where(Page.chapter_id == chapter_id)
        .order_by(Page.page_number, Bubble.reading_order)
    )
    bubbles = result.scalars().all()

    return [
        {
            "id": b.id,
            "page_id": b.page_id,
            "bubble_type": b.bubble_type,
            "x": b.x,
            "y": b.y,
            "width": b.width,
            "height": b.height,
            "polygon": b.polygon_json,
            "confidence": b.confidence,
            "reading_order": b.reading_order,
            "original_text": b.original_text,
            "translated_text": b.translated_text,
            "is_translated": b.is_translated,
            "rotation": b.rotation,
            "detector_engine": b.detector_engine,
            "has_precise_mask": b.has_precise_mask,
        }
        for b in bubbles
    ]
