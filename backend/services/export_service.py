"""Enhanced export service for generating downloadable manga archives.

Supports 7 formats: PDF, PNG, JPG, WEBP, ZIP, CBZ, CBR.
Features:
- Page selection (ranges like "1-5,8,10-15" or empty for all)
- Background exporting with progress callbacks
- Image quality control per format
- Comprehensive metadata (ComicRack for CBZ, bookmarks for PDF)
- Preserves page order and image quality
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.config import settings
from backend.services.export.engines import (
    EXPORT_ENGINE_REGISTRY,
    DEFAULT_EXPORT_PRIORITY,
    BaseExportEngine,
    ExportChapter,
    ExportOptions,
    ExportPage,
    ExportProgress,
)

logger = logging.getLogger(__name__)


@dataclass
class ExportTask:
    """Represents an export task in progress."""

    id: str
    status: str = "pending"  # pending, processing, completed, failed
    progress: float = 0.0
    format: str = "cbz"
    chapter_ids: list[str] = field(default_factory=list)
    output_path: Optional[str] = None
    total_size_bytes: Optional[int] = None
    error_message: Optional[str] = None
    total_pages: int = 0
    completed_pages: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


class ExportService:
    """Enhanced service for exporting translated manga chapters.

    Uses modular export engines for each format.
    Supports background export with progress tracking.
    """

    def __init__(self) -> None:
        self.export_dir = settings.CACHE_DIR / "exports"
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.active_tasks: dict[str, ExportTask] = {}

    def _get_format_engine(self, fmt: str) -> BaseExportEngine:
        """Get the export engine for a given format.

        Args:
            fmt: Format string (pdf, png, jpg, jpeg, webp, zip, cbz, cbr).

        Returns:
            Initialized export engine.

        Raises:
            ValueError: If format is not supported.
        """
        fmt_lower = fmt.lower().strip()

        # Normalize jpeg → jpg for engine lookup
        engine_key = "jpg" if fmt_lower == "jpeg" else fmt_lower

        engine_cls = EXPORT_ENGINE_REGISTRY.get(engine_key)
        if engine_cls is None:
            raise ValueError(
                f"Unsupported export format: '{fmt}'. "
                f"Supported: {', '.join(EXPORT_ENGINE_REGISTRY.keys())}"
            )

        # Image engine needs format param
        if engine_key in ("png", "jpg", "webp"):
            fmt_name = {"png": "PNG", "jpg": "JPEG", "webp": "WEBP"}[engine_key]
            engine = engine_cls(image_format=fmt_name)
        else:
            engine = engine_cls()

        return engine

    async def create_export(
        self,
        chapter_ids: list[str],
        format: str = "cbz",
        include_original: bool = False,
        quality: int = 90,
        page_range: str = "",
        filename_template: str = "{manga_title}_Chapter_{chapter_number}",
        manga_title: str = "Manga",
        chapter_data: Optional[list[dict]] = None,
        progress_callback: Optional[callable] = None,
    ) -> ExportTask:
        """Create and start an export task.

        Args:
            chapter_ids: List of chapter IDs to export.
            format: Export format (pdf, png, jpg, webp, zip, cbz, cbr).
            include_original: Include original (untranslated) pages.
            quality: JPEG/WebP quality (1-100).
            page_range: Page range string (e.g., "1-5,8,10-15") or "" for all.
            filename_template: Template for output filename.
            manga_title: Manga title for filename generation.
            chapter_data: Pre-loaded chapter/page data if available.
            progress_callback: Optional async callback (float, str) -> None.

        Returns:
            ExportTask with status and progress.
        """
        task_id = str(uuid.uuid4())

        # Calculate total pages
        total_pages = 0
        if chapter_data:
            for ch in chapter_data:
                pages = ch.get("pages", [])
                if page_range:
                    engine = self._get_format_engine(format)
                    selected = engine.filter_pages(
                        [ExportPage(
                            page_number=p.get("number", i + 1),
                            image_path=p.get("translated_path"),
                        ) for i, p in enumerate(pages)],
                        page_range,
                    )
                    total_pages += len(selected)
                else:
                    total_pages += len(pages)

        task = ExportTask(
            id=task_id,
            format=format,
            chapter_ids=chapter_ids,
            status="processing",
            total_pages=total_pages,
        )
        self.active_tasks[task_id] = task

        try:
            loop = asyncio.get_event_loop()

            def progress_sync(pct: float, msg: str) -> None:
                """Sync progress callback (called from thread pool)."""
                task.progress = pct
                if progress_callback:
                    # Schedule async callback in event loop
                    asyncio.run_coroutine_threadsafe(
                        progress_callback(pct, msg),
                        loop,
                    )

            def _build_export() -> str:
                """Build the export archive synchronously."""
                engine = self._get_format_engine(format)

                # Build ExportChapter objects from chapter_data
                chapters: list[ExportChapter] = []
                if chapter_data:
                    for ch_data in chapter_data:
                        ch = ExportChapter(
                            chapter_id=ch_data.get("id", ""),
                            chapter_number=ch_data.get("number", 1),
                            chapter_title=ch_data.get("title", ""),
                            manga_title=manga_title,
                        )
                        raw_pages = ch_data.get("pages", [])
                        for i, p in enumerate(raw_pages):
                            translated_path = p.get("translated_path")
                            original_path = p.get("original_path")
                            ch.pages.append(ExportPage(
                                page_number=p.get("number", i + 1),
                                image_path=(
                                    translated_path or original_path
                                ),
                                is_translated=p.get("is_translated", False),
                            ))
                        chapters.append(ch)

                if not chapters:
                    raise ValueError("No chapter data provided for export")

                options = ExportOptions(
                    format=format,
                    quality=quality,
                    include_original=include_original,
                    page_range=page_range,
                    filename_template=filename_template,
                    manga_title=manga_title,
                )

                # Generate output path
                safe_title = manga_title.replace(" ", "_").replace("/", "_")
                ext = engine.file_extension
                if format in ("png", "jpg", "jpeg", "webp"):
                    # Image exports go to directories
                    output_path = str(
                        self.export_dir / f"{safe_title}_{task_id[:8]}"
                    )
                else:
                    output_path = str(
                        self.export_dir / f"{safe_title}_{task_id[:8]}{ext}"
                    )

                ep = ExportProgress(on_progress=progress_sync)
                return engine.export(output_path, chapters, options, ep)

            output_path = await loop.run_in_executor(None, _build_export)

            task.status = "completed"
            task.progress = 100.0
            task.output_path = output_path

            out_path = Path(output_path)
            if out_path.exists():
                if out_path.is_file():
                    task.total_size_bytes = out_path.stat().st_size
                else:
                    # Directory export — sum all files
                    total_size = sum(
                        f.stat().st_size for f in out_path.rglob("*")
                        if f.is_file()
                    )
                    task.total_size_bytes = total_size
            task.completed_at = datetime.utcnow()

            logger.info(
                "Export %s completed: %s format, %d pages, %.1f MB",
                task_id, format, task.total_pages,
                (task.total_size_bytes or 0) / (1024 * 1024),
            )

        except Exception as e:
            logger.error("Export %s failed: %s", task_id, e)
            task.status = "failed"
            task.error_message = str(e)[:500]
            task.completed_at = datetime.utcnow()

        return task

    def get_task(self, task_id: str) -> Optional[ExportTask]:
        """Get the status of an export task."""
        return self.active_tasks.get(task_id)

    def get_active_tasks(self) -> list[ExportTask]:
        """Get all active (non-completed) tasks."""
        return [
            t for t in self.active_tasks.values()
            if t.status in ("pending", "processing")
        ]

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a pending/processing task.

        Note: This marks the task as cancelled but doesn't stop
        the running thread — the export will finish but be ignored.

        Args:
            task_id: Task ID to cancel.

        Returns:
            True if cancelled, False if not found.
        """
        task = self.active_tasks.get(task_id)
        if not task:
            return False
        if task.status in ("pending", "processing"):
            task.status = "cancelled"
            task.completed_at = datetime.utcnow()
        return True

    def cleanup_old_exports(self, max_age_hours: int = 24) -> int:
        """Delete export files older than max_age_hours.

        Args:
            max_age_hours: Max age in hours before deletion.

        Returns:
            Number of files/directories deleted.
        """
        import time

        now = time.time()
        deleted = 0

        for f in self.export_dir.iterdir():
            if f.is_file():
                file_age_hours = (now - f.stat().st_mtime) / 3600
                if file_age_hours > max_age_hours:
                    try:
                        f.unlink()
                        deleted += 1
                    except Exception as e:
                        logger.warning("Failed to delete %s: %s", f, e)
            elif f.is_dir():
                # Clean up old directory exports (image formats)
                dir_age_hours = (now - f.stat().st_mtime) / 3600
                if dir_age_hours > max_age_hours:
                    try:
                        shutil.rmtree(f)
                        deleted += 1
                    except Exception as e:
                        logger.warning("Failed to delete dir %s: %s", f, e)

        # Clean up completed tasks
        for task_id, task in list(self.active_tasks.items()):
            if task.status in ("completed", "failed", "cancelled") and task.completed_at:
                age = (datetime.utcnow() - task.completed_at).total_seconds() / 3600
                if age > max_age_hours:
                    del self.active_tasks[task_id]

        return deleted
