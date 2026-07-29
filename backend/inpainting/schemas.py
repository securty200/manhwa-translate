"""Pydantic schemas for the inpainting module."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class InpaintRegionSchema(BaseModel):
    """A region to inpaint, with optional polygon and mask reference."""

    bbox: tuple[int, int, int, int] = Field(
        ..., description="Bounding box (x, y, w, h) of the region",
    )
    polygon: list[list[float]] = Field(
        default_factory=list,
        description="Polygon vertices as [[x, y], ...] or empty for bbox-only",
    )
    complex_background: bool = Field(
        default=False,
        description="Whether this region has complex background (screentones, gradients)",
    )


class InpaintRequest(BaseModel):
    """Request to inpaint one or more regions on an image."""

    image_path: str = Field(..., description="Path to the image file to inpaint")
    regions: list[InpaintRegionSchema] = Field(
        ..., min_length=1,
        description="Regions to inpaint on the image",
    )
    engine_priority: list[str] = Field(
        default_factory=lambda: [
            "lama", "content_aware_fill", "bubble_reconstruction",
            "opencv", "matting_refinement",
        ],
        description="Engine priority order for inpainting",
    )
    refinement_passes: int = Field(
        default=2, ge=1, le=5,
        description="Number of progressive refinement passes",
    )


class InpaintRegionResult(BaseModel):
    """Result of inpainting a single region."""

    bbox: tuple[int, int, int, int]
    engine_used: str
    successful: bool = True
    processing_time_ms: float = 0.0
    complex_background: bool = False


class InpaintResponse(BaseModel):
    """Result of an inpainting operation."""

    image_path: str = Field(..., description="Path to the inpainted image")
    regions_inpainted: int = Field(..., ge=0)
    processing_time_ms: float = 0.0
    engine_used: str = ""
    refinement_passes: int = 1
    region_results: list[InpaintRegionResult] = Field(default_factory=list)
    error: Optional[str] = None


class InpaintStats(BaseModel):
    """Statistics about inpainting performance."""

    total_regions: int = 0
    regions_complex: int = 0
    regions_simple: int = 0
    avg_processing_time_ms: float = 0.0
    engines_used: list[str] = Field(default_factory=list)
    refinement_passes_used: int = 1
    mask_coverage_ratio: float = 0.0
