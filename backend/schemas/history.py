"""Pydantic schemas for translation history."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class HistoryEntry(BaseModel):
    """A single history entry for translation activity."""

    id: str
    job_id: str
    manga_title: str
    chapter_number: float
    chapter_title: Optional[str] = None
    action: str  # created, started, completed, failed, cancelled, resumed, stopped
    status: str
    pages_total: int = 0
    pages_completed: int = 0
    pages_failed: int = 0
    processing_time_ms: Optional[float] = None
    error_message: Optional[str] = None
    source_language: str
    target_language: str
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class HistoryFilter(BaseModel):
    """Filter parameters for querying history."""

    manga_id: Optional[str] = None
    status: Optional[str] = None
    action: Optional[str] = None
    source_language: Optional[str] = None
    target_language: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    search: Optional[str] = Field(None, max_length=100, description="Search in manga title or chapter title")
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class HistoryPage(BaseModel):
    """Paginated history response."""

    items: list[HistoryEntry]
    total: int
    limit: int
    offset: int
    has_more: bool


class ActivitySummary(BaseModel):
    """Summary of translation activity over a period."""

    total_jobs: int = 0
    completed_jobs: int = 0
    failed_jobs: int = 0
    total_pages_translated: int = 0
    total_time_ms: float = 0.0
    average_time_per_page_ms: float = 0.0
    pages_by_language: dict[str, int] = {}
    recent_activity: list[HistoryEntry] = []
