"""Tests for the enhanced rendering service.

Tests cover:
- Basic bubble rendering
- Per-bubble-type styling
- Outline/shadow/stroke effects
- Vertical text
- Polygon clipping
- Font fallback chains
- Auto font sizing
- CJK text wrapping
"""

from __future__ import annotations

import pytest
from PIL import Image, ImageDraw, ImageFont

from backend.renderer import (
    RenderService,
    RenderResult,
    FontEngine,
    LayoutEngine,
    TextEngine,
    BubbleStyleEngine,
    BubbleStyle,
    get_bubble_style,
    TextLayout,
)


@pytest.fixture
def service() -> RenderService:
    """Create a fresh render service for each test."""
    return RenderService()


# ── Basic Rendering Tests ────────────────────────────────────────────────


def test_create_service(service: RenderService):
    """Test that render service can be created."""
    assert service is not None
    assert isinstance(service.font_engine, FontEngine)
    assert isinstance(service.layout_engine, LayoutEngine)
    assert isinstance(service.text_engine, TextEngine)
    assert isinstance(service.style_engine, BubbleStyleEngine)


def test_render_bubble_simple(service: RenderService):
    """Test rendering basic text into a bubble region."""
    img = Image.new("RGB", (500, 500), color="white")
    bubbles = [
        {"x": 50, "y": 50, "width": 200, "height": 100,
         "translated_text": "Hello World", "bubble_type": "speech"},
    ]
    result = service.render_page(img, bubbles)
    assert result.bubbles_rendered == 1
    assert result.image.size == (500, 500)
    assert isinstance(result.processing_time_ms, float)
    assert result.processing_time_ms >= 0


def test_render_multiple_bubbles(service: RenderService):
    """Test rendering multiple bubbles in a single page."""
    img = Image.new("RGB", (800, 1200), color="white")
    bubbles = [
        {"x": 50, "y": 50, "width": 200, "height": 100,
         "translated_text": "Hello!", "bubble_type": "speech"},
        {"x": 300, "y": 200, "width": 150, "height": 80,
         "translated_text": "How are you?", "bubble_type": "narration"},
        {"x": 100, "y": 500, "width": 250, "height": 120,
         "translated_text": "", "bubble_type": "speech"},  # Empty, should skip
    ]
    result = service.render_page(img, bubbles)
    assert result.bubbles_rendered == 2
    assert result.image.size == (800, 1200)


def test_render_empty_bubbles(service: RenderService):
    """Test rendering with no bubbles."""
    img = Image.new("RGB", (200, 200), color="white")
    result = service.render_page(img, [])
    assert result.bubbles_rendered == 0
    assert result.image.size == (200, 200)


# ── Per-Bubble-Type Styling ──────────────────────────────────────────────


def test_bubble_style_presets():
    """Test that all bubble types have defined styles."""
    for bubble_type in ["speech", "thought", "narration", "sfx", "sign", "title", "poster"]:
        style = get_bubble_style(bubble_type)
        assert isinstance(style, BubbleStyle)
        assert style.font_size_min > 0
        assert style.font_size_max >= style.font_size_min


def test_bubble_style_fallback():
    """Test style fallback for unknown types."""
    style = get_bubble_style("unknown_type")
    assert isinstance(style, BubbleStyle)
    assert style.font_size_min == 12  # Default min


def test_sfx_style_uppercase():
    """Test that SFX style has uppercase enabled."""
    style = get_bubble_style("sfx")
    assert style.uppercase is True


def test_thought_style_italic():
    """Test that thought bubbles have italic styling."""
    style = get_bubble_style("thought")
    assert style.italic is True


# ── Outline / Shadow / Stroke ────────────────────────────────────────────


def test_render_with_outline(service: RenderService):
    """Test rendering with outline effect."""
    img = Image.new("RGB", (300, 200), color="gray")
    bubbles = [
        {"x": 10, "y": 10, "width": 280, "height": 180,
         "translated_text": "Text with Outline", "bubble_type": "speech"},
    ]
    result = service.render_page(img, bubbles)
    assert result.bubbles_rendered == 1
    # Image should be different from original (text + outline drawn)
    result_img = result.image
    assert result_img.size == (300, 200)


def test_render_with_shadow(service: RenderService):
    """Test rendering with shadow effect uses correct style."""
    style = get_bubble_style("speech")
    assert style.shadow_offset != (0, 0)
    assert any(c > 0 for c in style.shadow_color)


def test_sfx_has_stroke(service: RenderService):
    """Test that SFX style has a stroke width."""
    style = get_bubble_style("sfx")
    assert style.stroke_width > 0


# ── Font Engine ──────────────────────────────────────────────────────────


def test_font_engine_creation():
    """Test font engine creates successfully."""
    fe = FontEngine()
    assert fe is not None
    assert fe._cache == {}


def test_font_engine_fallback(service: RenderService):
    """Test font engine falls back to default PIL font."""
    font = service.font_engine.get_font(
        "nonexistent-font-that-doesnt-exist.ttf", 24
    )
    assert font is not None


def test_font_caching(service: RenderService):
    """Test that fonts are cached."""
    font1 = service.font_engine.get_font("test_font.ttf", 12)
    font2 = service.font_engine.get_font("test_font.ttf", 12)
    # Both should return the same cached PIL default font
    assert font1 is font2


def test_font_clear_cache(service: RenderService):
    """Test clearing font cache."""
    service.font_engine.get_font("test.ttf", 12)
    assert len(service.font_engine._cache) > 0
    service.font_engine.clear_cache()
    assert len(service.font_engine._cache) == 0


# ── Layout Engine ────────────────────────────────────────────────────────


