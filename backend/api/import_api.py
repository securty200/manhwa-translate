"""Import API routes for manga files — PDF, CBZ, CBR, ZIP, and images."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.session import get_session
from backend.models.manga import Chapter, Manga, Page
from backend.schemas.import_schema import (
    ImportFolderRequest,
    ImportPageInfo,
    ImportRequest,
    ImportResponse,
)
from datetime import datetime

from backend.services.import_service import ImportService, ImportResult, SUPPORTED_EXTENSIONS
from backend.services.upload_service import UploadService

logger = logging.getLogger(__name__)

router = APIRouter()
import_service = ImportService()
upload_service = UploadService()


@router.post("", response_model=ImportResponse, status_code=status.HTTP_201_CREATED)
async def import_manga_file(
    file: UploadFile = File(..., description="Manga file: PDF, CBZ, CBR, ZIP, or image (PNG, JPG, WEBP, TIFF)"),
    project_title: str = Query("Imported Manga", description="Auto-created project title"),
    chapter_number: float = Query(1.0, ge=0, description="Chapter number to assign"),
    source_language: str = Query("ja", description="Source language code"),
    target_language: str = Query("en", description="Target language code"),
    author: Optional[str] = Query(None, description="Author name"),
    generate_thumbnails: bool = Query(True, description="Generate thumbnail images"),
    auto_create_project: bool = Query(True, description="Auto-create project and chapter in database"),
    session: AsyncSession = Depends(get_session),
):
    """Import a manga file and automatically create a project + chapter.

    **Supported formats:**
    - **PDF** — Extracts all pages (requires PyMuPDF or pdf2image)
    - **CBZ** — Comic book ZIP archives
    - **CBR** — Comic book RAR archives (requires rarfile)
    - **ZIP** — ZIP archives containing images
    - **PNG, JPG, WEBP, TIFF, BMP** — Single image files

    **Features:**
    - Extracts every page maintaining correct reading order
    - Natural filename sorting for CBZ/CBR/ZIP
    - Generates cover thumbnails
    - Stores extracted metadata in the database
    - Auto-creates manga project and chapter
    - Handles corrupted pages gracefully (skips with error)
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Validate file extension
    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file format: {ext}. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )

    # Read file content
    content = await file.read()

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    # Import the file
    try:
        result = await import_service.import_file(
            file_content=content,
            filename=file.filename,
            project_title=project_title,
            chapter_number=chapter_number,
            source_language=source_language,
            target_language=target_language,
            author=author,
            generate_thumbnails=generate_thumbnails,
        )
    except Exception as e:
        logger.error("Import failed for %s: %s", file.filename, e)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to import {file.filename}: {str(e)[:500]}",
        )

    # Save to database
    if auto_create_project:
        try:
            result = await _save_to_database(session, result, file.filename, project_title)
        except Exception as e:
            logger.error("Database save failed after import: %s", e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Imported pages extracted but database save failed: {str(e)[:500]}",
            )

    # Build response
    response_pages = []
    for p in result.pages[:200]:  # Limit page details in response
        response_pages.append(ImportPageInfo(
            page_number=p.page_number,
            filename=p.filename,
            width=p.width,
            height=p.height,
            file_size_bytes=p.file_size_bytes,
            original_format=p.original_format,
            success=p.success,
            error_message=p.error_message if not p.success else "",
        ))

    return ImportResponse(
        project_id=result.project_id,
        project_title=result.project_title or project_title,
        chapter_id=result.chapter_id,
        chapter_number=result.chapter_number,
        total_pages=result.total_files,
        successful_pages=result.successful_pages,
        failed_pages=result.failed_pages,
        import_format=result.import_format,
        source_filename=result.source_filename,
        total_size_bytes=result.total_size_bytes,
        duration_ms=result.duration_ms,
        pages=response_pages,
        errors=result.errors[:50],  # Limit errors
        thumbnail_paths=result.thumbnail_paths,
        metadata=result.metadata,
        created_at=datetime.utcnow(),
    )


