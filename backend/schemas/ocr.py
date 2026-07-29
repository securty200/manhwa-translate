"""Pydantic schemas for OCR results with rich metadata."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class OCRTextRegion(BaseModel):
    """A single detected text region with full metadata."""

    text: str = ""
    confidence: float = 0.0
    detected_language: str = "unknown"
    bbox: tuple[float, float, float, float] | None = None  # x, y, w, h
    rotation: float = 0.0
    engine_name: str = ""
    processing_time_ms: float = 0.0
    page_number: int = 0
    region_index: int = 0


class OCRPageResult(BaseModel):
    """OCR results for an entire page."""

    page_id: str = ""
    page_number: int = 0
    regions: list[OCRTextRegion] = []
    best_engine: str = ""
    total_regions: int = 0
    average_confidence: float = 0.0
    processing_time_ms: float = 0.0
    engines_used: list[str] = []


class OCREngineInfo(BaseModel):
    """Information about an available OCR engine."""

    name: str
    available: bool = False
    languages: list[str] = []
    version: str = ""
    initialized: bool = False


class OCRBatchResult(BaseModel):
    """Result of OCR on multiple pages."""

    page_results: list[OCRPageResult] = []
    total_pages: int = 0
    total_regions: int = 0
    total_time_ms: float = 0.0
    engines_used: list[str] = []


class OCRRequest(BaseModel):
    """Request to run OCR on one or more pages."""

    page_ids: list[str] = Field(..., min_length=1)
    engine_priority: list[str] = Field(
        default=["paddleocr", "easyocr", "tesseract"],
        description="Engine priority order for auto-best-result",
    )
    languages: list[str] = Field(
        default=["ja", "en"],
        description="Languages to detect (ISO codes)",
    )
    auto_choose_best: bool = Field(
        default=True,
        description="Automatically choose best result across engines",
    )


class OCRResponse(BaseModel):
    """Response from OCR processing."""

    page_id: str
    page_number: int
    regions: list[OCRTextRegion] = []
    best_engine: str = ""
    total_regions: int = 0
    average_confidence: float = 0.0
    processing_time_ms: float = 0.0
    engines_available: list[str] = []
    engines_used: list[str] = []
    stored_in_db: bool = False
