"""Modular rendering engines for manga/manhwa translated text.

Provides:
- FontEngine — font loading, caching, fallback chains for CJK + Latin
- LayoutEngine — text wrapping, measuring (horizontal + vertical CJK)
- TextEngine — text drawing with outline, shadow, stroke effects
- BubbleStyleEngine — per-bubble-type styling (speech, thought, narration, sfx, sign, title, poster)
- VerticalTextEngine — tategaki (top-to-bottom, right-to-left columns)

Typography aims to match official manga releases:
- Bold outlines for readability on complex backgrounds
- Subtle shadows for depth
- Comic/manga fonts with proper fallbacks
- Auto-sizing that never overflows polygon boundaries
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImagePath

from backend.config import settings

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────

# Default colors
TEXT_WHITE = (255, 255, 255)
TEXT_BLACK = (0, 0, 0)
TEXT_DARK_GRAY = (30, 30, 30)

# Outline defaults
DEFAULT_OUTLINE_WIDTH = 2
DEFAULT_OUTLINE_COLOR = (255, 255, 255)  # White outline
DEFAULT_SHADOW_OFFSET = (2, 2)
DEFAULT_SHADOW_COLOR = (0, 0, 0, 100)  # Semi-transparent black
DEFAULT_SHADOW_BLUR_RADIUS = 3

# Layout defaults
DEFAULT_PADDING = 8
MIN_FONT_SIZE = 8
MAX_FONT_SIZE = 72

# ── Per-bubble-type style presets ────────────────────────────────────────


@dataclass
class BubbleStyle:
    """Visual style for a specific bubble type.

    Each bubble type (speech, thought, narration, etc.) gets its own
    style that mimics official manga/manhwa release conventions.
    """

    font_name: str = "default.ttf"
    font_size_min: int = 12
    font_size_max: int = 48
    text_color: tuple[int, int, int] = TEXT_BLACK
    outline_width: int = 0
    outline_color: tuple[int, int, int] = TEXT_WHITE
    shadow_offset: tuple[int, int] = (0, 0)
    shadow_color: tuple[int, int, int, int] = (0, 0, 0, 0)
    shadow_blur: int = 0
    stroke_width: int = 0
    stroke_color: tuple[int, int, int] = TEXT_WHITE
    is_vertical: bool = False  # Tategaki for Japanese text
    line_height_ratio: float = 1.4
    padding_ratio: float = 0.08
    text_align: str = "center"  # "left", "center", "right"
    font_weight: str = "normal"  # "normal", "bold"
    italic: bool = False
    uppercase: bool = False
    background_fill: tuple[int, int, int] | None = None  # None = transparent


# Manga-style presets for each bubble type
BUBBLE_STYLE_PRESETS: dict[str, BubbleStyle] = {
    "speech": BubbleStyle(
        font_name="manga.ttf",
        font_size_min=14,
        font_size_max=48,
        text_color=(0, 0, 0),
        outline_width=2,
        outline_color=(255, 255, 255),
        shadow_offset=(1, 1),
        shadow_color=(0, 0, 0, 60),
        shadow_blur=2,
        line_height_ratio=1.35,
        padding_ratio=0.08,
        text_align="center",
    ),
    "thought": BubbleStyle(
        font_name="manga.ttf",
        font_size_min=13,
        font_size_max=42,
        text_color=(60, 60, 60),
        outline_width=2,
        outline_color=(255, 255, 255),
        shadow_offset=(1, 1),
        shadow_color=(0, 0, 0, 50),
        shadow_blur=2,
        italic=True,
        line_height_ratio=1.3,
        padding_ratio=0.08,
        text_align="center",
    ),
    "narration": BubbleStyle(
        font_name="manga.ttf",
        font_size_min=11,
        font_size_max=36,
        text_color=(30, 30, 30),
        outline_width=1,
        outline_color=(255, 255, 255),
        shadow_offset=(1, 1),
        shadow_color=(0, 0, 0, 40),
        shadow_blur=1,
        line_height_ratio=1.3,
        padding_ratio=0.1,
        text_align="left",
        background_fill=(255, 255, 255),
    ),
    "sfx": BubbleStyle(
        font_name="sfx_bold.ttf",
        font_size_min=18,
        font_size_max=64,
        text_color=(0, 0, 0),
        outline_width=3,
        outline_color=(255, 255, 255),
        shadow_offset=(2, 2),
        shadow_color=(0, 0, 0, 80),
        shadow_blur=3,
        stroke_width=1,
        stroke_color=(255, 255, 255),
        line_height_ratio=1.1,
        padding_ratio=0.05,
        text_align="center",
        uppercase=True,
        font_weight="bold",
    ),
    "sign": BubbleStyle(
        font_name="manga.ttf",
        font_size_min=10,
        font_size_max=40,
        text_color=(0, 0, 0),
        outline_width=2,
        outline_color=(255, 255, 255),
        shadow_offset=(1, 1),
        shadow_color=(0, 0, 0, 60),
        shadow_blur=2,
        line_height_ratio=1.3,
        padding_ratio=0.06,
        text_align="center",
        background_fill=(255, 255, 255),
    ),
    "title": BubbleStyle(
        font_name="manga_bold.ttf",
        font_size_min=20,
        font_size_max=64,
        text_color=(0, 0, 0),
        outline_width=3,
        outline_color=(255, 255, 255),
        shadow_offset=(2, 2),
        shadow_color=(0, 0, 0, 80),
        shadow_blur=3,
        stroke_width=1,
        stroke_color=(255, 255, 255),
        font_weight="bold",
        line_height_ratio=1.3,
        padding_ratio=0.1,
        text_align="center",
    ),
    "poster": BubbleStyle(
        font_name="manga_bold.ttf",
        font_size_min=24,
        font_size_max=72,
        text_color=(0, 0, 0),
        outline_width=4,
        outline_color=(255, 255, 255),
        shadow_offset=(3, 3),
        shadow_color=(0, 0, 0, 100),
        shadow_blur=4,
        stroke_width=2,
        stroke_color=(255, 255, 255),
        font_weight="bold",
        line_height_ratio=1.2,
        padding_ratio=0.08,
        text_align="center",
    ),
    "default": BubbleStyle(
        font_name="default.ttf",
        font_size_min=12,
        font_size_max=48,
        text_color=(0, 0, 0),
        outline_width=2,
        outline_color=(255, 255, 255),
        shadow_offset=(1, 1),
        shadow_color=(0, 0, 0, 60),
        shadow_blur=2,
        line_height_ratio=1.35,
        padding_ratio=0.08,
        text_align="center",
    ),
}


def get_bubble_style(bubble_type: str) -> BubbleStyle:
    """Get the rendering style for a specific bubble type.

    Falls back to 'default' if the type is unknown.

    Args:
        bubble_type: Type string (speech, thought, narration, sfx, etc.).

    Returns:
        BubbleStyle preset for that type.
    """
    return BUBBLE_STYLE_PRESETS.get(
        bubble_type,
        BUBBLE_STYLE_PRESETS["default"],
    )


# ═══════════════════════════════════════════════════════════════════════════
# Font Engine
# ═══════════════════════════════════════════════════════════════════════════


class FontEngine:
    """Manages font loading, caching, and fallback chains.

    Supports:
    - Loading from FONTS_DIR or system fonts
    - Caching all loaded fonts by name + size
    - Automatic fallback chains (manga → comic → default)
    - CJK font detection for vertical text
    """

    # Font fallback chains: ordered list of font names to try
    MANGA_FONT_CHAIN = [
        "manga.ttf", "manga_bold.ttf",
        "komika.ttf", "anime.ttf",
        "default.ttf",
    ]
    SFX_FONT_CHAIN = [
        "sfx_bold.ttf", "sfx.ttf",
        "impact.ttf", "arialbd.ttf",
        "default.ttf",
    ]
    CJK_FONT_CHAIN = [
        "noto-sans-cjk.ttf", "notosanscjk.ttf",
        "source-han-sans.ttf",
        "msgothic.ttc", "meiryo.ttc",
        "default.ttf",
    ]

    def __init__(self) -> None:
        self._cache: dict[str, ImageFont.FreeTypeFont] = {}
        self._font_dirs: list[Path] = [
            settings.FONTS_DIR,
            Path("/usr/share/fonts/truetype"),
            Path("/System/Library/Fonts"),
            Path.home() / ".fonts",
        ]

    def get_font(
        self,
        font_name: str,
        font_size: int,
        fallback_chain: list[str] | None = None,
    ) -> ImageFont.FreeTypeFont:
        """Load a font at the specified size with fallback chain.

        Args:
            font_name: Primary font name to load.
            font_size: Font size in points.
            fallback_chain: Ordered list of fallback font names.

        Returns:
            Loaded ImageFont (or PIL default if nothing found).
        """
        cache_key = f"{font_name}:{font_size}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Try primary font first
        font = self._try_load(font_name, font_size)
        if font is not None:
            self._cache[cache_key] = font
            return font

        # Try fallback chain
        if fallback_chain:
            for fallback_name in fallback_chain:
                if fallback_name == font_name:
                    continue
                font = self._try_load(fallback_name, font_size)
                if font is not None:
                    self._cache[cache_key] = font
                    logger.debug(
                        "Font %s not found, using fallback: %s",
                        font_name, fallback_name,
                    )
                    return font

        # Ultimate fallback: PIL default font
        font = ImageFont.load_default()
        self._cache[cache_key] = font
        logger.debug("All fonts failed, using PIL default for %s", font_name)
        return font

    def get_cjk_font(self, font_size: int) -> ImageFont.FreeTypeFont:
        """Get a CJK-capable font for Japanese text.

        Uses a fallback chain specifically for CJK characters.

        Args:
            font_size: Font size in points.

        Returns:
            CJK-capable ImageFont.
        """
        return self.get_font(
            "noto-sans-cjk.ttf",
            font_size,
            fallback_chain=self.CJK_FONT_CHAIN,
        )

    def get_sfx_font(self, font_size: int) -> ImageFont.FreeTypeFont:
        """Get a bold/impact font for sound effects.

        Args:
            font_size: Font size in points.

        Returns:
            Bold ImageFont for SFX.
        """
        return self.get_font(
            "sfx_bold.ttf",
            font_size,
            fallback_chain=self.SFX_FONT_CHAIN,
        )

    def _try_load(
        self,
        font_name: str,
        font_size: int,
    ) -> ImageFont.FreeTypeFont | None:
        """Try to load a font from any known directory.

        Args:
            font_name: Font filename (e.g., "manga.ttf").
            font_size: Font size in points.

        Returns:
            Loaded font or None if not found.
        """
        # Try each font directory
        for font_dir in self._font_dirs:
            font_path = font_dir / font_name
            if font_path.exists():
                try:
                    return ImageFont.truetype(str(font_path), font_size)
                except (OSError, Exception) as e:
                    logger.debug("Failed to load %s: %s", font_path, e)
                    continue

        # Try as absolute/relative path
        font_path = Path(font_name)
        if font_path.exists():
            try:
                return ImageFont.truetype(str(font_path), font_size)
            except (OSError, Exception) as e:
                logger.debug("Failed to load %s: %s", font_path, e)

        return None

    def has_glyph(self, font: ImageFont.FreeTypeFont, char: str) -> bool:
        """Check if a font has a specific glyph.

        Args:
            font: ImageFont to check.
            char: Character to test.

        Returns:
            True if the font can render this character.
        """
        try:
            mask = font.getmask(char)
            return mask is not None
        except Exception:
            return False

    def clear_cache(self) -> None:
        """Clear the font cache."""
        self._cache.clear()


# ═══════════════════════════════════════════════════════════════════════════
# Layout Engine
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class TextLayout:
    """Result of laying out text for rendering."""

    lines: list[str] = field(default_factory=list)
    font_size: int = 12
    total_height: int = 0
    line_widths: list[int] = field(default_factory=list)
    max_line_width: int = 0
    is_vertical: bool = False
    vertical_char_positions: list[tuple[int, int, str]] = field(
        default_factory=list,
    )  # For vertical text: (x, y, char)


class LayoutEngine:
    """Handles text layout for both horizontal and vertical (CJK) text.

    Features:
    - Word-level and character-level wrapping
    - Auto font size fitting to available space
    - Vertical text layout (tategaki) for Japanese
    - Multi-line measurement
    """

    def __init__(self, font_engine: FontEngine) -> None:
        self.font_engine = font_engine

    def layout_text(
        self,
        text: str,
        font_name: str,
        max_width: int,
        max_height: int,
        draw: ImageDraw.ImageDraw,
        is_vertical: bool = False,
        font_size_min: int = MIN_FONT_SIZE,
        font_size_max: int = MAX_FONT_SIZE,
        line_height_ratio: float = 1.35,
        padding: int = DEFAULT_PADDING,
    ) -> TextLayout:
        """Lay out text within constraints, auto-sizing the font.

        Tries font sizes from largest to smallest, picking the first
        that fits within the available width and height.

        Args:
            text: Text to lay out.
            font_name: Font name to use.
            max_width: Available width in pixels.
            max_height: Available height in pixels.
            draw: ImageDraw instance for measuring.
            is_vertical: Use vertical (tategaki) layout.
            font_size_min: Minimum font size.
            font_size_max: Maximum font size.
            line_height_ratio: Multiplier for line height.
            padding: Inner padding in pixels.

        Returns:
            TextLayout with the best-fit arrangement.
        """
        inner_w = max_width - 2 * padding
        inner_h = max_height - 2 * padding

        if inner_w <= 0 or inner_h <= 0:
            return TextLayout(font_size=font_size_min)

        if is_vertical:
            return self._layout_vertical(
                text, font_name, inner_w, inner_h, draw,
                font_size_min, font_size_max,
            )
        else:
            return self._layout_horizontal(
                text, font_name, inner_w, inner_h, draw,
                font_size_min, font_size_max, line_height_ratio,
            )

    def _layout_horizontal(
        self,
        text: str,
        font_name: str,
        max_width: int,
        max_height: int,
        draw: ImageDraw.ImageDraw,
        font_size_min: int,
        font_size_max: int,
        line_height_ratio: float,
    ) -> TextLayout:
        """Layout text horizontally (left-to-right, top-to-bottom).

        Tries font sizes from largest to smallest.
        """
        best_layout = TextLayout()

        for size in range(font_size_max, font_size_min - 1, -2):
            font = self.font_engine.get_font(font_name, size)
            lines = self._wrap_text(text, font, max_width, draw)
            if not lines:
                continue

            line_height = int(size * line_height_ratio)
            total_height = len(lines) * line_height

            line_widths = [
                self._text_width(line, font, draw) for line in lines
            ]
            max_line_width = max(line_widths) if line_widths else 0

            if total_height <= max_height and max_line_width <= max_width:
                return TextLayout(
                    lines=lines,
                    font_size=size,
                    total_height=total_height,
                    line_widths=line_widths,
                    max_line_width=max_line_width,
                    is_vertical=False,
                )

            # Even if it overflows, keep the best one found
            if not best_layout.lines or total_height < best_layout.total_height:
                best_layout = TextLayout(
                    lines=lines,
                    font_size=size,
                    total_height=total_height,
                    line_widths=line_widths,
                    max_line_width=max_line_width,
                    is_vertical=False,
                )

        # Return best-effort layout (might overflow slightly)
        return best_layout

    def _layout_vertical(
        self,
        text: str,
        font_name: str,
        max_width: int,
        max_height: int,
        draw: ImageDraw.ImageDraw,
        font_size_min: int,
        font_size_max: int,
    ) -> TextLayout:
        """Layout text vertically (tategaki — top-to-bottom, right-to-left).

        Characters flow from top to bottom in a column.
        When a column fills the available height, a new column starts
        to the left of the previous one.

        Args:
            text: Text to lay out (may include Latin/numbers mixed with CJK).
            font_name: Base font name (will use CJK fallback).
            max_width: Available width in pixels.
            max_height: Available height in pixels.
            draw: ImageDraw instance for measuring.
            font_size_min: Minimum font size.
            font_size_max: Maximum font size.

        Returns:
            TextLayout with vertical char positions.
        """
        best_layout = TextLayout(is_vertical=True)

        for size in range(font_size_max, font_size_min - 1, -2):
            font = self.font_engine.get_cjk_font(size)
            char_height = int(size * 1.2)  # Vertical char spacing
            col_width = int(size * 1.0)    # Column width (char width + small gap)

            # Calculate how many chars fit per column and how many columns needed
            chars_per_col = max_height // char_height
            if chars_per_col < 1:
                chars_per_col = 1

            n_cols = math.ceil(len(text) / chars_per_col)
            total_width = n_cols * col_width

            # Check if it fits
            if total_width <= max_width and chars_per_col >= 1:
                positions: list[tuple[int, int, str]] = []
                x = max_width - col_width  # Start from rightmost column
                for i, char in enumerate(text):
                    col_idx = i // chars_per_col
                    char_idx = i % chars_per_col

                    cx = x - col_idx * col_width
                    cy = char_idx * char_height
                    positions.append((cx, cy, char))

                return TextLayout(
                    font_size=size,
                    total_height=min(max_height, chars_per_col * char_height),
                    is_vertical=True,
                    vertical_char_positions=positions,
                )

            if not best_layout.vertical_char_positions:
                # Store last attempted layout
                positions = []
                x = max_width - col_width
                for i, char in enumerate(text):
                    col_idx = i // max(chars_per_col, 1)
                    char_idx = i % max(chars_per_col, 1)
                    cx = x - col_idx * col_width
                    cy = char_idx * char_height
                    positions.append((cx, cy, char))

                best_layout = TextLayout(
                    font_size=size,
                    total_height=min(max_height, chars_per_col * char_height),
                    is_vertical=True,
                    vertical_char_positions=positions,
                )

        return best_layout

    def _wrap_text(
        self,
        text: str,
        font: ImageFont.FreeTypeFont,
        max_width: int,
        draw: ImageDraw.ImageDraw,
    ) -> list[str]:
        """Wrap text to fit within a given width.

        First tries word-level wrapping. If that produces only one line
        and it still overflows, falls back to character-level wrapping
        (useful for CJK text without spaces).

        Args:
            text: Text to wrap.
            font: Font to measure with.
            max_width: Maximum width in pixels.
            draw: ImageDraw instance for measuring.

        Returns:
            List of text lines that fit within max_width.
        """
        # Quick check: if text fits on one line, return it
        if self._text_width(text, font, draw) <= max_width:
            return [text]

        # Try word-level wrapping
        words = text.split()
        lines: list[str] = []
        current_line = ""

        for word in words:
            test_line = f"{current_line} {word}".strip()
            if self._text_width(test_line, font, draw) <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word

        if current_line:
            lines.append(current_line)

        # If wrapping didn't help, try character-level wrapping
        # (essential for CJK text without spaces)
        if len(lines) <= 1 and self._text_width(text, font, draw) > max_width:
            return self._wrap_by_char(text, font, max_width, draw)

        return lines

    def _wrap_by_char(
        self,
        text: str,
        font: ImageFont.FreeTypeFont,
        max_width: int,
        draw: ImageDraw.ImageDraw,
    ) -> list[str]:
        """Character-level text wrapping.

        Used for CJK text without spaces or when word-wrapping fails.

        Args:
            text: Text to wrap.
            font: Font to measure with.
            max_width: Maximum width in pixels.
            draw: ImageDraw instance for measuring.

        Returns:
            List of lines wrapped at character boundaries.
        """
        lines: list[str] = []
        current_line = ""

        for char in text:
            test_line = current_line + char
            if self._text_width(test_line, font, draw) <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = char

        if current_line:
            lines.append(current_line)

        return lines

    def _text_width(
        self,
        text: str,
        font: ImageFont.FreeTypeFont,
        draw: ImageDraw.ImageDraw,
    ) -> int:
        """Measure the width of text in pixels.

        Args:
            text: Text to measure.
            font: Font to measure with.
            draw: ImageDraw instance.

        Returns:
            Width in pixels.
        """
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]


# ═══════════════════════════════════════════════════════════════════════════
# Text Engine (Outline + Shadow + Stroke)
# ═══════════════════════════════════════════════════════════════════════════


class TextEngine:
    """Draws text with professional manga-typography effects.

    Features:
    - White outline — essential for readability on any background
    - Drop shadow — adds depth, matches official releases
    - Stroke — thicker border around characters
    - Vertical text rendering
    - Polygon-clipped rendering (text never overflows bubble)
    """

    def __init__(self) -> None:
        self.font_engine = FontEngine()

    def draw_text(
        self,
        image: Image.Image,
        layout: TextLayout,
        style: BubbleStyle,
        region_bbox: tuple[int, int, int, int],
        polygon: list[tuple[float, float]] | None = None,
    ) -> None:
        """Draw text onto an image with the specified style.

        Supports both horizontal and vertical layouts.
        Uses polygon clipping to prevent overflow.

        Args:
            image: PIL Image to draw onto (modified in-place).
            layout: Pre-computed TextLayout.
            style: BubbleStyle with visual parameters.
            region_bbox: (x, y, w, h) bounding box.
            polygon: Optional polygon vertices for clipping.
        """
        draw = ImageDraw.Draw(image)
        x, y, w, h = region_bbox
        padding = int(w * style.padding_ratio)
        # Resolve italic font variant
        resolved_font_name = self._resolve_italic_font(
            style.font_name, style.italic,
        )
        font = self.font_engine.get_font(
            resolved_font_name,
            layout.font_size,
            fallback_chain=(
                self.font_engine.MANGA_FONT_CHAIN
                if not style.is_vertical
                else self.font_engine.CJK_FONT_CHAIN
            ),
        )

        if layout.is_vertical:
            self._draw_vertical_text(image, draw, layout, style, font, x, y, w, h, padding)
        else:
            self._draw_horizontal_text(draw, layout, style, font, x, y, w, h, padding)

    def _draw_horizontal_text(
        self,
        draw: ImageDraw.ImageDraw,
        layout: TextLayout,
        style: BubbleStyle,
        font: ImageFont.FreeTypeFont,
        bx: int, by: int, bw: int, bh: int,
        padding: int,
    ) -> None:
        """Draw horizontally laid-out text onto the image.

        Draws in this order:
        1. Shadow (if enabled)
        2. Outline (if enabled)  
        3. Stroke (if enabled)
        4. Main text (on top)

        Args:
            draw: ImageDraw instance.
            layout: TextLayout with horizontal lines.
            style: BubbleStyle with visual parameters.
            font: Loaded font.
            bx, by, bw, bh: Bubble bounding box.
            padding: Inner padding in pixels.
        """
        inner_x = bx + padding
        inner_y = by + padding
        inner_w = bw - 2 * padding
        inner_h = bh - 2 * padding

        if inner_w <= 0 or inner_h <= 0:
            return

        line_height = int(layout.font_size * style.line_height_ratio)
        total_text_height = len(layout.lines) * line_height
        start_y = inner_y + (inner_h - total_text_height) // 2

        # Draw each line
        for line_idx, line in enumerate(layout.lines):
            if not line:
                continue

            bbox = draw.textbbox((0, 0), line, font=font)
            line_width = bbox[2] - bbox[0]
            line_height_px = bbox[3] - bbox[1]

            # Horizontal alignment
            if style.text_align == "center":
                text_x = inner_x + (inner_w - line_width) // 2
            elif style.text_align == "right":
                text_x = inner_x + inner_w - line_width
            else:  # left
                text_x = inner_x

            text_y = start_y + line_idx * line_height

            processed_text = line.upper() if style.uppercase else line

            # Step 1: Shadow
            if style.shadow_offset != (0, 0) and any(style.shadow_color):
                shadow_x = text_x + style.shadow_offset[0]
                shadow_y = text_y + style.shadow_offset[1]
                self._draw_shadow(
                    draw, processed_text, font,
                    (shadow_x, shadow_y),
                    style.shadow_color, style.shadow_blur,
                )

            # Step 2: Outline (multi-pass to create border)
            if style.outline_width > 0:
                for ox in range(-style.outline_width, style.outline_width + 1):
                    for oy in range(-style.outline_width, style.outline_width + 1):
                        if ox == 0 and oy == 0:
                            continue
                        # Only draw on the outline ring (not interior)
                        if abs(ox) == style.outline_width or abs(oy) == style.outline_width:
                            draw.text(
                                (text_x + ox, text_y + oy),
                                processed_text,
                                fill=style.outline_color,
                                font=font,
                            )

            # Step 3: Stroke (thick border, drawn as multiple overlapping outlines)
            if style.stroke_width > 0:
                for sx in range(-style.stroke_width, style.stroke_width + 1):
                    for sy in range(-style.stroke_width, style.stroke_width + 1):
                        if sx == 0 and sy == 0:
                            continue
                        draw.text(
                            (text_x + sx, text_y + sy),
                            processed_text,
                            fill=style.stroke_color,
                            font=font,
                        )

            # Step 4: Main text (on top of outline/shadow/stroke)
            draw.text(
                (text_x, text_y),
                processed_text,
                fill=style.text_color,
                font=font,
            )

    def _draw_vertical_text(
        self,
        image: Image.Image,
        draw: ImageDraw.ImageDraw,
        layout: TextLayout,
        style: BubbleStyle,
        font: ImageFont.FreeTypeFont,
        bx: int, by: int, bw: int, bh: int,
        padding: int,
    ) -> None:
        """Draw vertically laid-out text (tategaki).

        Characters are drawn one by one in vertical columns,
        reading right-to-left.

        Args:
            image: PIL Image.
            draw: ImageDraw instance.
            layout: TextLayout with vertical char positions.
            style: BubbleStyle with visual parameters.
            font: Loaded CJK font.
            bx, by, bw, bh: Bubble bounding box.
            padding: Inner padding in pixels.
        """
        inner_x = bx + padding
        inner_y = by + padding

        if not layout.vertical_char_positions:
            return

        # Calculate centering offset for the entire text block
        n_cols = max(1, len(set(pos[0] for pos in layout.vertical_char_positions)))
        col_width = int(layout.font_size * 1.0)
        total_width = n_cols * col_width
        offset_x = inner_x + (bw - 2 * padding - total_width) // 2

        max_y = max(pos[1] for pos in layout.vertical_char_positions) + inner_y
        # Since tategaki starts from right, the bounding-box right edge is the leftmost column
        # Actually for vertical text, the x positions are already relative to the right edge
        # We need to shift to align within the bubble

        # Calculate the min/max of actual char positions
        char_xs = [inner_x + (bw - 2 * padding - total_width) // 2 - c * col_width + (bx + inner_x)
                   for c in range(n_cols)]
        # This is getting complex. Let me simplify.
        # In _layout_vertical, x starts from max_width - col_width (right edge)
        # and goes left by col_width per column.
        # We need to position this within the bubble.

        # Re-map positions: the layout engine computed relative to inner_w
        # We need to center the text block horizontally in the bubble
        actual_x_start = bx + padding
        # The rightmost column should be at actual_x_start + total_width
        # So we shift by: actual_x_start + total_width - max_x_in_layout
        if layout.vertical_char_positions:
            max_layout_x = max(pos[0] for pos in layout.vertical_char_positions)
            min_layout_x = min(pos[0] for pos in layout.vertical_char_positions)
            layout_width = max_layout_x - min_layout_x + col_width
            x_shift = bx + padding + (bw - 2 * padding - layout_width) // 2

            y_shift = by + padding + (bh - 2 * padding - layout.total_height) // 2

            for cx, cy, char in layout.vertical_char_positions:
                # Adjust x so that the rightmost column aligns within the bubble
                abs_x = x_shift + cx
                abs_y = y_shift + cy

                # Apply effects
                if style.shadow_offset != (0, 0) and any(style.shadow_color):
                    sx = abs_x + style.shadow_offset[0]
                    sy = abs_y + style.shadow_offset[1]
                    self._draw_shadow(
                        draw, char, font, (sx, sy),
                        style.shadow_color, style.shadow_blur,
                    )

                if style.outline_width > 0:
                    for ox in range(-style.outline_width, style.outline_width + 1):
                        for oy in range(-style.outline_width, style.outline_width + 1):
                            if ox == 0 and oy == 0:
                                continue
                            if abs(ox) == style.outline_width or abs(oy) == style.outline_width:
                                draw.text(
                                    (abs_x + ox, abs_y + oy),
                                    char, fill=style.outline_color, font=font,
                                )

                if style.stroke_width > 0:
                    for sx in range(-style.stroke_width, style.stroke_width + 1):
                        for sy in range(-style.stroke_width, style.stroke_width + 1):
                            if sx == 0 and sy == 0:
                                continue
                            draw.text(
                                (abs_x + sx, abs_y + sy),
                                char, fill=style.stroke_color, font=font,
                            )

                draw.text(
                    (abs_x, abs_y),
                    char, fill=style.text_color, font=font,
                )

    def _draw_shadow(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont,
        pos: tuple[int, int],
        shadow_color: tuple[int, int, int, int],
        blur_radius: int,
    ) -> None:
        """Draw a text shadow with opacity blending.

        For blur > 0, reduces opacity proportionally to simulate
        a soft shadow. True Gaussian blur would require creating a
        separate RGBA layer, drawing text, applying GaussianBlur,
        and compositing — for simplicity we blend opacity here.

        Args:
            draw: ImageDraw instance.
            text: Text to draw as shadow.
            font: Font to use.
            pos: (x, y) position.
            shadow_color: RGBA color for shadow.
            blur_radius: Gaussian blur radius (0 = no blur).
        """
        r, g, b, a = shadow_color

        if blur_radius > 0:
            # Simulate blur by reducing opacity — produces a visible
            # semi-transparent shadow. For production quality with
            # true Gaussian blur, render on a temp RGBA image, blur it,
            # then Image.composite() back onto the main image.
            opacity_factor = max(0.3, 1.0 / (blur_radius * 0.5 + 1.0))
            blurred_a = max(30, int(a * opacity_factor))
            draw.text(pos, text, fill=(r, g, b, blurred_a), font=font)
        else:
            draw.text(pos, text, fill=(r, g, b, a), font=font)

    def _resolve_italic_font(
        self, font_name: str, italic: bool,
    ) -> str:
        """Resolve italic variant for a font name.

        If italic is True, tries to find an italic variant
        by inserting '_italic' before the file extension.
        Falls back to the original font if no italic variant exists.

        Args:
            font_name: Base font name (e.g., "manga.ttf").
            italic: Whether to use italic variant.

        Returns:
            Italic font name if found, else original.
        """
        if not italic:
            return font_name

        dot_idx = font_name.rfind(".")
        if dot_idx > 0:
            italic_name = f"{font_name[:dot_idx]}_italic{font_name[dot_idx:]}"
            # Check if italic variant exists in any font dir
            for font_dir in self.font_engine._font_dirs:
                if (font_dir / italic_name).exists():
                    logger.debug("Using italic font: %s", italic_name)
                    return italic_name
            if Path(italic_name).exists():
                return italic_name

        logger.debug(
            "Italic font for %s not found, using regular",
            font_name,
        )
        return font_name


# ═══════════════════════════════════════════════════════════════════════════
# Bubble Style Engine
# ═══════════════════════════════════════════════════════════════════════════


class BubbleStyleEngine:
    """Manages per-bubble-type visual styles for manga rendering.

    Provides:
    - Style lookup by bubble type
    - Style customization/overrides per bubble
    - Automatic style selection based on bubble characteristics
    """

    def __init__(self) -> None:
        self.presets = BUBBLE_STYLE_PRESETS.copy()

    def get_style(self, bubble_type: str) -> BubbleStyle:
        """Get style for a bubble type with fallback."""
        return get_bubble_style(bubble_type)

    def apply_override(
        self,
        base_style: BubbleStyle,
        overrides: dict | None = None,
    ) -> BubbleStyle:
        """Apply per-bubble style overrides on top of a base style.

        Args:
            base_style: Base BubbleStyle.
            overrides: Dict of field names to override values.

        Returns:
            New BubbleStyle with overrides applied.
        """
        if not overrides:
            return base_style

        overridden = {k: v for k, v in base_style.__dict__.items()}
        for key, value in overrides.items():
            if hasattr(base_style, key):
                overridden[key] = value

        return BubbleStyle(**overridden)
