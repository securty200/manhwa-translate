"""File upload API routes for manga page images and covers."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.session import get_session
from backend.models.manga import Chapter, Manga, Page
from backend.schemas.manga import PageResponse
from backend.services.upload_service import UploadService

logger = logging.getLogger(__name__)

router = APIRouter()
upload_service = UploadService()


@router.post("/{manga_id}/chapters/{chapter_id}/pages", response_model=list[PageResponse])
async def upload_pages(
    manga_id: str,
    chapter_id: str,
    files: list[UploadFile] = File(..., description="Page images to upload (jpg, png, webp)"),
    session: AsyncSession = Depends(get_session),
):
    """Upload one or more page images to a chapter.

    Supports JPEG, PNG, WebP, BMP, TIFF formats.
    Files are automatically numbered in order of upload.
    """
    # Verify manga and chapter exist
    manga = await session.get(Manga, manga_id)
    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")

    chapter = await session.get(Chapter, chapter_id)
    if not chapter or chapter.manga_id != manga_id:
        raise HTTPException(status_code=404, detail="Chapter not found")

    # Get current max page number
    from sqlalchemy import select, func
    max_page_result = await session.execute(
        select(func.max(Page.page_number)).where(Page.chapter_id == chapter_id)
    )
    start_page = (max_page_result.scalar() or 0) + 1

    # Upload each file
    results = []
    created_pages = []

    for i, file in enumerate(files):
        content = await file.read()
        result = await upload_service.upload_page(
            content=content,
            filename=file.filename or f"page_{start_page + i}.png",
            manga_id=manga_id,
            chapter_id=chapter_id,
            page_number=start_page + i,
        )

        if not result.success:
            logger.warning("Upload failed for %s: %s", file.filename, result.error_message)
            # Clean up any previously created pages
            for p in created_pages:
                await session.delete(p)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Upload failed for {file.filename}: {result.error_message}",
            )

        # Create database record
        page = Page(
            id=str(uuid.uuid4()),
            chapter_id=chapter_id,
            page_number=result.page_number,
            original_image_path=result.file_path,
            width=result.width,
            height=result.height,
        )
        session.add(page)
        created_pages.append(page)
        results.append(result)

    # Update chapter page count
    chapter.page_count = (await session.execute(
        select(func.count(Page.id)).where(Page.chapter_id == chapter_id)
    )).scalar() or 0
    session.add(chapter)

    await session.flush()

    logger.info(
        "Uploaded %d pages to chapter %s (pages %d-%d)",
        len(results), chapter_id, start_page, start_page + len(results) - 1,
    )

    # Build response
    pages_db = []
    for page in created_pages:
        resp = PageResponse.model_validate(page)
        pages_db.append(resp)

    return pages_db


@router.post("/{manga_id}/cover")
async def upload_cover(
    manga_id: str,
    file: UploadFile = File(..., description="Cover image"),
    session: AsyncSession = Depends(get_session),
):
    """Upload a cover image for a manga.

    Cover images are automatically resized to a standard thumbnail size.
    """
    manga = await session.get(Manga, manga_id)
    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")

    content = await file.read()
    result = await upload_service.upload_cover(
        content=content,
        filename=file.filename or "cover.jpg",
        manga_id=manga_id,
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error_message,
        )

    manga.cover_image_path = result.file_path
    session.add(manga)
    await session.flush()

    return {
        "message": "Cover uploaded successfully",
        "file_path": result.file_path,
        "width": result.width,
        "height": result.height,
    }


@router.get("/{manga_id}/storage")
async def get_storage_info(
    manga_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get storage usage information for a manga."""
    manga = await session.get(Manga, manga_id)
    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")

    size_bytes = upload_service.get_storage_size(manga_id)

    # Count files
    import glob
    manga_dir = upload_service.upload_dir / manga_id
    file_count = 0
    if manga_dir.exists():
        file_count = len(list(manga_dir.rglob("*")))

    return {
        "manga_id": manga_id,
        "storage_bytes": size_bytes,
        "storage_mb": round(size_bytes / (1024 * 1024), 2),
        "file_count": file_count,
    }
