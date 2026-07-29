"""Pydantic schemas for manga, chapter, page, and bubble data."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class MangaCreate(BaseModel):
    """Schema for creating a new manga entry."""

    title: str = Field(..., min_length=1, max_length=255)
    title_original: Optional[str] = None
    author: Optional[str] = None
    artist: Optional[str] = None
    description: Optional[str] = None
    source_language: str = Field(default="ja", max_length=10)
    target_language: str = Field(default="en", max_length=10)
    tags: Optional[list[str]] = None
    metadata_json: Optional[dict[str, Any]] = None


class MangaUpdate(BaseModel):
    """Schema for updating an existing manga entry."""

    title: Optional[str] = Field(None, min_length=1, max_length=255)
    title_original: Optional[str] = None
    author: Optional[str] = None
    artist: Optional[str] = None
    description: Optional[str] = None
    source_language: Optional[str] = Field(None, max_length=10)
    target_language: Optional[str] = Field(None, max_length=10)
    tags: Optional[list[str]] = None
    metadata_json: Optional[dict[str, Any]] = None


class MangaResponse(BaseModel):
    """Schema for manga response data."""

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
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChapterCreate(BaseModel):
    """Schema for creating a new chapter."""

    chapter_number: float = Field(..., ge=0)
    title: Optional[str] = None
    page_count: int = Field(default=0, ge=0)


class ChapterResponse(BaseModel):
    """Schema for chapter response data."""

    id: str
    manga_id: str
    chapter_number: float
    title: Optional[str] = None
    page_count: int
    is_translated: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PageResponse(BaseModel):
    """Schema for page response data."""

    id: str
    chapter_id: str
    page_number: int
    original_image_path: str
    translated_image_path: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    is_translated: bool
    bubble_count: int = 0

    model_config = {"from_attributes": True}


class BubbleResponse(BaseModel):
    """Schema for bubble response data with polygon support."""

    id: str
    page_id: str
    bubble_type: str
    x: float
    y: float
    width: float
    height: float
    polygon: Optional[list[list[float]]] = Field(
        None, description="Precise polygon vertices [[x,y], ...]"
    )
    confidence: float
    reading_order: Optional[int] = None
    original_text: Optional[str] = None
    translated_text: Optional[str] = None
    is_translated: bool
    rotation: float = Field(0.0, description="Estimated rotation in degrees")
    detector_engine: str = Field("", description="Detection engine used")
    has_precise_mask: bool = Field(False, description="Whether SAM2 precise mask is available")

    model_config = {"from_attributes": True}


class BubbleUpdate(BaseModel):
    """Schema for updating a bubble's translation."""

    translated_text: Optional[str] = None
    is_translated: bool = False
