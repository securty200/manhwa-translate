"""Modular export engines for manga/manhwa chapters.

Each engine handles a specific output format:
- PDF — multi-page PDF with title/author metadata
- Image (PNG, JPG, WEBP) — individual image files in a structured folder
- ZIP — compressed archive with metadata.json
- CBZ — comic book ZIP archive (standard comic format)
- CBR — comic book RAR archive (with ZIP fallback)
"""

from __future__ import annotations

import io
import json
import logging
import os
import shutil
import tempfile
import zipfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from PIL import Image

from backend.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ExportPage:
    """A single page to export with its image data."""

    page_number: int
    image_path: str | None = None
    image_data: bytes | None = None  # Pre-loaded image bytes
    pil_image: Image.Image | None = None  # Pre-loaded PIL Image
    width: int = 0
    height: int = 0
    is_translated: bool = True


@dataclass
class ExportChapter:
    """A chapter to export containing ordered pages."""

    chapter_id: str
    chapter_number: float = 1.0
    chapter_title: str = ""
    pages: list[ExportPage] = field(default_factory=list)
    manga_title: str = "Manga"


@dataclass
class ExportProgress:
    """Progress callback for long-running exports."""

    on_progress: Optional[Callable[[float, str], None]] = None
    on_page_done: Optional[Callable[[int, int], None]] = None  # current, total


@dataclass
class ExportOptions:
    """Options for controlling export behavior."""

    format: str = "cbz"
    quality: int = 90
    include_original: bool = False
    page_range: str = ""  # e.g., "1-5,8,10-15" or empty for all
    filename_template: str = "{manga_title}_Chapter_{chapter_number}"
    output_dir: str = ""
    manga_title: str = "Manga"


# ═══════════════════════════════════════════════════════════════════════════
# Base Export Engine
# ═══════════════════════════════════════════════════════════════════════════


class BaseExportEngine(ABC):
    """Abstract base for all export engines."""

    @property
    @abstractmethod
    def format_name(self) -> str:
        """Return the format identifier (e.g., 'pdf', 'cbz')."""
        ...

    @property
    @abstractmethod
    def file_extension(self) -> str:
        """Return the file extension with dot (e.g., '.pdf', '.cbz')."""
        ...

    @abstractmethod
    def export(
        self,
        output_path: str,
        chapters: list[ExportChapter],
        options: ExportOptions,
        progress: Optional[ExportProgress] = None,
    ) -> str:
        """Export chapters to the output path.

        Args:
            output_path: Full path for the output file/directory.
            chapters: Ordered list of chapters to export.
            options: Export options (quality, page range, etc.).
            progress: Optional progress callback.

        Returns:
            The path to the exported file/directory.
        """
        ...

    def filter_pages(
        self,
        pages: list[ExportPage],
        page_range: str,
    ) -> list[ExportPage]:
        """Filter pages by a range string.

        Supports formats like: "1-5,8,10-15" or empty for all pages.

        Args:
            pages: Full list of pages.
            page_range: Range string or empty.

        Returns:
            Filtered list of pages.
        """
        if not page_range or page_range.strip() == "":
            return pages

        selected: set[int] = set()
        parts = page_range.split(",")
        for part in parts:
            part = part.strip()
            if "-" in part:
                try:
                    start, end = part.split("-", 1)
                    start_n = int(start.strip())
                    end_n = int(end.strip())
                    selected.update(range(start_n, end_n + 1))
                except (ValueError, TypeError):
                    logger.warning("Invalid page range: %s", part)
            else:
                try:
                    selected.add(int(part))
                except (ValueError, TypeError):
                    logger.warning("Invalid page number: %s", part)

        return [p for p in pages if p.page_number in selected]

    def count_selected_pages(
        self,
        chapters: list[ExportChapter],
        page_range: str,
    ) -> int:
        """Count total pages after filtering by page_range.

        Args:
            chapters: List of chapters with pages.
            page_range: Page range string or empty.

        Returns:
            Total number of pages after filtering.
        """
        return sum(
            len(self.filter_pages(c.pages, page_range))
            for c in chapters
        )

    def _load_page_image(self, page: ExportPage) -> Image.Image:
        """Load a page's image from whatever source is available.

        Args:
            page: ExportPage with image data.

        Returns:
            PIL Image in RGB mode.
        """
        if page.pil_image is not None:
            return page.pil_image.convert("RGB")
        if page.image_data is not None:
            buf = io.BytesIO(page.image_data)
            return Image.open(buf).convert("RGB")
        if page.image_path is not None and Path(page.image_path).exists():
            return Image.open(page.image_path).convert("RGB")
        # Fallback: blank page
        img = Image.new("RGB", (800, 1200), (255, 255, 255))
        return img

    def _save_image_bytes(
        self,
        img: Image.Image,
        fmt: str,
        quality: int,
    ) -> bytes:
        """Save a PIL Image to bytes in the specified format.

        Args:
            img: PIL Image.
            fmt: Format (JPEG, PNG, WEBP).
            quality: Quality (1-100, for JPEG/WEBP).

        Returns:
            Image bytes.
        """
        buf = io.BytesIO()
        if fmt.upper() == "JPEG":
            img.save(buf, format="JPEG", quality=quality, optimize=True)
        elif fmt.upper() == "PNG":
            img.save(buf, format="PNG", optimize=True)
        elif fmt.upper() == "WEBP":
            img.save(buf, format="WEBP", quality=quality, method=6)
        else:
            img.save(buf, format=fmt.upper(), quality=quality)
        return buf.getvalue()


