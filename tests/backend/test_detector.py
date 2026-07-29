"""Tests for the text detection service."""

from __future__ import annotations

import pytest
from PIL import Image

from backend.detector.service import DetectionService


@pytest.mark.asyncio
async def test_detection_initialization():
    """Test that detection service initializes."""
    service = DetectionService(model_name="craft")
    await service.initialize()
    assert service._initialized
    await service.cleanup()


@pytest.mark.asyncio
async def test_detection_empty_page():
    """Test detection on a blank page (should return no regions)."""
    service = DetectionService(model_name="craft")
    img = Image.new("RGB", (800, 1200), color="white")
    result = await service.detect_regions(img)
    assert isinstance(result.regions, list)
    assert result.page_width == 800
    assert result.page_height == 1200
    assert isinstance(result.processing_time_ms, float)
    await service.cleanup()


@pytest.mark.asyncio
async def test_fallback_detection():
    """Test fallback detection logic when no ML model is loaded."""
    service = DetectionService(model_name="craft")
    service._model = None  # Force fallback mode
    service._initialized = True

    img = Image.new("RGB", (800, 1200), color="white")
    result = await service.detect_regions(img)
    assert isinstance(result.regions, list)
    await service.cleanup()
