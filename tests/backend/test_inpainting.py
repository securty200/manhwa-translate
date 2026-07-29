"""Tests for the inpainting service."""

from __future__ import annotations

import pytest
from PIL import Image

from backend.inpainting import InpaintingService, InpaintRegion, InpaintResult


@pytest.mark.asyncio
async def test_inpainting_initialization():
    """Test that inpainting service initializes."""
    service = InpaintingService(engine_priority=["opencv"])
    await service.initialize()
    assert "opencv" in service._engines
    await service.cleanup()


@pytest.mark.asyncio
async def test_inpaint_single_region():
    """Test inpainting a single region with a bbox."""
    service = InpaintingService(engine_priority=["opencv"])
    await service.initialize()

    img = Image.new("RGB", (200, 200), color="white")
    region = InpaintRegion(bbox=(10, 10, 50, 30))
    result = await service.inpaint_region(img, region)
    assert result is not None
    assert result.regions_inpainted >= 0
    assert result.image.size == (200, 200)
    await service.cleanup()


@pytest.mark.asyncio
async def test_inpaint_batch():
    """Test batch inpainting with multiple regions (backward compat)."""
    service = InpaintingService(engine_priority=["opencv"])
    await service.initialize()

    img = Image.new("RGB", (500, 500), color="white")
    regions = [
        InpaintRegion(bbox=(10, 10, 50, 30)),
        InpaintRegion(bbox=(100, 100, 80, 40)),
    ]
    result = await service.inpaint_page(img, regions)
    assert result.regions_inpainted == 2
    assert result.image.size == (500, 500)
    assert result.processing_time_ms > 0
    await service.cleanup()


@pytest.mark.asyncio
async def test_inpaint_with_polygon():
    """Test inpainting with a polygon region."""
    service = InpaintingService(engine_priority=["opencv"])
    await service.initialize()

    img = Image.new("RGB", (200, 200), color="white")
    polygon = [(10, 10), (60, 10), (60, 40), (10, 40)]
    region = InpaintRegion(
        bbox=(10, 10, 50, 30),
        polygon=polygon,
    )
    result = await service.inpaint_region(img, region)
    assert result is not None
    assert result.polygons_used >= 1
    await service.cleanup()


@pytest.mark.asyncio
async def test_inpaint_empty_regions():
    """Test inpainting with no regions (should return original image)."""
    service = InpaintingService(engine_priority=["opencv"])
    await service.initialize()

    img = Image.new("RGB", (200, 200), color="white")
    result = await service.inpaint_page(img, [])
    assert result.regions_inpainted == 0
    # Image should be unchanged
    import numpy as np
    assert np.array_equal(np.array(result.image), np.array(img))
    await service.cleanup()


@pytest.mark.asyncio
async def test_inpaint_no_engines():
    """Test inpainting when no engines are available."""
    service = InpaintingService(
        engine_priority=["nonexistent_engine"],
    )
    # Should not crash even with unknown engine
    await service.initialize()

    img = Image.new("RGB", (200, 200), color="white")
    region = InpaintRegion(bbox=(10, 10, 50, 30))
    result = await service.inpaint_region(img, region)
    assert result is not None
    assert result.regions_inpainted == 0
    await service.cleanup()


@pytest.mark.asyncio
async def test_inpaint_batch_legacy_tuples():
    """Test inpaint_batch with legacy tuple format (backward compat)."""
    service = InpaintingService(engine_priority=["opencv"])
    await service.initialize()

    img = Image.new("RGB", (200, 200), color="white")
    # Legacy format: list of (x, y, w, h) tuples
    regions: list[InpaintRegion | tuple[int, int, int, int]] = [
        (10, 10, 50, 30),
        (100, 100, 80, 40),
    ]
    result = await service.inpaint_batch(img, regions)
    assert result.regions_inpainted == 2
    assert result.image.size == (200, 200)
    await service.cleanup()