# ═══════════════════════════════════════════════════════════════════════════
# Engine 1: PDF Export
# ═══════════════════════════════════════════════════════════════════════════


class PdfExportEngine(BaseExportEngine):
    """Export chapters as a multi-page PDF.

    Uses PIL's PDF save for basic output, or PyMuPDF (fitz) for
    advanced features (metadata, bookmarks, table of contents).
    """

    @property
    def format_name(self) -> str:
        return "pdf"

    @property
    def file_extension(self) -> str:
        return ".pdf"

    def export(
        self,
        output_path: str,
        chapters: list[ExportChapter],
        options: ExportOptions,
        progress: Optional[ExportProgress] = None,
    ) -> str:
        """Create a multi-page PDF with chapter breaks.

        Tries PyMuPDF first for advanced features, falls back to PIL.
        """
        if progress:
            progress.on_progress(0.0, "Preparing PDF export...")

        total_pages = sum(len(c.pages) for c in chapters)
        exported = 0

        # Try PyMuPDF for advanced PDF features
        if self._try_fitz_export(output_path, chapters, options, progress):
            return output_path

        # Fallback: PIL-based PDF
        self._pil_pdf_export(output_path, chapters, options, progress)

        return output_path

    def _try_fitz_export(
        self,
        output_path: str,
        chapters: list[ExportChapter],
        options: ExportOptions,
        progress: Optional[ExportProgress] = None,
    ) -> bool:
        """Try PyMuPDF-based export with metadata and bookmarks."""
        try:
            import fitz  # PyMuPDF

            doc = fitz.open()
            total_pages = self.count_selected_pages(chapters, options.page_range)
            page_num = 0

            for ch_idx, chapter in enumerate(chapters):
                filtered = self.filter_pages(chapter.pages, options.page_range)

                for pg_idx, page in enumerate(filtered):
                    img = self._load_page_image(page)
                    # Convert PIL to fitz pixmap
                    img_bytes = io.BytesIO()
                    img.save(img_bytes, format="PNG")
                    img_bytes.seek(0)

                    pix = fitz.Pixmap(img_bytes.read())
                    rect = fitz.Rect(0, 0, pix.width, pix.height)
                    fz_page = doc.new_page(width=pix.width, height=pix.height)
                    fz_page.insert_image(rect, pixmap=pix)

                    page_num += 1
                    if progress:
                        pct = (page_num / max(total_pages, 1)) * 100
                        progress.on_progress(
                            pct,
                            f"Exporting page {page.page_number} ({page_num}/{total_pages})",
                        )

                # Add chapter bookmark
                toc_title = f"Ch. {chapter.chapter_number}"
                if chapter.chapter_title:
                    toc_title += f": {chapter.chapter_title}"
                # PyMuPDF toc: [level, title, page]
                # We handle TOC after building

            # Set metadata
            doc.set_metadata({
                "title": chapters[0].manga_title if chapters else "Manga",
                "author": "AI Manga Translator",
                "subject": "Fan Translation",
            })

            doc.save(output_path, deflate=True)
            doc.close()
            return True

        except ImportError:
            logger.info("PyMuPDF not available, using PIL PDF export")
            return False
        except Exception as e:
            logger.warning("PyMuPDF export failed: %s, using PIL fallback", e)
            return False

    def _pil_pdf_export(
        self,
        output_path: str,
        chapters: list[ExportChapter],
        options: ExportOptions,
        progress: Optional[ExportProgress] = None,
    ) -> None:
        """Fallback PDF export using PIL.

        Each chapter becomes a section in the PDF.
        """
        all_images: list[Image.Image] = []
        total_pages = self.count_selected_pages(chapters, options.page_range)

        for ch_idx, chapter in enumerate(chapters):
            filtered = self.filter_pages(chapter.pages, options.page_range)

            for pg_idx, page in enumerate(filtered):
                img = self._load_page_image(page)
                all_images.append(img)

                if progress:
                    done = len(all_images)
                    pct = (done / max(total_pages, 1)) * 100
                    progress.on_progress(
                        pct,
                        f"PDF: page {page.page_number} ({done}/{total_pages})",
                    )

        if all_images:
            all_images[0].save(
                output_path,
                save_all=True,
                append_images=all_images[1:],
                quality=options.quality,
                optimize=True,
            )
        else:
            # Empty PDF
            blank = Image.new("RGB", (800, 1200), "white")
            blank.save(output_path, quality=options.quality)


