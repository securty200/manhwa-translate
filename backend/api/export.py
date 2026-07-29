"""Enhanced export API routes for downloading translated manga chapters.

Supports 7 formats: PDF, PNG, JPG, WEBP, ZIP, CBZ, CBR.
Features:
- Page range selection
- Background export with progress
- Format info endpoint
- Task management (status, cancel, download, delete)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.session import get_session
from backend.models.manga import Chapter, Manga, Page
from backend.schemas.export import (
    ExportFormatInfo,
    ExportRequest,
    ExportTaskResponse,
    ExportTaskStatus,
    SUPPORTED_FORMATS,
)
from backend.services.export_service import ExportService

logger = logging.getLogger(__name__)

router = APIRouter()
export_service = ExportService()


@router.get("/formats", response_model=dict[str, ExportFormatInfo])
async def list_export_formats():
    """List all supported export formats with metadata.

    Returns format details including extension, description,
    quality support, and MIME type.
    """
    return SUPPORTED_FORMATS


@router.post("", response_model=ExportTaskResponse)
async def create_export(
    data: ExportRequest,
    manga_id: Optional[str] = Query(None, description="Manga ID for title resolution"),
    session: AsyncSession = Depends(get_session),
):
    """Create an export task for one or more translated chapters.

    Supported formats: pdf, png, jpg, webp, zip, cbz, cbr
    Page range: "1-5,8,10-15" or "" for all pages
    """
    manga_title = "Manga"
    chapter_data = []

    for chapter_id in data.chapter_ids[:]:
        chapter = await session.get(Chapter, chapter_id)
        if not chapter:
            raise HTTPException(
                status_code=404,
                detail=f"Chapter {chapter_id} not found",
            )

        if manga_id:
            manga = await session.get(Manga, manga_id)
            if manga:
                manga_title = manga.title

        # Gather pages for this chapter
        pages_result = await session.execute(
            select(Page)
            .where(Page.chapter_id == chapter_id)
            .order_by(Page.page_number)
        )
        pages = list(pages_result.scalars().all())

        chapter_data.append({
            "id": chapter_id,
            "number": chapter.chapter_number,
            "title": chapter.title or "",
            "pages": [
                {
                    "id": p.id,
                    "number": p.page_number,
                    "original_path": p.original_image_path,
                    "translated_path": p.translated_image_path,
                    "is_translated": p.is_translated,
                }
                for p in pages
            ],
        })

    # Calculate estimated pages and size
    total_pages = sum(len(c["pages"]) for c in chapter_data)
    if data.page_range:
        # Rough estimate using first chapter's page count
        try:
            parts = data.page_range.split(",")
            count = 0
            for part in parts:
                part = part.strip()
                if "-" in part:
                    s, e = part.split("-", 1)
                    count += int(e.strip()) - int(s.strip()) + 1
                else:
                    count += 1
            total_pages = count * len(data.chapter_ids)
        except (ValueError, TypeError):
            pass

    # Start export task
    task = await export_service.create_export(
        chapter_ids=data.chapter_ids,
        format=data.format,
        include_original=data.include_original,
        quality=data.quality,
        page_range=data.page_range,
        filename_template=data.filename_template,
        manga_title=manga_title,
        chapter_data=chapter_data,
    )

    # Estimate size: ~0.5 MB per page for JPEG quality 90
    estimated_size_mb = round(
        total_pages * (0.5 * (data.quality / 90)), 1
    )

    fmt_info = SUPPORTED_FORMATS.get(data.format, {})
    fmt_name = fmt_info.format if hasattr(fmt_info, 'format') else data.format

    return ExportTaskResponse(
        task_id=task.id,
        status=task.status,
        format=fmt_name,
        message=(
            f"Export started for {len(data.chapter_ids)} chapter(s) "
            f"({total_pages} pages) as {data.format.upper()}"
        ),
        estimated_chapters=len(data.chapter_ids),
        estimated_pages=total_pages,
        estimated_size_mb=estimated_size_mb,
    )


@router.get("/tasks", response_model=list[ExportTaskStatus])
async def list_export_tasks():
    """List all active export tasks with their status."""
    tasks = []
    for task_id, task in export_service.active_tasks.items():
        tasks.append(_task_to_status(task))
    return tasks


@router.get("/tasks/{task_id}", response_model=ExportTaskStatus)
async def get_export_task(task_id: str):
    """Get the detailed status of an export task."""
    task = export_service.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=404,
            detail="Export task not found",
        )
    return _task_to_status(task)


@router.post("/tasks/{task_id}/cancel")
async def cancel_export_task(task_id: str):
    """Cancel a pending or in-progress export task."""
    cancelled = export_service.cancel_task(task_id)
    if not cancelled:
        raise HTTPException(
            status_code=404,
            detail="Export task not found or already completed",
        )
    return {
        "message": "Export task cancelled",
        "task_id": task_id,
    }


@router.get("/download/{task_id}")
async def download_export(task_id: str):
    """Download a completed export file.

    For image format exports (png, jpg, webp), creates a ZIP
    on-the-fly and returns it. For archive formats (cbz, zip, cbr)
    and pdf, returns the file directly.
    """
    task = export_service.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=404,
            detail="Export task not found",
        )

    if task.status != "completed" or not task.output_path:
        raise HTTPException(
            status_code=400,
            detail=f"Export is not ready (status: {task.status})",
        )

    output_path = Path(task.output_path)

    # Image format exports are directories — ZIP them for download
    if output_path.is_dir():
        import tempfile
        import shutil

        temp_zip = Path(tempfile.mktemp(suffix=".zip"))
        try:
            archive_path = shutil.make_archive(
                str(temp_zip.with_suffix("")),
                "zip",
                output_path,
            )
            return FileResponse(
                path=archive_path,
                filename=f"{output_path.name}.zip",
                media_type="application/zip",
            )
        except Exception as e:
            logger.error("Failed to ZIP image export: %s", e)
            raise HTTPException(
                status_code=500,
                detail="Failed to prepare export for download",
            )

    if not output_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Export file not found on disk",
        )

    # Determine media type
    fmt = task.format.lower()
    fmt_info = SUPPORTED_FORMATS.get(fmt)
    media_type = (
        fmt_info.mime_type if fmt_info else "application/octet-stream"
    )

    return FileResponse(
        path=output_path,
        filename=output_path.name,
        media_type=media_type,
    )


@router.delete("/tasks/{task_id}")
async def delete_export_task(task_id: str):
    """Cancel and delete an export task and its files."""
    task = export_service.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=404,
            detail="Export task not found",
        )

    # Delete the output file/directory
    if task.output_path:
        try:
            out_path = Path(task.output_path)
            if out_path.exists():
                if out_path.is_file():
                    out_path.unlink(missing_ok=True)
                elif out_path.is_dir():
                    import shutil
                    shutil.rmtree(out_path)
        except Exception as e:
            logger.warning("Failed to delete export path: %s", e)

    # Remove from active tasks
    if task_id in export_service.active_tasks:
        del export_service.active_tasks[task_id]

    return {
        "message": "Export task deleted",
        "task_id": task_id,
    }


@router.post("/cleanup")
async def cleanup_old_exports(
    max_age_hours: int = Query(
        default=24, ge=1, le=168,
        description="Delete exports older than this many hours",
    ),
):
    """Clean up old export files and completed tasks."""
    deleted = export_service.cleanup_old_exports(
        max_age_hours=max_age_hours,
    )
    return {
        "message": f"Cleaned up {deleted} old export(s)",
        "files_deleted": deleted,
    }


def _task_to_status(task) -> ExportTaskStatus:
    """Convert an ExportTask to an ExportTaskStatus schema."""
    return ExportTaskStatus(
        id=task.id,
        status=task.status,
        progress=task.progress,
        format=task.format,
        total_pages=task.total_pages,
        completed_pages=task.completed_pages,
        output_path=task.output_path,
        total_size_bytes=task.total_size_bytes,
        total_size_mb=(
            round(task.total_size_bytes / (1024 * 1024), 2)
            if task.total_size_bytes else None
        ),
        error_message=task.error_message,
        created_at=task.created_at,
        completed_at=task.completed_at,
    )
