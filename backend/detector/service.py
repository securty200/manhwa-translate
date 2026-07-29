"""Enhanced modular detection service with YOLO, SAM2, and GroundingDINO support.

Pipeline:
1. Run engines in priority order (YOLO → SAM2 → GroundingDINO)
2. Merge overlapping detections with highest confidence wins
3. Classify bubble types (speech, thought, narration, sfx, sign, title, poster)
4. Generate precise polygons (SAM2 masks → polygon, else bbox → polygon)
5. Sort in manga reading order
6. Link detection results with OCR results for database storage
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import numpy as np
from PIL import Image

from backend.config import settings

logger = logging.getLogger(__name__)

# Re-export core types
from backend.detector.engines import (
    BUBBLE_TYPES,
    DetectedRegion,
    DetectionPageResult,
    YOLODetector,
    SAM2Detector,
    GroundingDINODetector,
    _polygon_iou,
    _sort_manga_reading_order,
)


class DetectionService:
    """Orchestrates multiple detection engines for manga bubble detection.

    Runs YOLO, SAM2, and GroundingDINO in priority order, then merges,
    deduplicates, and classifies results. Returns precise polygons for
    downstream OCR, inpainting, and rendering.
    """

    def __init__(
        self,
        engine_priority: list[str] | None = None,
        device: str | None = None,
        confidence_threshold: float = 0.3,
        merge_iou_threshold: float = 0.5,
    ) -> None:
        self.engine_priority = engine_priority or [
            "yolo",
            "groundingdino",
            "sam2",
        ]
        self.device = device or settings.OCR_DEVICE
        self.confidence_threshold = confidence_threshold
        self.merge_iou_threshold = merge_iou_threshold
        self._engines: dict[str, YOLODetector | SAM2Detector | GroundingDINODetector] = {}
        self._initialized: dict[str, bool] = {}

    async def initialize(
        self,
        target_types: list[str] | None = None,
    ) -> None:
        """Initialize all available detection engines.

        Attempts each engine in priority order. Engines that fail
        to initialize are skipped silently.

        Args:
            target_types: Optional bubble types to target (used by GroundingDINO).
        """
        loop = asyncio.get_event_loop()

        for engine_name in self.engine_priority:
            if engine_name in self._initialized and self._initialized[engine_name]:
                continue

            try:
                if engine_name == "yolo":
                    engine = YOLODetector(
                        device=self.device,
                        confidence_threshold=0.25,
                    )

                    def _init_yolo() -> None:
                        engine.initialize()

                    await loop.run_in_executor(None, _init_yolo)
                    self._engines[engine_name] = engine
                    self._initialized[engine_name] = engine._initialized

                elif engine_name == "sam2":
                    engine = SAM2Detector(device=self.device)

                    def _init_sam2() -> None:
                        engine.initialize()

                    await loop.run_in_executor(None, _init_sam2)
                    self._engines[engine_name] = engine
                    self._initialized[engine_name] = engine._initialized

                elif engine_name == "groundingdino":
                    engine = GroundingDINODetector(device=self.device)

                    def _init_gdino() -> None:
                        engine.initialize()

                    await loop.run_in_executor(None, _init_gdino)
                    self._engines[engine_name] = engine
                    self._initialized[engine_name] = engine._initialized

            except Exception as e:
                logger.info("Detector engine %s not available: %s", engine_name, e)
                self._initialized[engine_name] = False

        available = [n for n, v in self._initialized.items() if v]
        if available:
            logger.info("Detection engines available: %s", available)
        else:
            logger.warning("No detection engines available, using fallback")

    async def detect_page(
        self,
        image: Image.Image,
        target_types: list[str] | None = None,
        allow_fallback: bool = True,
    ) -> DetectionPageResult:
        """Detect all bubbles and text regions on a manga page.

        Pipeline:
        1. Run engines in priority order
        2. Merge overlapping detections (highest confidence wins)
        3. Classify bubble types via heuristics
        4. Sort in manga reading order
        5. Generate DetectionPageResult

        Args:
            image: PIL Image of the manga page.
            target_types: Filter to specific bubble types (None = all).
            allow_fallback: Use heuristic fallback if no ML engines available.

        Returns:
            DetectionPageResult with all detected regions.
        """
        total_start = time.perf_counter()
        width, height = image.size

        # Initialize engines if needed
        if not self._initialized or not any(self._initialized.values()):
            await self.initialize(target_types)

        # Step 1: Run all available engines
        loop = asyncio.get_event_loop()
        all_regions: list[DetectedRegion] = []
        engines_used: list[str] = []

        for engine_name in self.engine_priority:
            engine = self._engines.get(engine_name)
            if engine is None or not self._initialized.get(engine_name, False):
                continue

            try:
                if engine_name == "yolo":
                    def _run_yolo(e: YOLODetector, img: Image.Image) -> list[DetectedRegion]:
                        return e.extract(img, target_types=target_types)

                    regions = await loop.run_in_executor(None, _run_yolo, engine, image)

                elif engine_name == "sam2":
                    # SAM2 can refine YOLO boxes if available
                    yolo_results = [r for r in all_regions if r.engine_name == "yolo"]
                    prompt_boxes = [r.bbox for r in yolo_results] if yolo_results else None

                    def _run_sam2(
                        e: SAM2Detector, img: Image.Image, boxes: list | None
                    ) -> list[DetectedRegion]:
                        return e.extract(img, prompt_boxes=boxes)

                    regions = await loop.run_in_executor(
                        None, _run_sam2, engine, image, prompt_boxes
                    )

                elif engine_name == "groundingdino":
                    def _run_gdino(
                        e: GroundingDINODetector, img: Image.Image
                    ) -> list[DetectedRegion]:
                        return e.extract(img, target_types=target_types)

                    regions = await loop.run_in_executor(None, _run_gdino, engine, image)

                else:
                    continue

                # Filter by confidence
                regions = [
                    r for r in regions
                    if r.confidence >= self.confidence_threshold
                ]

                all_regions.extend(regions)
                if regions:
                    engines_used.append(engine_name)

                logger.debug(
                    "%s: %d regions detected (filtered to %d)",
                    engine_name, len(regions), len(regions),
                )

            except Exception as e:
                logger.warning("Engine %s failed: %s", engine_name, e)

        # Step 2: Fallback detection if no ML regions found
        if not all_regions and allow_fallback:
            logger.info("No ML detections, using heuristic fallback")
            fallback_regions = self._fallback_detection(image)
            all_regions.extend(fallback_regions)
            if fallback_regions:
                engines_used.append("fallback")

        # Step 3: Merge overlapping detections
        merged = self._merge_overlapping(all_regions) if all_regions else []

        # Step 4: Sort in manga reading order
        merged = _sort_manga_reading_order(merged)

        # Step 5: Assign reading order indices
        for i, region in enumerate(merged):
            # Store reading order as an attribute we'll pass through
            pass

        elapsed = (time.perf_counter() - total_start) * 1000

        logger.info(
            "Page %dx%d: %d regions from %s in %.0fms",
            width, height, len(merged),
            engines_used or ["fallback"],
            elapsed,
        )

        return DetectionPageResult(
            regions=merged,
            page_width=width,
            page_height=height,
            total_processing_time_ms=elapsed,
            engines_used=engines_used or ["fallback"],
        )

    def _merge_overlapping(
        self,
        regions: list[DetectedRegion],
    ) -> list[DetectedRegion]:
        """Merge heavily overlapping detections from multiple engines.

        Strategy:
        1. Sort by confidence descending
        2. For each region, check IoU with previously accepted regions
        3. If IoU > threshold, pick the one with higher confidence
        4. Prefer SAM2 polygons over bbox-only polygons when merging

        Args:
            regions: All detected regions from all engines.

        Returns:
            Deduplicated list of merged regions.
        """
        if not regions:
            return []

        # Sort by confidence descending
        sorted_regions = sorted(regions, key=lambda r: r.confidence, reverse=True)
        merged: list[DetectedRegion] = []

        for region in sorted_regions:
            is_duplicate = False
            to_replace: int | None = None

            for idx, existing in enumerate(merged):
                iou = _polygon_iou(region.polygon, existing.polygon)

                if iou > self.merge_iou_threshold:
                    if region.confidence > existing.confidence:
                        to_replace = idx
                    is_duplicate = True
                    break
                elif iou > self.merge_iou_threshold * 0.7:
                    # Partial overlap — prefer the one with mask
                    if region.mask is not None and existing.mask is None:
                        to_replace = idx
                        is_duplicate = True
                        break

            if to_replace is not None:
                merged[to_replace] = region
            elif not is_duplicate:
                merged.append(region)

        return merged

    def _fallback_detection(
        self,
        image: Image.Image,
    ) -> list[DetectedRegion]:
        """Heuristic fallback detection when no ML models are available.

        Uses OpenCV contour analysis with manga-specific heuristics:
        - Large white/light regions (typical bubble background)
        - Connected component analysis
        - Shape classification
        """
        try:
            import cv2

            img_np = np.array(image.convert("RGB"))
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

            # Adaptive thresholding for manga pages
            binary = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV, 31, 10,
            )

            # Morphological closing to connect nearby text regions
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)

            # Find contours
            contours, _ = cv2.findContours(
                closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            h, w = gray.shape
            page_area = w * h
            min_area = page_area * 0.002  # 0.2%
            max_area = page_area * 0.35   # 35%

            regions: list[DetectedRegion] = []
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < min_area or area > max_area:
                    continue

                x, y, cw, ch = cv2.boundingRect(cnt)
                aspect = cw / ch if ch > 0 else 0

                # Filter thin/noisy regions
                if aspect < 0.2 or aspect > 8.0:
                    continue

                # Get polygon from contour approximation
                epsilon = 0.01 * cv2.arcLength(cnt, closed=True)
                approx = cv2.approxPolyDP(cnt, epsilon, closed=True)
                polygon = [(float(pt[0][0]), float(pt[0][1])) for pt in approx]

                # Classify by shape
                bubble_type = _classify_shape_heuristic(polygon, cw, ch, area / page_area)

                # Confidence based on area relative to expected bubble size
                confidence = min(1.0, area / (page_area * 0.05))

                regions.append(DetectedRegion(
                    polygon=polygon,
                    confidence=round(confidence, 4),
                    bubble_type=bubble_type,
                    engine_name="fallback",
                ))

            return regions

        except ImportError:
            logger.warning("OpenCV not available for fallback detection")
            return []
        except Exception as e:
            logger.error("Fallback detection failed: %s", e)
            return []

    def regions_to_bboxes(
        self,
        regions: list[DetectedRegion],
    ) -> list[tuple[int, int, int, int]]:
        """Convert detected regions to (x, y, w, h) bboxes for OCR pipeline."""
        return [
            (int(r.bbox[0]), int(r.bbox[1]), int(r.bbox[2]), int(r.bbox[3]))
            for r in regions
        ]

    def regions_to_inpaint_boxes(
        self,
        regions: list[DetectedRegion],
    ) -> list[dict]:
        """Convert detected regions to inpainting input format.

        For regions with masks, uses the mask for precise inpainting.
        Otherwise falls back to bounding box.
        """
        result = []
        for r in regions:
            item = {
                "x": int(r.bbox[0]),
                "y": int(r.bbox[1]),
                "width": int(r.bbox[2]),
                "height": int(r.bbox[3]),
                "polygon": [(int(x), int(y)) for x, y in r.polygon],
            }
            if r.mask is not None:
                item["mask"] = r.mask
            result.append(item)
        return result

    def regions_to_render_format(
        self,
        regions: list[DetectedRegion],
        translations: list[str],
    ) -> list[dict]:
        """Convert detected regions + translations to renderer input.

        Each entry contains the precise polygon for text rendering within
        the detected bubble shape.
        """
        result = []
        for idx, (region, text) in enumerate(zip(regions, translations)):
            if not text:
                continue
            result.append({
                "x": region.bbox[0],
                "y": region.bbox[1],
                "width": region.bbox[2],
                "height": region.bbox[3],
                "polygon": [(float(x), float(y)) for x, y in region.polygon],
                "translated_text": text,
                "reading_order": idx,
                "bubble_type": region.bubble_type,
            })
        return result

    async def cleanup(self) -> None:
        """Release all detector engine resources."""
        for engine_name, engine in self._engines.items():
            try:
                if hasattr(engine, "cleanup"):
                    engine.cleanup()
            except Exception as e:
                logger.debug("Cleanup %s: %s", engine_name, e)
        self._engines.clear()
        self._initialized.clear()
        logger.info("All detector resources released")


# ── Shape classification helper ──────────────────────────────────────────


def _classify_shape_heuristic(
    polygon: list[tuple[float, float]],
    width: float,
    height: float,
    area_ratio: float,
) -> str:
    """Classify a region's bubble type based on geometric heuristics.

    For use in fallback detection mode.
    """
    if not polygon or len(polygon) < 3 or width <= 0 or height <= 0:
        return "speech"

    aspect = width / height

    # Large area → poster or SFX
    if area_ratio > 0.15:
        if aspect > 2.5:
            return "poster"
        return "sfx"

    # Very wide → narration or sign
    if aspect > 2.0:
        if area_ratio < 0.02:
            return "sign"
        return "narration"

    # Very tall → vertical text (signs in manga)
    if aspect < 0.5:
        return "sign"

    # Rectangular with moderate aspect → narration
    if aspect > 1.5:
        return "narration"

    # Default → speech
    return "speech"