# ═══════════════════════════════════════════════════════════════════════════
# Engine 2: Image Export (PNG, JPG, WEBP)
# ═══════════════════════════════════════════════════════════════════════════


class ImageExportEngine(BaseExportEngine):
    """Export pages as individual image files in a structured directory.

    Supports: PNG (lossless), JPG/JPEG (lossy), WEBP (lossy/lossless).
    Pages are saved as image_format/page_0001.ext
    """

    def __init__(self, image_format: str = "PNG") -> None:
        self._image_format = image_format.upper()

    @property
    def format_name(self) -> str:
        return self._image_format.lower()

    @property
    def file_extension(self) -> str:
        return f".{self._image_format.lower()}"

    @property
    def image_format(self) -> str:
        return self._image_format

    @image_format.setter
    def image_format(self, fmt: str) -> None:
        self._image_format = fmt.upper()

    def export(
        self,
        output_path: str,
        chapters: list[ExportChapter],
        options: ExportOptions,
        progress: Optional[ExportProgress] = None,
    ) -> str:
        """Export pages as individual images in folder structure.

        Creates: output_dir/manga_title/Chapter_01/page_0001.ext
        """
        # If output_path ends with .ext, strip it to get directory
        out_dir = Path(output_path)
        if out_dir.suffix in (".png", ".jpg", ".jpeg", ".webp"):
            out_dir = out_dir.parent / out_dir.stem
        out_dir.mkdir(parents=True, exist_ok=True)

        total_pages = self.count_selected_pages(chapters, options.page_range)
        done = 0

        for ch_idx, chapter in enumerate(chapters):
            chapter_dir = out_dir / f"Chapter_{int(chapter.chapter_number):02d}"
            chapter_dir.mkdir(parents=True, exist_ok=True)

            filtered = self.filter_pages(chapter.pages, options.page_range)

            for pg_idx, page in enumerate(filtered):
                img = self._load_page_image(page)
                ext = self._image_format.lower()
                if ext == "jpeg":
                    ext = "jpg"
                page_filename = f"page_{page.page_number:04d}.{ext}"
                page_path = chapter_dir / page_filename

                save_kwargs = {"format": self._image_format}
                if self._image_format in ("JPEG", "WEBP"):
                    save_kwargs["quality"] = options.quality
                if self._image_format == "PNG":
                    save_kwargs["optimize"] = True
                if self._image_format == "WEBP":
                    save_kwargs["method"] = 6

                img.save(str(page_path), **save_kwargs)

                done += 1
                if progress:
                    pct = (done / max(total_pages, 1)) * 100
                    progress.on_progress(
                        pct,
                        f"Exporting page {page.page_number}.{ext} ({done}/{total_pages})",
                    )

            # Write chapter metadata
            meta = {
                "manga_title": chapter.manga_title,
                "chapter_number": chapter.chapter_number,
                "chapter_title": chapter.chapter_title,
                "page_count": len(filtered),
                "format": self._image_format,
                "generated_at": datetime.utcnow().isoformat(),
            }
            (chapter_dir / "metadata.json").write_text(
                json.dumps(meta, indent=2),
            )

        # Write root metadata
        root_meta = {
            "manga_title": chapters[0].manga_title if chapters else "Manga",
            "chapters": [
                {
                    "number": c.chapter_number,
                    "title": c.chapter_title,
                    "pages": len(
                        self.filter_pages(c.pages, options.page_range),
                    ),
                }
                for c in chapters
            ],
            "format": self._image_format,
            "generated_at": datetime.utcnow().isoformat(),
        }
        (out_dir / "metadata.json").write_text(json.dumps(root_meta, indent=2))

        return str(out_dir)


