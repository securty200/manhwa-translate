"""Text rendering module for overlaying translated text onto manga pages.

Provides professional manga-typography rendering with:
- Outline / Shadow / Stroke effects
- Vertical text (tategaki — 縦書き)
- Per-bubble-type styling (speech, thought, narration, sfx, sign, title, poster)
- Polygon-based clipping (text never overflows bubbles)
- Auto font sizing with CJK fallback chains
- No white background fill
"""

from backend.renderer.engines import (
    BubbleStyle,
    BubbleStyleEngine,
    BUBBLE_STYLE_PRESETS,
    FontEngine,
    LayoutEngine,
    TextEngine,
    TextLayout,
    get_bubble_style,
)

from backend.renderer.service import (
    RenderService,
    RenderResult,
)

from backend.renderer.schemas import (
    BubbleRenderInfo,
    RenderPageRequest,
    RenderPageResponse,
    BubbleRenderResult,
    RenderStats,
)

__all__ = [
    # Engines
    "BubbleStyle",
    "BubbleStyleEngine",
    "BUBBLE_STYLE_PRESETS",
    "FontEngine",
    "LayoutEngine",
    "TextEngine",
    "TextLayout",
    "get_bubble_style",
    # Service
    "RenderService",
    "RenderResult",
    # Schemas
    "BubbleRenderInfo",
    "RenderPageRequest",
    "RenderPageResponse",
    "BubbleRenderResult",
    "RenderStats",
]
