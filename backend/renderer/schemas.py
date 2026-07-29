"""Pydantic schemas for the rendering module."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class BubbleRenderInfo(BaseModel):
    """A single bubble to render, with position and styling."""

    x: float = Field(..., description="Bubble left edge in pixels")
    y: float = Field(..., description="Bubble top edge in pixels")
    width: float = Field(..., gt=0, description="Bubble width in pixels")
    height: float = Field(..., gt=0, description="Bubble height in pixels")
    translated_text: str = Field(..., min_length=1, description="Text to render")
    polygon: list[list[float]] | None = Field(
        default=None,
        description="Polygon vertices [[x,y],...] for clipping",
    )
    reading_order: int = Field(default=0, ge=0, description="Reading order index")
    bubble_type: str = Field(
        default="speech",
        description="Bubble type: speech, thought, narration, sfx, sign, title, poster",
    )
    rotation: float = Field(
        default=0.0,
        description="Rotation angle in degrees (for rotated text)",
    )
    font_override: Optional[str] = Field(
        default=None,
        description="Override font name for this bubble",
    )
    is_vertical: bool = Field(
        default=False,
        description="Render text vertically (tategaki)",
    )


class RenderPageRequest(BaseModel):
    """Request to render translated text onto a page."""

    image_path: str = Field(..., description="Path to the inpainted page image")
    bubbles: list[BubbleRenderInfo] = Field(
        ..., min_length=1,
        description="Bubbles to render on the page",
    )
    default_bubble_type: str = Field(
        default="speech",
        description="Default bubble type if not specified per-bubble",
    )


class BubbleRenderResult(BaseModel):
    """Result of rendering a single bubble."""

    index: int = Field(..., ge=0)
    bubble_type: str
    text_rendered: str
    font_size_used: int
    lines_rendered: int
    processing_time_ms: float = 0.0
    success: bool = True


class RenderPageResponse(BaseModel):
    """Result of rendering a page."""

    image_path: str = Field(..., description="Path to the rendered page image")
    bubbles_rendered: int = Field(..., ge=0)
    processing_time_ms: float = 0.0
    font_used: str = ""
    bubble_results: list[BubbleRenderResult] = Field(default_factory=list)
    error: Optional[str] = None


class RenderStats(BaseModel):
    """Rendering statistics."""

    total_bubbles: int = 0
    bubbles_with_effects: int = 0
    fonts_used: list[str] = Field(default_factory=list)
    avg_processing_time_ms: float = 0.0
    vertical_bubbles_count: int = 0
    bubble_types_used: list[str] = Field(default_factory=list)