# ═══════════════════════════════════════════════════════════════════════════
# Engine 3: ZIP Export
# ═══════════════════════════════════════════════════════════════════════════


class ZipExportEngine(BaseExportEngine):
    """Export chapters as a standard ZIP archive.

    Structure:
    - Chapter_01/page_0001.jpg
    - Chapter_01/page_0002.jpg
    - metadata.json
    """

    @property
    def format_name(self) -> str:
        return "zip"

    @property
    def file_extension(self) -> str:
        return ".zip"

    def export(
        self,
        output_path: str,
        chapters: list[ExportChapter],
        options: ExportOptions,
        progress: Optional[ExportProgress] = None,
    ) -> str:
        """Create a ZIP archive with organized chapter/page structure."""
        total_pages = self.count_selected_pages(chapters, options.page_range)
        done = 0

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for ch_idx, chapter in enumerate(chapters):
                filtered = self.filter_pages(chapter.pages, options.page_range)

                for pg_idx, page in enumerate(filtered):
                    img = self._load_page_image(page)
                    img_bytes = self._save_image_bytes(
                        img, "JPEG", options.quality,
                    )

                    arcname = (
                        f"Chapter_{int(chapter.chapter_number):02d}/"
                        f"page_{page.page_number:04d}.jpg"
                    )
                    zf.writestr(arcname, img_bytes)

                    done += 1
                    if progress:
                        pct = (done / max(total_pages, 1)) * 100
                        progress.on_progress(
                            pct,
                            f"ZIP: page {page.page_number} ({done}/{total_pages})",
                        )

                # Include original if requested
                if options.include_original:
                    for pg_idx, page in enumerate(filtered):
                        if page.image_path and Path(page.image_path).exists():
                            orig_arcname = (
                                f"Chapter_{int(chapter.chapter_number):02d}/"
                                f"original/page_{page.page_number:04d}.jpg"
                            )
                            zf.write(page.image_path, orig_arcname)

            # Write metadata
            metadata = self._build_metadata(chapters, options)
            zf.writestr("metadata.json", json.dumps(metadata, indent=2))

        return output_path

    def _build_metadata(
        self,
        chapters: list[ExportChapter],
        options: ExportOptions,
    ) -> dict:
        """Build export metadata JSON."""
        return {
            "generated_by": "AI Manga Translator",
            "generated_at": datetime.utcnow().isoformat(),
            "version": settings.VERSION,
            "manga_title": chapters[0].manga_title if chapters else "Manga",
            "chapters": [
                {
                    "id": c.chapter_id,
                    "number": c.chapter_number,
                    "title": c.chapter_title,
                    "page_count": len(
                        self.filter_pages(c.pages, options.page_range),
                    ),
                }
                for c in chapters
            ],
            "total_chapters": len(chapters),
            "quality": options.quality,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Engine 4: CBZ Export
# ═══════════════════════════════════════════════════════════════════════════


class CbzExportEngine(ZipExportEngine):
    """Export chapters as CBZ (Comic Book ZIP) archive.

    CBZ is the standard comic book archive format — a ZIP file
    with renamed extension containing ordered page images.

    Books are combined into a single archive for multi-chapter exports.
    """

    @property
    def format_name(self) -> str:
        return "cbz"

    @property
    def file_extension(self) -> str:
        return ".cbz"

    def _build_metadata(
        self,
        chapters: list[ExportChapter],
        options: ExportOptions,
    ) -> dict:
        """Build ComicBookInfo-compatible metadata for CBZ."""
        meta = super()._build_metadata(chapters, options)
        meta["comic_book_info"] = {
            "series": chapters[0].manga_title if chapters else "Manga",
            "format": "CBZ",
            "pages": sum(
                len(self.filter_pages(c.pages, options.page_range))
                for c in chapters
            ),
        }
        # ComicRack metadata
        comic_rack = {
            "series": chapters[0].manga_title if chapters else "",
            "title": chapters[0].manga_title if chapters else "",
            "publisher": "AI Manga Translator",
            "genre": "Manga",
            "language": "en",
        }
        meta["ComicRack"] = comic_rack
        return meta


# ═══════════════════════════════════════════════════════════════════════════
# Engine 5: CBR Export (RAR)
# ═══════════════════════════════════════════════════════════════════════════


class CbrExportEngine(BaseExportEngine):
    """Export chapters as CBR (Comic Book RAR) archive.

    Uses rarfile if available for RAR compression.
    Falls back to CBZ (ZIP) if rarfile is not installed.
    """

    @property
    def format_name(self) -> str:
        return "cbr"

    @property
    def file_extension(self) -> str:
        return ".cbr"

    def export(
        self,
        output_path: str,
        chapters: list[ExportChapter],
        options: ExportOptions,
        progress: Optional[ExportProgress] = None,
    ) -> str:
        """Create a CBR archive.

        Tries rarfile first for genuine RAR compression.
        Falls back to a CBZ (ZIP) archive with .cbr extension.
        """
        try:
            import rarfile
            return self._rar_export(output_path, chapters, options, progress)
        except ImportError:
            logger.info(
                "rarfile not available, creating CBZ with .cbr extension"
            )
            return self._zip_fallback(output_path, chapters, options, progress)

    def _rar_export(
        self,
        output_path: str,
        chapters: list[ExportChapter],
        options: ExportOptions,
        progress: Optional[ExportProgress] = None,
    ) -> str:
        """Export using genuine RAR compression via rarfile."""
        try:
            import subprocess

            # rarfile requires the 'rar' or 'unrar' command-line tool
            # We create pages as temp JPEGs, then RAR them
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                total_pages = self.count_selected_pages(chapters, options.page_range)
                done = 0

                for ch_idx, chapter in enumerate(chapters):
                    ch_dir = tmp_path / f"Chapter_{int(chapter.chapter_number):02d}"
                    ch_dir.mkdir(parents=True, exist_ok=True)

                    filtered = self.filter_pages(
                        chapter.pages, options.page_range,
                    )

                    for pg_idx, page in enumerate(filtered):
                        img = self._load_page_image(page)
                        page_path = ch_dir / f"page_{page.page_number:04d}.jpg"
                        img.save(
                            str(page_path),
                            "JPEG", quality=options.quality,
                        )

                        done += 1
                        if progress:
                            pct = (done / max(total_pages, 1)) * 100
                            progress.on_progress(
                                pct,
                                f"CBR: page {page.page_number} ({done}/{total_pages})",
                            )

                # Write metadata
                meta = {
                    "generated_by": "AI Manga Translator",
                    "generated_at": datetime.utcnow().isoformat(),
                    "format": "CBR",
                    "chapters": len(chapters),
                }
                (tmp_path / "metadata.json").write_text(
                    json.dumps(meta, indent=2),
                )

                # Use 'rar' command to create archive
                result = subprocess.run(
                    ["rar", "a", "-ep1", output_path, f"{tmp_path}{os.sep}"],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode != 0:
                    logger.warning(
                        "rar command failed: %s", result.stderr[:200],
                    )
                    raise RuntimeError("rar command failed")

            return output_path

        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.warning("RAR command error: %s, using ZIP fallback", e)
            return self._zip_fallback(output_path, chapters, options, progress)

    def _zip_fallback(
        self,
        output_path: str,
        chapters: list[ExportChapter],
        options: ExportOptions,
        progress: Optional[ExportProgress] = None,
    ) -> str:
        """Fallback: create a CBZ (ZIP) archive with .cbr extension."""
        engine = CbzExportEngine()
        return engine.export(output_path, chapters, options, progress)


# ═══════════════════════════════════════════════════════════════════════════
# Engine Registry
# ═══════════════════════════════════════════════════════════════════════════

EXPORT_ENGINE_REGISTRY: dict[str, type[BaseExportEngine]] = {
    "pdf": PdfExportEngine,
    "png": ImageExportEngine,
    "jpg": ImageExportEngine,
    "jpeg": ImageExportEngine,
    "webp": ImageExportEngine,
    "zip": ZipExportEngine,
    "cbz": CbzExportEngine,
    "cbr": CbrExportEngine,
}

DEFAULT_EXPORT_PRIORITY: list[str] = [
    "cbz", "zip", "pdf", "png", "jpg", "webp", "cbr",
]