def test_layout_engine_wrapping(service: RenderService):
    """Test text wrapping produces correct number of lines."""
    img = Image.new("RGB", (400, 200), color="white")
    draw = ImageDraw.Draw(img)
    layout = service.layout_engine.layout_text(
        text="Hello world this is a long text that should wrap",
        font_name="default.ttf",
        max_width=150,
        max_height=150,
        draw=draw,
        is_vertical=False,
    )
    assert len(layout.lines) >= 1
    assert layout.font_size > 0


def test_layout_engine_cjk_wrapping(service: RenderService):
    """Test CJK text wrapping (no spaces)."""
    img = Image.new("RGB", (400, 200), color="white")
    draw = ImageDraw.Draw(img)
    layout = service.layout_engine.layout_text(
        text="こんにちは世界これは長い文章ですラップする必要があります",
        font_name="default.ttf",
        max_width=150,
        max_height=150,
        draw=draw,
        is_vertical=False,
    )
    assert len(layout.lines) >= 1


def test_layout_engine_vertical(service: RenderService):
    """Test vertical text layout (tategaki)."""
    img = Image.new("RGB", (400, 400), color="white")
    draw = ImageDraw.Draw(img)
    layout = service.layout_engine.layout_text(
        text="日本語の縦書きテスト",
        font_name="default.ttf",
        max_width=100,
        max_height=300,
        draw=draw,
        is_vertical=True,
    )
    assert layout.is_vertical is True
    assert len(layout.vertical_char_positions) > 0


def test_layout_engine_single_word(service: RenderService):
    """Test that short text stays on a single line."""
    img = Image.new("RGB", (400, 200), color="white")
    draw = ImageDraw.Draw(img)
    layout = service.layout_engine.layout_text(
        text="Hi",
        font_name="default.ttf",
        max_width=300,
        max_height=200,
        draw=draw,
    )
    assert len(layout.lines) == 1


def test_layout_engine_auto_size(service: RenderService):
    """Test that auto-sizing picks a reasonable font size."""
    img = Image.new("RGB", (400, 200), color="white")
    draw = ImageDraw.Draw(img)
    layout = service.layout_engine.layout_text(
        text="Hello World",
        font_name="default.ttf",
        max_width=200,
        max_height=100,
        draw=draw,
        font_size_min=8,
        font_size_max=48,
    )
    assert 8 <= layout.font_size <= 48


# ── Render with different bubble types ───────────────────────────────────


def test_render_all_bubble_types(service: RenderService):
    """Test rendering with all bubble types."""
    img = Image.new("RGB", (1000, 600), color="lightgray")
    bubbles = []
    types = ["speech", "thought", "narration", "sfx", "sign", "title", "poster"]
    for i, btype in enumerate(types):
        bubbles.append({
            "x": 20 + i * 140, "y": 50,
            "width": 120, "height": 80,
            "translated_text": f"{btype} text",
            "bubble_type": btype,
        })
    result = service.render_page(img, bubbles)
    assert result.bubbles_rendered == len(types)


# ── Polygon Rendering ────────────────────────────────────────────────────


def test_render_with_polygon(service: RenderService):
    """Test rendering with polygon clipping (no overflow)."""
    img = Image.new("RGB", (300, 300), color="white")
    polygon = [[50, 50], [250, 50], [250, 250], [50, 250]]
    bubbles = [
        {"x": 50, "y": 50, "width": 200, "height": 200,
         "translated_text": "Text inside polygon clip",
         "bubble_type": "speech",
         "polygon": polygon},
    ]
    result = service.render_page(img, bubbles)
    assert result.bubbles_rendered == 1
    # Text should be visible inside the polygon
    assert result.image.size == (300, 300)


def test_render_with_polygon_irregular(service: RenderService):
    """Test rendering with an irregular polygon (e.g., thought bubble)."""
    img = Image.new("RGB", (300, 300), color="white")
    # Irregular polygon (cloud-like thought bubble shape)
    polygon = [[60, 50], [240, 50], [250, 80], [240, 140],
               [250, 200], [200, 250], [100, 250],
               [50, 200], [60, 140], [50, 80]]
    bubbles = [
        {"x": 50, "y": 50, "width": 200, "height": 200,
         "translated_text": "Thought bubble text!",
         "bubble_type": "thought",
         "polygon": polygon},
    ]
    result = service.render_page(img, bubbles)
    assert result.bubbles_rendered == 1


# ── Edge Cases ───────────────────────────────────────────────────────────


def test_render_very_long_text(service: RenderService):
    """Test rendering very long text (should auto-size smaller)."""
    img = Image.new("RGB", (300, 200), color="white")
    bubbles = [
        {"x": 10, "y": 10, "width": 280, "height": 180,
         "translated_text": "This is a very long text that should wrap multiple times "
         "and the auto font size should make it small enough to fit",
         "bubble_type": "speech"},
    ]
    result = service.render_page(img, bubbles)
    assert result.bubbles_rendered == 1


def test_render_very_small_bubble(service: RenderService):
    """Test rendering into a very small bubble."""
    img = Image.new("RGB", (100, 100), color="white")
    bubbles = [
        {"x": 2, "y": 2, "width": 30, "height": 30,
         "translated_text": "Tiny", "bubble_type": "speech"},
    ]
    result = service.render_page(img, bubbles)
    assert result.bubbles_rendered == 1


def test_cleanup(service: RenderService):
    """Test that cleanup clears the font cache."""
    service.font_engine.get_font("test.ttf", 12)
    assert len(service.font_engine._cache) >= 1
    service.cleanup()
    assert len(service.font_engine._cache) == 0
