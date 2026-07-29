"""Enhanced OCR service with modular engines and auto-best-result selection.

Supports:
- PaddleOCR (priority 1) — multilingual, bbox + rotation + confidence
- EasyOCR (priority 2) — multilingual, bbox + confidence
- Tesseract (priority 3) — multilingual, bbox + per-block data
- Auto-best-result: runs multiple engines, picks highest confidence per region
- Language auto-detection for 12 languages
- Rotation estimation
- Database storage
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

from backend.config import settings

logger = logging.getLogger(__name__)


# Re-export the engine dataclass and language map for convenience
from backend.ocr.engines import (
    EngineResult,
    LANGUAGE_MAP,
    PaddleOCREngine,
    EasyOCREngine,
    TesseractEngine,
    engine_for_language,
)


@dataclass
class OCRResult:
    """Enhanced OCR result with rich per-region metadata."""

    text: str
    confidence: float = 0.0
    language: str = "unknown"
    processing_time_ms: float = 0.0
    bbox: tuple[float, float, float, float] | None = None  # x, y, w, h
    rotation: float = 0.0
    engine_name: str = ""
    regions: list[EngineResult] = field(default_factory=list)
    all_engine_results: dict[str, list[EngineResult]] = field(default_factory=dict)
    raw_data: dict | None = None


class OCRService:
    """Optical Character Recognition with modular engine system.

    Runs PaddleOCR, EasyOCR, and Tesseract in priority order,
    then automatically selects the best result by confidence.
    Results include bounding boxes, confidence scores,
    detected language, and rotation.
    """

    def __init__(
        self,
        engine_priority: list[str] | None = None,
        device: str | None = None,
    ) -> None:
        self.engine_priority = engine_priority or ["paddleocr", "easyocr", "tesseract"]
        self.device = device or settings.OCR_DEVICE
        self._engines: dict[str, PaddleOCREngine | EasyOCREngine | TesseractEngine] = {}
        self._initialized: dict[str, bool] = {}

    async def initialize(self, languages: list[str] | None = None) -> None:
        """Initialize all available OCR engines.

        Attempts each engine in priority order. Engines that fail to
        initialize are skipped silently.
        """
        lang_list = languages or ["ja"]
        loop = asyncio.get_event_loop()

        for engine_name in self.engine_priority:
            if engine_name in self._initialized and self._initialized[engine_name]:
                continue

            try:
                if engine_name == "paddleocr":
                    engine = PaddleOCREngine(device=self.device)
                    # PaddleOCR multilingual setup
                    paddle_lang = "japan"
                    for lang in lang_list:
                        pl = engine_for_language("paddleocr", lang)
                        if pl != lang:
                            paddle_lang = pl
                            break

                    def _init_paddle(e: PaddleOCREngine, lang: str) -> None:
                        e.initialize(language=lang)

                    await loop.run_in_executor(None, _init_paddle, engine, paddle_lang)
                    self._engines[engine_name] = engine
                    self._initialized[engine_name] = engine._initialized

                elif engine_name == "easyocr":
                    engine = EasyOCREngine(device=self.device)
                    easy_langs = ["ja", "en"]
                    # Add any extra languages that EasyOCR supports
                    for lang in lang_list:
                        el = engine_for_language("easyocr", lang)
                        if el != lang and el not in easy_langs:
                            easy_langs.append(el)

                    def _init_easy(e: EasyOCREngine, langs: list[str]) -> None:
                        e.initialize(languages=langs)

                    await loop.run_in_executor(None, _init_easy, engine, easy_langs)
                    self._engines[engine_name] = engine
                    self._initialized[engine_name] = engine._initialized

                elif engine_name == "tesseract":
                    engine = TesseractEngine()

                    def _init_tess(e: TesseractEngine) -> None:
                        e.initialize()

                    await loop.run_in_executor(None, _init_tess, engine)
                    self._engines[engine_name] = engine
                    self._initialized[engine_name] = engine._initialized

            except Exception as e:
                logger.info("OCR engine %s not available: %s", engine_name, e)
                self._initialized[engine_name] = False

        available = [n for n, v in self._initialized.items() if v]
        if available:
            logger.info("OCR engines available: %s", available)
        else:
            logger.warning("No OCR engines available")

    async def extract_text(
        self,
        image: Image.Image,
        region: tuple[int, int, int, int] | None = None,
        languages: list[str] | None = None,
        auto_choose_best: bool = True,
        use_cache: bool = True,
    ) -> OCRResult:
        """Extract text from an image or image region using best available engines.

        Results are cached by image hash for performance.
        When auto_choose_best is True, runs all available engines and selects
        the best result per text region by confidence.

        Args:
            image: PIL Image to extract text from.
            region: Optional (x, y, w, h) region to crop before OCR.
            languages: Language codes to use for detection (ISO format).
            auto_choose_best: Run multiple engines and pick best results.
            use_cache: Whether to check/populate the OCR cache.

        Returns:
            OCRResult with extracted text and rich per-region metadata.
        """
        start_time = time.perf_counter()
        lang_list = languages or ["ja"]

        # Check cache (using resized thumbnail hash for memory efficiency)
        if use_cache:
            import hashlib
            # Use a small thumbnail to generate a cache key (avoids hashing 72MB raw pixels)
            thumb = image.copy()
            thumb.thumbnail((64, 64))
            thumb_bytes = thumb.tobytes()
            cache_key = f"ocr:{hashlib.md5(thumb_bytes).hexdigest()}:{region}:{':'.join(lang_list)}"
            from backend.services.cache_service import ocr_cache
            cached = await ocr_cache.get(cache_key)
            if cached is not None:
                logger.debug("OCR cache hit for region %s", region)
                return cached

        # Initialize engines if needed
        if not self._initialized or not any(self._initialized.values()):
            await self.initialize(lang_list)

        # Crop region if needed
        cropped = image
        if region:
            from backend.ocr.engines import _safe_crop
            cropped = _safe_crop(image, region)

        # Run available engines
        all_results: dict[str, list[EngineResult]] = {}
        loop = asyncio.get_event_loop()

        for engine_name in self.engine_priority:
            engine = self._engines.get(engine_name)
            if engine is None or not self._initialized.get(engine_name, False):
                continue

            try:
                engine_start = time.perf_counter()

                if engine_name == "paddleocr":
                    lang_for_engine = next(
                        (engine_for_language("paddleocr", l) for l in lang_list
                         if engine_for_language("paddleocr", l) != l),
                        "japan",
                    )

                    def _run_paddle(e: PaddleOCREngine, img: Image.Image,
                                    langs: list[str]) -> list[EngineResult]:
                        return e.extract(img, languages=langs)

                    results = await loop.run_in_executor(
                        None, _run_paddle, engine, cropped, [lang_for_engine]
                    )

                elif engine_name == "easyocr":
                    def _run_easy(e: EasyOCREngine, img: Image.Image) -> list[EngineResult]:
                        return e.extract(img)

                    results = await loop.run_in_executor(
                        None, _run_easy, engine, cropped
                    )

                elif engine_name == "tesseract":
                    tess_lang = next(
                        (engine_for_language("tesseract", l) for l in lang_list
                         if engine_for_language("tesseract", l) != l),
                        "jpn",
                    )

                    def _run_tess(e: TesseractEngine, img: Image.Image,
                                  lang: str) -> list[EngineResult]:
                        return e.extract(img, language=lang)

                    results = await loop.run_in_executor(
                        None, _run_tess, engine, cropped, tess_lang
                    )
                else:
                    continue

                # Log per-engine stats
                engine_time = (time.perf_counter() - engine_start) * 1000
                n_texts = sum(1 for r in results if r.text.strip())
                if results:
                    logger.debug(
                        "%s: %d regions, %d with text, %.0fms",
                        engine_name, len(results), n_texts, engine_time,
                    )

                all_results[engine_name] = results

            except Exception as e:
                logger.warning("Engine %s failed: %s", engine_name, e)
                all_results[engine_name] = []

        # Auto-choose best results
        best_regions = self._choose_best_results(all_results) if auto_choose_best else []
        best_engine = ""
        if all_results:
            engine_scores: dict[str, float] = {}
            for eng, res in all_results.items():
                score = sum(r.confidence for r in res if r.text.strip())
                engine_scores[eng] = score
            if engine_scores:
                best_engine = max(engine_scores, key=engine_scores.get)

        # Merge best regions into single text
        combined_text = "\n".join(r.text for r in best_regions if r.text.strip())
        avg_confidence = (
            sum(r.confidence for r in best_regions) / len(best_regions)
            if best_regions else 0.0
        )

        elapsed = (time.perf_counter() - start_time) * 1000

        result = OCRResult(
            text=combined_text.strip(),
            confidence=round(avg_confidence, 4),
            language=lang_list[0] if lang_list else "unknown",
            processing_time_ms=round(elapsed, 2),
            bbox=region,
            rotation=best_regions[0].rotation if best_regions else 0.0,
            engine_name=best_engine,
            regions=best_regions[:settings.MAX_OCR_REGIONS_PER_PAGE],
            all_engine_results=all_results,
        )

        # Cache the result
        if use_cache:
            try:
                from backend.services.cache_service import ocr_cache
                asyncio.create_task(
                    ocr_cache.set(cache_key, result, ttl=settings.CACHE_OCR_TTL)
                )
            except Exception:
                pass

        return result

    def _choose_best_results(
        self,
        all_results: dict[str, list[EngineResult]],
    ) -> list[EngineResult]:
        """Automatically choose the best OCR results across all engines.

        Strategy:
        1. Collect all text regions from all engines
        2. Group overlapping regions spatially
        3. For each group, pick the highest-confidence text
        4. Merge and deduplicate
        """
        if not all_results:
            return []

        # Flatten all results with engine source
        flat: list[EngineResult] = []
        for engine_name, results in all_results.items():
            for r in results:
                if r.text.strip():
                    r.engine_name = engine_name
                    flat.append(r)

        if not flat:
            return []

        # Simple dedup by checking overlapping bounding boxes
        # Sort by confidence descending
        flat.sort(key=lambda r: r.confidence, reverse=True)

        # Dedup by checking overlapping bounding boxes
        # Collect items to remove separately to avoid modifying list during iteration
        selected: list[EngineResult] = []
        for result in flat:
            is_duplicate = False
            to_replace: int | None = None
            for idx, existing in enumerate(selected):
                if _regions_overlap(result.bbox, existing.bbox, threshold=0.5):
                    if result.confidence > existing.confidence:
                        to_replace = idx
                    is_duplicate = True
                    break
            if to_replace is not None:
                selected[to_replace] = result
            elif not is_duplicate:
                selected.append(result)

        # Run language detection on each selected region's text
        for region in selected:
            if region.detected_language in ("unknown", "japan") and region.text.strip():
                detected = self.detect_language_from_text(region.text)
                if detected != "unknown":
                    region.detected_language = detected

        # Sort by page position (top-to-bottom, then left-to-right)
        selected.sort(key=lambda r: (r.bbox[1] if r.bbox else 0, r.bbox[0] if r.bbox else 0))

        return selected

    def detect_language_from_text(self, text: str) -> str:
        """Detect the language of a text string using character range analysis.

        Examines Unicode character ranges to identify the script used.
        For mixed CJK text: checks for Hiragana/Katakana first to distinguish
        Japanese from Chinese, since both share Kanji characters.

        Returns ISO language code or "unknown".
        """
        if not text.strip():
            return "unknown"

        # Check for Japanese-specific kana first (distinguishes ja from zh)
        has_hiragana = False
        has_katakana = False
        for ch in text:
            code = ord(ch)
            if 0x3040 <= code <= 0x309F:
                has_hiragana = True
            elif 0x30A0 <= code <= 0x30FF:
                has_katakana = True

        if has_hiragana or has_katakana:
            return "ja"

        # Count characters by Unicode range for other languages
        ranges: dict[str, tuple[int, int]] = {
            "zh": (0x4E00, 0x9FFF),   # CJK Unified (Chinese-only when no kana)
            "ko": (0xAC00, 0xD7AF),   # Hangul
            "ar": (0x0600, 0x06FF),   # Arabic
            "th": (0x0E00, 0x0E7F),   # Thai
            "vi": (0x1EA0, 0x1EFF),   # Vietnamese Latin extensions
            "ru": (0x0400, 0x04FF),   # Cyrillic
        }

        score: dict[str, int] = {}
        for ch in text:
            code = ord(ch)
            for lang, (start, end) in ranges.items():
                if start <= code <= end:
                    score[lang] = score.get(lang, 0) + 1

        if not score:
            # Default to English for basic Latin text
            if all(ord(c) < 0x02B0 for c in text if c.isalpha()):
                return "en"
            return "unknown"

        return max(score, key=score.get)

    async def extract_batch(
        self,
        image: Image.Image,
        regions: list[tuple[int, int, int, int]],
        languages: list[str] | None = None,
    ) -> list[OCRResult]:
        """Extract text from multiple regions on the same image.

        All regions share the same language configuration.
        Engines are initialized once for the batch.

        Args:
            image: PIL Image containing the regions.
            regions: List of (x, y, w, h) tuples.
            languages: Language codes (ISO format).

        Returns:
            List of OCRResult objects in the same order as regions.
        """
        if not self._initialized or not any(self._initialized.values()):
            await self.initialize(languages)

        results: list[OCRResult] = []
        for region in regions:
            result = await self.extract_text(
                image, region, languages=languages,
                auto_choose_best=True,
            )
            results.append(result)
        return results

    async def extract_page(
        self,
        page_image: Image.Image,
        bubble_regions: list[tuple[int, int, int, int]],
        languages: list[str] | None = None,
    ) -> list[OCRResult]:
        """Run OCR on all bubbles in a page.

        Shorthand for extract_batch with default settings.

        Args:
            page_image: PIL Image of the full page.
            bubble_regions: List of (x, y, w, h) bubble regions.
            languages: Language codes.

        Returns:
            List of OCRResult objects.
        """
        return await self.extract_batch(page_image, bubble_regions, languages)

    async def cleanup(self) -> None:
        """Release resources used by all OCR engines."""
        for engine_name, engine in self._engines.items():
            try:
                if hasattr(engine, 'cleanup'):
                    if asyncio.iscoroutinefunction(engine.cleanup):
                        await engine.cleanup()
                    else:
                        engine.cleanup()
            except Exception as e:
                logger.debug("Cleanup %s: %s", engine_name, e)
        self._engines.clear()
        self._initialized.clear()
        logger.info("All OCR resources released")


# ── Utility functions ────────────────────────────────────────────────────


def _regions_overlap(
    a: tuple[float, float, float, float] | None,
    b: tuple[float, float, float, float] | None,
    threshold: float = 0.3,
) -> bool:
    """Check if two bounding boxes overlap by more than threshold.

    Args:
        a, b: (x, y, w, h) bounding boxes.
        threshold: Minimum IoU to consider overlapping.

    Returns:
        True if boxes overlap significantly.
    """
    if a is None or b is None:
        return False

    ax, ay, aw, ah = a
    bx, by, bw, bh = b

    # Calculate intersection
    ix = max(ax, bx)
    iy = max(ay, by)
    ix2 = min(ax + aw, bx + bw)
    iy2 = min(ay + ah, by + bh)

    if ix2 <= ix or iy2 <= iy:
        return False

    intersection = (ix2 - ix) * (iy2 - iy)
    area_a = aw * ah
    area_b = bw * bh
    min_area = min(area_a, area_b)

    if min_area <= 0:
        return False

    iou = intersection / min_area
    return iou > threshold
