"""Tests for the OCR service."""

from __future__ import annotations

import pytest
from PIL import Image

from backend.ocr.service import OCRService


@pytest.mark.asyncio
async def test_ocr_service_initialization():
    """Test that the OCR service can be initialized."""
    service = OCRService(engine_priority=["paddleocr", "easyocr", "tesseract"])
    await service.initialize()
    assert isinstance(service._initialized, dict)
    await service.cleanup()


@pytest.mark.asyncio
async def test_ocr_extract_empty_image():
    """Test OCR on a blank image (should return empty or low-confidence text)."""
    service = OCRService(engine_priority=["paddleocr", "easyocr", "tesseract"])
    img = Image.new("RGB", (100, 100), color="white")
    result = await service.extract_text(img)
    assert result.text is not None
    assert isinstance(result.processing_time_ms, float)
    await service.cleanup()


@pytest.mark.asyncio
async def test_ocr_batch_extraction():
    """Test batch OCR with multiple regions."""
    service = OCRService(engine_priority=["paddleocr", "easyocr", "tesseract"])
    img = Image.new("RGB", (500, 500), color="white")
    regions = [(10, 10, 100, 50), (200, 200, 150, 60)]
    results = await service.extract_batch(img, regions)
    assert len(results) == 2
    for result in results:
        assert isinstance(result.text, str)
    await service.cleanup()
