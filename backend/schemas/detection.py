"""Pydantic schemas for speech bubble detection with precise polygon support."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class PolygonPoint(BaseModel):
    """A single vertex in a polygon."""

    x: float = Field(..., description="X coordinate in pixels")
    y: float = Field(..., description="Y coordinate in pixels")


class DetectedRegionSchema(BaseModel):
    """A detected region/bubble with precise polygon outline."""

    polygon: list[PolygonPoint] = Field(
        ..., description="Precise polygon vertices defining the region boundary"
    )
    bbox: tuple[float, float, float, float] = Field(
        ..., description="Bounding box (x, y, width, height) from polygon"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Detection confidence score"
    )
    bubble_type: str = Field(
        ..., description="Type: speech, thought, narration, sfx, sign, title, poster"
    )
    engine_name: str = Field(..., description="Detector engine used")
    area: float = Field(0.0, description="Polygon area in pixels")
    text_prompt: str = Field("", description="Text prompt used for detection")
    reading_order: Optional[int] = Field(None, description="Manga reading order index")
    processing_time_ms: float = Field(0.0, description="Processing time in milliseconds")
    has_mask: bool = Field(
        False, description="Whether a precise segmentation mask is available"
    )


class DetectionPageResultSchema(BaseModel):
    """Result of detecting all regions on a single manga page."""

    regions: list[DetectedRegionSchema] = Field(
        default_factory=list, description="All detected regions"
    )
    page_width: int = Field(0, description="Page image width in pixels")
    page_height: int = Field(0, description="Page image height in pixels")
    total_processing_time_ms: float = Field(
        0.0, description="Total detection time in milliseconds"
    )
    engines_used: list[str] = Field(
        default_factory=list, description="Engines that contributed to detection"
    )
    region_count: int = Field(0, description="Total number of regions detected")


class DetectionRequest(BaseModel):
    """Request to run bubble detection on a page."""

    page_id: Optional[str] = Field(None, description="Page ID to detect (from DB)")
    image_path: Optional[str] = Field(None, description="Path to image file")
    target_types: Optional[list[str]] = Field(
        None, description="Filter to specific bubble types"
    )
    engine_priority: Optional[list[str]] = Field(
        None, description="Engine priority order"
    )
    merge_overlapping: bool = Field(
        True, description="Merge heavily overlapping regions"
    )


class DetectionResponse(BaseModel):
    """Response from a detection request."""

    success: bool = Field(..., description="Whether detection succeeded")
    result: Optional[DetectionPageResultSchema] = Field(
        None, description="Detection results"
    )
    error: Optional[str] = Field(None, description="Error message if failed")
    processing_time_ms: float = Field(0.0, description="Total processing time")


class BubbleDetectionLink(BaseModel):
    """Link between a detected bubble and its OCR/translation data."""

    bubble_id: str = Field(..., description="Bubble record ID in database")
    polygon: list[PolygonPoint] = Field(
        ..., description="Precise polygon of the bubble"
    )
    bubble_type: str = Field(..., description="Type of bubble")
    reading_order: Optional[int] = Field(None, description="Reading order index")
    original_text: Optional[str] = Field(None, description="OCR-extracted original text")
    translated_text: Optional[str] = Field(
        None, description="Translated text (if available)"
    )
    ocr_confidence: float = Field(0.0, description="OCR confidence score")
    ocr_engine: str = Field("", description="OCR engine used")
    detection_engine: str = Field("", description="Detection engine used")
    has_precise_mask: bool = Field(
        False, description="Whether SAM2 precise mask is available"
    )


class DetectionStats(BaseModel):
    """Statistics about a detection run."""

    total_regions: int = Field(0, description="Total regions detected")
    by_type: dict[str, int] = Field(
        default_factory=dict, description="Count by bubble type"
    )
    by_engine: dict[str, int] = Field(
        default_factory=dict, description="Count by engine"
    )
    avg_confidence: float = Field(0.0, description="Average confidence")
    total_time_ms: float = Field(0.0, description="Total detection time")
    page_width: int = Field(0, description="Page width")
    page_height: int = Field(0, description="Page height")
