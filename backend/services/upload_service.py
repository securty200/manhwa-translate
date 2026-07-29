"""File upload service for manga page images."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PIL import Image

from backend.config import settings

logger = logging.getLogger(__name__)


@dataclass
class UploadResult:
    """Result of a file upload operation."""

    file_path: str
    file_name: str
    file_size_bytes: int
    width: int = 0
    height: int = 0
    mime_type: str = ""
    page_number: int = 0
    success: bool = True
    error_message: str = ""


ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}
ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/bmp",
    "image/tiff",
}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
MAX_IMAGE_DIMENSION = 10000  # px


class UploadService:
    """Service for handling manga page image uploads."""

    def __init__(self) -> None:
        self.upload_dir = settings.CACHE_DIR / "uploads"
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def _validate_file(self, filename: str, content: bytes) -> tuple[bool, str]:
        """Validate uploaded file type and size."""
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            return False, f"Unsupported file extension: {ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"

        if len(content) > MAX_FILE_SIZE:
            size_mb = len(content) / (1024 * 1024)
            return False, f"File too large: {size_mb:.1f} MB. Max: {MAX_FILE_SIZE / (1024 * 1024):.0f} MB"

        return True, ""

    def _detect_mime(self, ext: str) -> str:
        """Detect MIME type from file extension."""
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
            ".tiff": "image/tiff",
            ".tif": "image/tiff",
        }
        return mime_map.get(ext.lower(), "application/octet-stream")

    async def upload_page(
        self,
        content: bytes,
        filename: str,
        manga_id: str,
        chapter_id: str,
        page_number: int,
    ) -> UploadResult:
        """Upload and validate a single manga page image.

        Args:
            content: Raw file bytes.
            filename: Original filename.
            manga_id: ID of the manga this page belongs to.
            chapter_id: ID of the chapter this page belongs to.
            page_number: Page number within the chapter.

        Returns:
            UploadResult with file path and metadata.
        """
        # Validate
        is_valid, error_msg = self._validate_file(filename, content)
        if not is_valid:
            return UploadResult(
                file_path="", file_name=filename, file_size_bytes=len(content),
                success=False, error_message=error_msg,
            )

        # Create directory structure
        ext = Path(filename).suffix.lower()
        mime = self._detect_mime(ext)
        dest_dir = self.upload_dir / manga_id / chapter_id
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique filename
        unique_name = f"page_{page_number:04d}_{uuid.uuid4().hex[:8]}{ext}"
        dest_path = dest_dir / unique_name

        # Write file asynchronously
        loop = asyncio.get_event_loop()

        def _write() -> tuple[int, int]:
            """Write file and return image dimensions."""
            dest_path.write_bytes(content)
            try:
                with Image.open(dest_path) as img:
                    return img.width, img.height
            except Exception:
                return 0, 0

        width, height = await loop.run_in_executor(None, _write)

        if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
            dest_path.unlink(missing_ok=True)
            return UploadResult(
                file_path="", file_name=filename, file_size_bytes=len(content),
                success=False,
                error_message=f"Image dimensions {width}x{height} exceed max {MAX_IMAGE_DIMENSION}px",
            )

        logger.info(
            "Uploaded page %d: %s (%dx%d, %s)",
            page_number, unique_name, width, height,
            self._format_size(len(content)),
        )

        return UploadResult(
            file_path=str(dest_path),
            file_name=unique_name,
            file_size_bytes=len(content),
            width=width,
            height=height,
            mime_type=mime,
            page_number=page_number,
        )

    async def upload_cover(
        self,
        content: bytes,
        filename: str,
        manga_id: str,
    ) -> UploadResult:
        """Upload a cover image for a manga.

        Cover images are resized to a max dimension for consistency.
        """
        result = await self.upload_page(content, filename, manga_id, "cover", 0)
        if not result.success:
            return result

        # Resize cover to standard dimensions
        loop = asyncio.get_event_loop()

        def _resize() -> str:
            """Resize cover to max 400x600 while maintaining aspect ratio."""
            with Image.open(result.file_path) as img:
                img.thumbnail((400, 600), Image.LANCZOS)
                output_path = str(Path(result.file_path).with_suffix(".jpg"))
                img.convert("RGB").save(output_path, "JPEG", quality=85)
                # Remove original if format changed
                if output_path != result.file_path:
                    Path(result.file_path).unlink()
                return output_path

        output_path = await loop.run_in_executor(None, _resize)
        result.file_path = output_path

        return result

    async def upload_batch(
        self,
        files: list[tuple[bytes, str]],  # (content, filename)
        manga_id: str,
        chapter_id: str,
        start_page: int = 1,
    ) -> list[UploadResult]:
        """Upload multiple page images in batch.

        Args:
            files: List of (content_bytes, filename) tuples.
            manga_id: Manga ID.
            chapter_id: Chapter ID.
            start_page: Starting page number.

        Returns:
            List of UploadResult objects, sorted by natural page order.
        """
        tasks = []
        for i, (content, filename) in enumerate(files):
            task = self.upload_page(content, filename, manga_id, chapter_id, start_page + i)
            tasks.append(task)

        results = await asyncio.gather(*tasks)
        return sorted(results, key=lambda r: r.page_number)

    def delete_page_file(self, file_path: str) -> bool:
        """Delete an uploaded page file."""
        try:
            path = Path(file_path)
            if path.exists():
                path.unlink()
                logger.info("Deleted file: %s", file_path)
                return True
            return False
        except Exception as e:
            logger.error("Failed to delete file %s: %s", file_path, e)
            return False

    def delete_chapter_files(self, manga_id: str, chapter_id: str) -> bool:
        """Delete all uploaded files for a chapter."""
        chapter_dir = self.upload_dir / manga_id / chapter_id
        try:
            if chapter_dir.exists():
                import shutil
                shutil.rmtree(chapter_dir)
                logger.info("Deleted chapter directory: %s", chapter_dir)
                return True
            return False
        except Exception as e:
            logger.error("Failed to delete chapter %s: %s", chapter_id, e)
            return False

    def delete_manga_files(self, manga_id: str) -> bool:
        """Delete all uploaded files for a manga."""
        manga_dir = self.upload_dir / manga_id
        try:
            if manga_dir.exists():
                import shutil
                shutil.rmtree(manga_dir)
                logger.info("Deleted manga directory: %s", manga_dir)
                return True
            return False
        except Exception as e:
            logger.error("Failed to delete manga %s: %s", manga_id, e)
            return False

    def get_storage_size(self, manga_id: Optional[str] = None) -> int:
        """Get total storage size for a manga or all uploads."""
        target_dir = self.upload_dir / manga_id if manga_id else self.upload_dir
        if not target_dir.exists():
            return 0

        total = 0
        for f in target_dir.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
        return total

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format file size in human-readable format."""
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"
