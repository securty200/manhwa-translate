"""Optical Character Recognition module for extracting text from manga.

Modular engine system with auto-best-result selection:
- PaddleOCR (priority 1): multilingual, bbox + rotation + confidence
- EasyOCR (priority 2): multilingual, bbox + confidence  
- Tesseract (priority 3): multilingual, per-block data

Supports 12 languages: Japanese, Chinese, Korean, English, Russian,
Uzbek, Spanish, French, Arabic, Thai, Vietnamese.
"""

from backend.ocr.service import OCRService, OCRResult
from backend.ocr.engines import EngineResult, LANGUAGE_MAP

__all__ = [
    "OCRService",
    "OCRResult",
    "EngineResult",
    "LANGUAGE_MAP",
]
