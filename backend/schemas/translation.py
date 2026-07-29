"""Pydantic schemas for translation-related data."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class TranslationRequest(BaseModel):
    """Schema for a single translation request."""

    text: str = Field(..., min_length=1, max_length=5000)
    source_language: str = Field(default="ja", max_length=10)
    target_language: str = Field(default="en", max_length=10)
    context: Optional[str] = Field(None, description="Optional context (e.g., genre, character names)")


class TranslationResponse(BaseModel):
    """Schema for a single translation response."""

    translated_text: str
    source_language: str
    target_language: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    processing_time_ms: float = 0.0


class BatchTranslationRequest(BaseModel):
    """Schema for batch translation request."""

    texts: list[str] = Field(..., min_length=1, max_length=100)
    source_language: str = "ja"
    target_language: str = "en"
    context: Optional[str] = None


class TranslationJobCreate(BaseModel):
    """Schema for creating a translation job."""

    chapter_id: str = Field(..., description="Chapter to translate")
    source_language: str = "ja"
    target_language: str = "en"
    options: Optional[dict[str, Any]] = None


class TranslationJobResponse(BaseModel):
    """Schema for translation job response data."""

    id: str
    chapter_id: Optional[str] = None
    status: str
    progress: float
    total_pages: int
    completed_pages: int
    failed_pages: int
    error_message: Optional[str] = None
    source_language: str
    target_language: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TranslationJobStatus(BaseModel):
    """Schema for lightweight job status polling."""

    id: str
    status: str
    progress: float
    completed_pages: int
    total_pages: int
    failed_pages: int
    error_message: Optional[str] = None


class TranslationProgress(BaseModel):
    """WebSocket message for real-time progress updates."""

    job_id: str
    status: str
    progress: float
    current_page: int
    total_pages: int
    message: str = ""
