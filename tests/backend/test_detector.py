"""Tests for the text detection service."""

from __future__ import annotations

import pytest
from PIL import Image

from backend.detector.service import DetectionService


@pytest.mark.asyncio
async def test_detection_initialization():
    """Test that detection service initializes."""
    service = DetectionService(engine_priority=["yolo", "groundingdino", "sam2"])
    await service.initialize()
    assert isinstance(service._initialized, dict)
    await service.cleanup()


@pytest.mark.asyncio
async def test_detection_empty_page():
    """Test detection on a blank page (should return no regions)."""
    service = DetectionService(engine_priority=["yolo", "groundingdino", "sam2"])
    img = Image.new("RGB", (800, 1200), color="white")
    result = await service.detect_page(img)
    assert isinstance(result.regions, list)
    assert result.page_width == 800
    assert result.page_height == 1200
    assert isinstance(result.total_processing_time_ms, float)
    await service.cleanup()


@pytest.mark.asyncio
async def test_fallback_detection():
    """Test fallback detection logic when no ML model is loaded."""
    service = DetectionService(engine_priority=["yolo", "groundingdino", "sam2"])
    service._engines = {}
    service._initialized = {"yolo": False, "groundingdino": False, "sam2": False}

    img = Image.new("RGB", (800, 1200), color="white")
    result = await service.detect_page(img, allow_fallback=True)
    assert isinstance(result.regions, list)
    await service.cleanup()
