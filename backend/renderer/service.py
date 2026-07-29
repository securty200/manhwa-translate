"""Enhanced rendering service for manga/manhwa translated text.

Provides professional manga-typography rendering:
- Outline / Shadow / Stroke on all text
- Vertical text support (tategaki — 縦書き)
- Per-bubble-type styling (speech, thought, narration, sfx, sign, title, poster)
- Polygon-based clipping (text never overflows bubbles)
- Auto font size fitting
- Font fallback chains for CJK + Latin
- No white background fill (uses inpainted page as-is)

Typography matches official manga/manhwa releases:
- Bold white outlines for readability
- Subtle drop shadows for depth
- Comic/manga-style fonts
- Centered text with proper padding
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter

from backend.config import settings
from backend.renderer.engines import (
    BubbleStyle,
    FontEngine,
    LayoutEngine,
    TextEngine,
    BubbleStyleEngine,
    get_bubble_style,
)

logger = logging.getLogger(__name__)


@dataclass
class RenderResult:
    """Result of rendering translated text onto a page."""

    image: Image.Image
    processing_time_ms: float = 0.0
    font_used: str = ""
    bubbles_rendered: int = 0
    bubble_details: list[dict] = field(default_factory=list)


class RenderService:
    """Enhanced rendering service for manga/manhwa translated text.

    Draws translated text onto inpainted manga pages with:
    - Auto font sizing (per-bubble-type min/max range)
    - Word/character wrapping with CJK support
    - Per-bubble-type visual styling
    - Outline, shadow, and stroke effects
    - Vertical text (tategaki) for Japanese
    - Polygon-based clipping for tight bubble boundaries
    - No white fill — text drawn directly on inpainted background
    """

    def __init__(self) -> None:
        self.font_engine = FontEngine()
        self.layout_engine = LayoutEngine(self.font_engine)
        self.text_engine = TextEngine()
        self.style_engine = BubbleStyleEngine()

    def render_page(
        self,
        page_image: Image.Image,
        bubbles: list[dict],
        default_font: str | None = None,
    ) -> RenderResult:
        """Render translated text for all bubbles on a page.

        Args:
            page_image: Inpainted PIL Image of the page.
            bubbles: List of dicts with keys:
                - x, y, width, height (required)
                - translated_text (required)
                - polygon (optional, [[x,y],...])
                - bubble_type (optional, default "speech")
                - reading_order (optional)
                - is_vertical (optional, default False)
            default_font: Font name override (applied to all bubbles).

        Returns:
            RenderResult with the final image.
        """
        start_time = time.perf_counter()

        # Work on a copy to preserve the inpainted page
        image = page_image.copy()
        rendered_count = 0
        bubble_details = []

        for bubble in bubbles:
            text = bubble.get("translated_text", "").strip()
            if not text:
                continue

            x = float(bubble.get("x", 0))
            y = float(bubble.get("y", 0))
            w = float(bubble.get("width", 100))
            h = float(bubble.get("height", 50))
            polygon = bubble.get("polygon")
            bubble_type = bubble.get("bubble_type", "speech")
            is_vertical = bubble.get("is_vertical", False)
            reading_order = bubble.get("reading_order", 0)
            font_override = bubble.get("font_override")

            if w <= 0 or h <= 0:
                continue

            # Get style for this bubble type
            style = get_bubble_style(bubble_type)

            # Apply per-bubble overrides
            if font_override:
                style = BubbleStyle(**{**style.__dict__, "font_name": font_override})
            if is_vertical:
                style = BubbleStyle(**{**style.__dict__, "is_vertical": True})

            if default_font:
                style = BubbleStyle(**{**style.__dict__, "font_name": default_font})

            # Reconstruct polygon if provided
            polygon_pts = None
            if polygon and len(polygon) >= 3:
                polygon_pts = [(float(p[0]), float(p[1])) for p in polygon]

            # Clip text to polygon if available
            if polygon_pts:
                image = self._render_bubble_polygon(
                    image, text, style, (x, y, w, h), polygon_pts,
                )
            else:
                image = self._render_bubble_bbox(
                    image, text, style, (x, y, w, h),
                )

            rendered_count += 1
            bubble_details.append({
                "index": len(bubble_details),
                "bubble_type": bubble_type,
                "reading_order": reading_order,
                "bbox": [x, y, w, h],
                "is_vertical": is_vertical,
                "text_snippet": text[:50],
            })

        elapsed = (time.perf_counter() - start_time) * 1000

        logger.info(
            "Rendered %d bubbles in %.0fms",
            rendered_count, elapsed,
        )

        return RenderResult(
            image=image,
            processing_time_ms=elapsed,
            font_used=default_font or "",
            bubbles_rendered=rendered_count,
            bubble_details=bubble_details,
        )

    def _render_bubble_bbox(
        self,
        image: Image.Image,
        text: str,
        style: BubbleStyle,
        bbox: tuple[int, int, int, int],
    ) -> Image.Image:
        """Render text into a bounding-box region.

        Auto-sizes the font and lays out the text, then draws it
        with the specified style effects.

        Args:
            image: PIL Image to draw onto.
            text: Text to render.
            style: BubbleStyle with visual parameters.
            bbox: (x, y, w, h) bounding box.

        Returns:
            Modified image.
        """
        x, y, w, h = [int(v) for v in bbox]
        draw = ImageDraw.Draw(image)
        padding = max(2, int(w * style.padding_ratio))

        # Layout text within the available space
        layout = self.layout_engine.layout_text(
            text=text,
            font_name=style.font_name,
            max_width=w,
            max_height=h,
            draw=draw,
            is_vertical=style.is_vertical,
            font_size_min=style.font_size_min,
            font_size_max=style.font_size_max,
            line_height_ratio=style.line_height_ratio,
            padding=padding,
        )

        if not layout.lines and not layout.vertical_char_positions:
            # Text too small to fit — draw at minimum size
            layout = self.layout_engine.layout_text(
                text=text,
                font_name=style.font_name,
                max_width=w,
                max_height=h,
                draw=draw,
                is_vertical=style.is_vertical,
                font_size_min=8,
                font_size_max=style.font_size_min,
                line_height_ratio=style.line_height_ratio,
                padding=2,
            )

        # Draw the text with effects
        self.text_engine.draw_text(
            image, layout, style, (x, y, w, h), polygon=None,
        )

        return image

    def _render_bubble_polygon(
        self,
        image: Image.Image,
        text: str,
        style: BubbleStyle,
        bbox: tuple[int, int, int, int],
        polygon: list[tuple[float, float]],
    ) -> Image.Image:
        """Render text into a polygon-cropped region.

        Uses the polygon for clipping so text never overflows
        the bubble boundary. This is essential for irregularly
        shaped bubbles (thought bubbles, SFX, etc.).

        Args:
            image: PIL Image to draw onto.
            text: Text to render.
            style: BubbleStyle with visual parameters.
            bbox: (x, y, w, h) bounding box.
            polygon: Polygon vertices for clipping.

        Returns:
            Modified image with text clipped to polygon.
        """
        x, y, w, h = [int(v) for v in bbox]

        # Create a temp image for the text layer
        text_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(text_layer)
        padding = max(2, int(w * style.padding_ratio))

        # Layout text
        layout = self.layout_engine.layout_text(
            text=text,
            font_name=style.font_name,
            max_width=w,
            max_height=h,
            draw=draw,
            is_vertical=style.is_vertical,
            font_size_min=style.font_size_min,
            font_size_max=style.font_size_max,
            line_height_ratio=style.line_height_ratio,
            padding=padding,
        )

        if not layout.lines and not layout.vertical_char_positions:
            layout = self.layout_engine.layout_text(
                text=text,
                font_name=style.font_name,
                max_width=w,
                max_height=h,
                draw=draw,
                is_vertical=style.is_vertical,
                font_size_min=8,
                font_size_max=style.font_size_min,
                line_height_ratio=style.line_height_ratio,
                padding=2,
            )

        # Draw on the text layer
        self.text_engine.draw_text(
            text_layer, layout, style, (x, y, w, h), polygon=polygon,
        )

        # Create polygon clipping mask
        mask = Image.new("L", image.size, 0)
        if polygon and len(polygon) >= 3:
            # Dilate the polygon slightly to prevent clipping at edges
            int_poly = [(int(p[0]), int(p[1])) for p in polygon]
            ImageDraw.Draw(mask).polygon(int_poly, fill=255)
            # Blur the mask for smooth edges
            mask = mask.filter(ImageFilter.GaussianBlur(radius=2))
        else:
            # Fallback to bbox mask
            ImageDraw.Draw(mask).rectangle(
                [x, y, x + w, y + h], fill=255,
            )

        # Composite the text layer onto the image using the mask
        image = image.convert("RGBA")
        image = Image.composite(text_layer, image, mask)
        image = image.convert("RGB")

        return image

    def cleanup(self) -> None:
        """Clear font cache."""
        self.font_engine.clear_cache()
        logger.info("Font cache cleared")