async def _save_to_database(
    session: AsyncSession,
    result: ImportResult,
    filename: str,
    project_title: str,
) -> ImportResult:
    """Save the imported data to the database.

    Creates or finds a manga project and chapter, then adds all pages.
    """
    import uuid as _uuid

    # Use detected title from metadata or fallback to project_title
    title = result.metadata.get("detected_title") or project_title

    # Check if a project with this title already exists
    existing = await session.execute(
        select(Manga).where(Manga.title.ilike(f"%{title}%")).limit(1)
    )
    manga = existing.scalar()

    if not manga:
        # Create new project
        manga = Manga(
            id=result.project_id,
            title=title,
            source_language="ja",
            target_language="en",
            author=result.source_filename,
            metadata_json=result.metadata,
        )
        session.add(manga)
        await session.flush()
    else:
        # Use existing project
        result.project_id = manga.id
        result.project_title = manga.title

    # Create chapter
    chapter = Chapter(
        id=result.chapter_id,
        manga_id=manga.id,
        chapter_number=result.chapter_number or 1.0,
        title=Path(filename).stem[:255],
        page_count=result.successful_pages,
    )
    session.add(chapter)
    await session.flush()

    # Save page images to disk
    saved_pages = await import_service.save_pages(result.pages, manga.id, chapter.id)

    # Create page records
    for saved in saved_pages:
        page = Page(
            id=str(_uuid.uuid4()),
            chapter_id=chapter.id,
            page_number=saved["page_number"],
            original_image_path=saved["file_path"],
            width=saved["width"],
            height=saved["height"],
        )
        session.add(page)

    await session.commit()

    # Use the cover as the project thumbnail
    if result.thumbnail_paths:
        manga.cover_image_path = result.thumbnail_paths[0]
        session.add(manga)
        await session.commit()

    logger.info(
        "Saved import to DB: project=%s chapter=%s pages=%d",
        manga.id, chapter.id, result.successful_pages,
    )

    return result


@router.post("/folder", response_model=ImportResponse, status_code=status.HTTP_201_CREATED)
async def import_manga_folder(
    data: ImportFolderRequest,
    session: AsyncSession = Depends(get_session),
):
    """Import a folder of images from the server filesystem as a manga chapter.

    Scans the folder for image files (PNG, JPG, WEBP, TIFF, BMP),
    sorts them by natural filename order, and imports them.

    **Security note:** This endpoint accesses the server filesystem directly.
    Only use in trusted environments or restrict folder paths.
    """
    folder_path = Path(data.folder_path)
    if not folder_path.exists():
        raise HTTPException(status_code=404, detail=f"Folder not found: {data.folder_path}")
    if not folder_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {data.folder_path}")

    try:
        result = await import_service.import_folder(
            folder_path=str(folder_path),
            project_title=data.project_title,
            chapter_number=data.chapter_number,
            source_language=data.source_language,
            target_language=data.target_language,
            generate_thumbnails=data.generate_thumbnails,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)[:500],
        )

    # Save to database
    try:
        result = await _save_to_database(session, result, folder_path.name, data.project_title)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Folder import extracted but database save failed: {str(e)[:500]}",
        )

    response_pages = []
    for p in result.pages[:200]:
        response_pages.append(ImportPageInfo(
            page_number=p.page_number,
            filename=p.filename,
            width=p.width,
            height=p.height,
            file_size_bytes=p.file_size_bytes,
            original_format=p.original_format,
            success=p.success,
            error_message=p.error_message if not p.success else "",
        ))

    return ImportResponse(
        project_id=result.project_id,
        project_title=result.project_title or data.project_title,
        chapter_id=result.chapter_id,
        chapter_number=result.chapter_number,
        total_pages=result.total_files,
        successful_pages=result.successful_pages,
        failed_pages=result.failed_pages,
        import_format="folder",
        source_filename=folder_path.name,
        total_size_bytes=result.total_size_bytes,
        duration_ms=result.duration_ms,
        pages=response_pages,
        errors=result.errors[:50],
        thumbnail_paths=result.thumbnail_paths,
        metadata=result.metadata,
        created_at=datetime.utcnow(),
    )


@router.get("/supported-formats")
async def get_supported_formats():
    """Get a list of all supported import formats."""
    from backend.services.import_service import SUPPORTED_EXTENSIONS, IMAGE_EXTENSIONS, ARCHIVE_EXTENSIONS, PDF_EXTENSION

    return {
        "supported_formats": sorted(SUPPORTED_EXTENSIONS),
        "images": sorted(IMAGE_EXTENSIONS),
        "archives": sorted(ARCHIVE_EXTENSIONS),
        "pdf": sorted(PDF_EXTENSION),
        "max_file_size_mb": 500,
        "max_page_size_mb": 50,
        "description": (
            "Upload PDF, CBZ, CBR, ZIP archives, or individual image files. "
            "All pages are extracted in natural order, thumbnails generated, "
            "and stored in the database. Corrupted files are handled gracefully."
        ),
    }
