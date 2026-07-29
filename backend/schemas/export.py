"""Pydantic schemas for export operations.

Supports 7 formats: PDF, PNG, JPG, WEBP, ZIP, CBZ, CBR.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ExportRequest(BaseModel):
    """Schema for requesting an export."""

    chapter_ids: list[str] = Field(
        ..., min_length=1,
        description="Chapter IDs to export",
    )
    format: str = Field(
        default="cbz",
        description="Export format: pdf, png, jpg, jpeg, webp, zip, cbz, cbr",
    )
    include_original: bool = Field(
        default=False,
        description="Include original (untranslated) pages",
    )
    quality: int = Field(
        default=90, ge=10, le=100,
        description="JPEG/WebP quality (10-100)",
    )
    page_range: str = Field(
        default="",
        description="Page range: '1-5,8,10-15' or '' for all pages",
    )
    filename_template: str = Field(
        default="{manga_title}_Chapter_{chapter_number}",
        description="Filename template: {manga_title}, {chapter_number}, {chapter_title}",
    )

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        """Validate that the format is supported."""
        supported = {"pdf", "png", "jpg", "jpeg", "webp", "zip", "cbz", "cbr"}
        fmt = v.lower().strip()
        if fmt not in supported:
            raise ValueError(
                f"Unsupported format: '{v}'. "
                f"Supported: {', '.join(sorted(supported))}"
            )
        return fmt

    @field_validator("page_range")
    @classmethod
    def validate_page_range(cls, v: str) -> str:
        """Validate page range format."""
        if not v or v.strip() == "":
            return ""
        parts = v.split(",")
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                bounds = part.split("-", 1)
                if len(bounds) != 2:
                    raise ValueError(f"Invalid range: '{part}'")
                try:
                    start, end = int(bounds[0].strip()), int(bounds[1].strip())
                    if start < 1 or end < start:
                        raise ValueError(
                            f"Invalid range: '{part}' — must start>=1, end>=start"
                        )
                except ValueError:
                    raise ValueError(f"Invalid range: '{part}'")
            else:
                try:
                    n = int(part)
                    if n < 1:
                        raise ValueError(f"Page number must be >= 1: '{part}'")
                except ValueError:
                    raise ValueError(f"Invalid page number: '{part}'")
        return v


class ExportTaskResponse(BaseModel):
    """Response for export task creation."""

    task_id: str
    status: str = "pending"
    message: str = "Export task created"
    format: str = "cbz"
    estimated_chapters: int = 0
    estimated_pages: int = 0
    estimated_size_mb: Optional[float] = None


class ExportTask(BaseModel):
    """Schema for an export task (kept for backward compatibility)."""

    id: str
    status: str = "pending"
    progress: float = 0.0
    format: str = "cbz"
    chapter_ids: list[str] = Field(default_factory=list)
    output_path: Optional[str] = None
    total_size_bytes: Optional[int] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class ExportTaskStatus(BaseModel):
    """Detailed status of an export task."""

    id: str
    status: str
    progress: float = 0.0
    format: str
    total_pages: int = 0
    completed_pages: int = 0
    output_path: Optional[str] = None
    total_size_bytes: Optional[int] = None
    total_size_mb: Optional[float] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class ExportFormatInfo(BaseModel):
    """Information about a supported export format."""

    format: str
    extension: str
    description: str
    supports_quality: bool = False
    supports_page_range: bool = True
    is_archive: bool = False
    is_image: bool = False
    mime_type: str = "application/octet-stream"


# Supported formats with metadata
SUPPORTED_FORMATS: dict[str, ExportFormatInfo] = {
    "pdf": ExportFormatInfo(
        format="pdf",
        extension=".pdf",
        description="Multi-page PDF with metadata",
        supports_quality=True,
        is_archive=False,
        is_image=False,
        mime_type="application/pdf",
    ),
    "png": ExportFormatInfo(
        format="png",
        extension=".png",
        description="Individual PNG images in folder structure",
        supports_quality=False,
        is_archive=False,
        is_image=True,
        mime_type="image/png",
    ),
    "jpg": ExportFormatInfo(
        format="jpg",
        extension=".jpg",
        description="Individual JPEG images in folder structure",
        supports_quality=True,
        is_archive=False,
        is_image=True,
        mime_type="image/jpeg",
    ),
    "jpeg": ExportFormatInfo(
        format="jpeg",
        extension=".jpeg",
        description="Individual JPEG images in folder structure",
        supports_quality=True,
        is_archive=False,
        is_image=True,
        mime_type="image/jpeg",
    ),
    "webp": ExportFormatInfo(
        format="webp",
        extension=".webp",
        description="Individual WebP images in folder structure",
        supports_quality=True,
        is_archive=False,
        is_image=True,
        mime_type="image/webp",
    ),
    "zip": ExportFormatInfo(
        format="zip",
        extension=".zip",
        description="Compressed ZIP archive with organized structure",
        supports_quality=True,
        is_archive=True,
        is_image=False,
        mime_type="application/zip",
    ),
    "cbz": ExportFormatInfo(
        format="cbz",
        extension=".cbz",
        description="Comic Book ZIP archive (standard comic format)",
        supports_quality=True,
        is_archive=True,
        is_image=False,
        mime_type="application/vnd.comicbook+zip",
    ),
    "cbr": ExportFormatInfo(
        format="cbr",
        extension=".cbr",
        description="Comic Book RAR archive (with ZIP fallback)",
        supports_quality=True,
        is_archive=True,
        is_image=False,
        mime_type="application/vnd.comicbook-rar",
    ),
}
