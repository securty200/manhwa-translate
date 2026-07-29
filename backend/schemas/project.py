"""Pydantic schemas for project management."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    """Schema for creating a new translation project."""

    title: str = Field(..., min_length=1, max_length=255)
    title_original: Optional[str] = None
    author: Optional[str] = None
    artist: Optional[str] = None
    description: Optional[str] = None
    source_language: str = Field(default="ja", max_length=10)
    target_language: str = Field(default="en", max_length=10)
    tags: Optional[list[str]] = None


class ProjectResponse(BaseModel):
    """Schema for project response data."""

    id: str
    title: str
    title_original: Optional[str] = None
    author: Optional[str] = None
    artist: Optional[str] = None
    description: Optional[str] = None
    cover_image_path: Optional[str] = None
    source_language: str
    target_language: str
    tags: Optional[list] = None
    chapter_count: int = 0
    total_pages: int = 0
    translated_pages: int = 0
    translation_progress: float = 0.0
    last_translated_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectUpdate(BaseModel):
    """Schema for updating a project."""

    title: Optional[str] = Field(None, min_length=1, max_length=255)
    title_original: Optional[str] = None
    author: Optional[str] = None
    artist: Optional[str] = None
    description: Optional[str] = None
    source_language: Optional[str] = Field(None, max_length=10)
    target_language: Optional[str] = Field(None, max_length=10)
    tags: Optional[list[str]] = None


class ProjectStats(BaseModel):
    """Aggregated statistics for a project."""

    project_id: str
    title: str
    total_chapters: int = 0
    total_pages: int = 0
    translated_chapters: int = 0
    translated_pages: int = 0
    translation_progress: float = 0.0
    total_bubbles: int = 0
    total_jobs: int = 0
    completed_jobs: int = 0
    failed_jobs: int = 0
    total_processing_time_ms: float = 0.0
    storage_size_bytes: int = 0


class ProjectSummary(BaseModel):
    """Lightweight project summary for list views."""

    id: str
    title: str
    title_original: Optional[str] = None
    author: Optional[str] = None
    cover_image_path: Optional[str] = None
    source_language: str
    target_language: str
    chapter_count: int
    total_pages: int
    translated_pages: int
    translation_progress: float
    last_activity: datetime
    created_at: datetime

    model_config = {"from_attributes": True}
