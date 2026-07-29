"""Pydantic schemas for import operations."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ImportRequest(BaseModel):
    """Schema for an import request."""

    project_title: str = Field(default="Imported Manga", max_length=255)
    chapter_number: float = Field(default=1.0, ge=0)
    source_language: str = Field(default="ja", max_length=10)
    target_language: str = Field(default="en", max_length=10)
    author: Optional[str] = Field(None, max_length=255)
    generate_thumbnails: bool = True
    auto_create_project: bool = True


class ImportPageInfo(BaseModel):
    """Information about a single imported page."""

    page_number: int
    filename: str
    width: int = 0
    height: int = 0
    file_size_bytes: int = 0
    original_format: str = ""
    success: bool = True
    error_message: str = ""
    thumbnail_path: Optional[str] = None


class ImportResponse(BaseModel):
    """Response after a successful import."""

    project_id: str
    project_title: str
    chapter_id: str
    chapter_number: float
    total_pages: int
    successful_pages: int
    failed_pages: int
    import_format: str
    source_filename: str
    total_size_bytes: int
    duration_ms: float
    pages: list[ImportPageInfo]
    errors: list[str]
    thumbnail_paths: list[str]
    metadata: dict[str, Any] = {}
    created_at: datetime


class ImportFolderRequest(BaseModel):
    """Schema for importing a folder of images."""

    folder_path: str = Field(..., description="Absolute path to folder on server")
    project_title: str = Field(default="Imported Manga", max_length=255)
    chapter_number: float = Field(default=1.0, ge=0)
    source_language: str = Field(default="ja", max_length=10)
    target_language: str = Field(default="en", max_length=10)
    generate_thumbnails: bool = True
    recursive: bool = Field(default=False, description="Scan subdirectories")
