"""Modular detector engines for speech bubbles, thought bubbles, narration,
sound effects, signs, titles, and posters — optimized for manga/manhwa pages.

Supports:
- YOLO (ultralytics) — fast bounding box + class detection
- SAM2 (segment-anything-2) — precise polygon segmentation
- GroundingDINO — zero-shot detection with text prompts
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from PIL import Image

from backend.config import settings

logger = logging.getLogger(__name__)

# ── Bubble type categories ───────────────────────────────────────────────

BUBBLE_TYPES = [
    "speech",    # Standard speech bubble (tail pointing to speaker)
    "thought",   # Thought/cloud bubble (dotted outline)
    "narration", # Narration box (rectangular, usually at top/bottom)
    "sfx",       # Sound effect text (onomatopoeia, action lines)
    "sign",      # Sign/placard text
    "title",     # Chapter/page title text
    "poster",    # Poster/banner text (large display text)
]

# YOLO class-to-type mapping (fine-grained for manga)
YOLO_CLASS_MAP: dict[int, str] = {
    0: "speech",
    1: "thought",
    2: "narration",
    3: "sfx",
    4: "sign",
    5: "title",
    6: "poster",
}

# GroundingDINO prompt templates for each bubble type
GROUNDING_PROMPTS: dict[str, str] = {
    "speech": "speech bubble . text bubble . dialogue balloon",
    "thought": "thought bubble . cloud bubble . thinking bubble",
    "narration": "narration box . caption box . text box . panel text",
    "sfx": "sound effect . onomatopoeia . action text . sfx",
    "sign": "sign . placard . billboard . signboard",
    "title": "title text . chapter title . heading",
    "poster": "poster . banner . large display text",
}


@dataclass
class DetectedRegion:
    """A detected region (bubble, text box, etc.) with precise polygon.

    Attributes:
        polygon: Ordered list of (x, y) vertices defining the precise region.
        bbox: (x, y, w, h) bounding box computed from polygon extremes.
        confidence: Detection confidence score (0.0–1.0).
        bubble_type: Category label (speech, thought, narration, sfx, ...).
        engine_name: Name of the engine that detected this region.
        mask: Optional binary pixel mask from SAM2 segmentation.
        text_prompt: Optional text prompt used for GroundingDINO.
    """

    polygon: list[tuple[float, float]] = field(default_factory=list)
    confidence: float = 0.0
    bubble_type: str = "speech"
    engine_name: str = ""
    mask: Optional[np.ndarray] = None  # Binary mask for precise inpainting
    text_prompt: str = ""
    reading_order: int = 0
    processing_time_ms: float = 0.0

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        """Compute (x, y, w, h) bounding box from polygon vertices."""
        if not self.polygon:
            return (0.0, 0.0, 0.0, 0.0)
        xs = [p[0] for p in self.polygon]
        ys = [p[1] for p in self.polygon]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        return (x_min, y_min, x_max - x_min, y_max - y_min)

    @property
    def area(self) -> float:
        """Compute polygon area using the shoelace formula."""
        if len(self.polygon) < 3:
            return 0.0
        n = len(self.polygon)
        area = 0.0
        for i in range(n):
            x1, y1 = self.polygon[i]
            x2, y2 = self.polygon[(i + 1) % n]
            area += x1 * y2 - x2 * y1
        return abs(area) / 2.0

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict."""
        return {
            "polygon": [(float(x), float(y)) for x, y in self.polygon],
            "bbox": list(self.bbox),
            "confidence": self.confidence,
            "bubble_type": self.bubble_type,
            "engine_name": self.engine_name,
            "area": self.area,
            "text_prompt": self.text_prompt,
            "processing_time_ms": self.processing_time_ms,
        }


@dataclass
class DetectionPageResult:
    """Result of detecting all regions on a single page."""

    regions: list[DetectedRegion] = field(default_factory=list)
    page_width: int = 0
    page_height: int = 0
    total_processing_time_ms: float = 0.0
    engines_used: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "page_width": self.page_width,
            "page_height": self.page_height,
            "total_processing_time_ms": self.total_processing_time_ms,
            "engines_used": self.engines_used,
            "regions": [r.to_dict() for r in self.regions],
            "region_count": len(self.regions),
        }


# ── Utility functions ────────────────────────────────────────────────────


def _polygon_from_bbox(
    x: float, y: float, w: float, h: float,
) -> list[tuple[float, float]]:
    """Convert a bounding box to a 4-point rectangular polygon."""
    return [
        (x, y),
        (x + w, y),
        (x + w, y + h),
        (x, y + h),
    ]


def _polygon_iou(
    poly1: list[tuple[float, float]],
    poly2: list[tuple[float, float]],
) -> float:
    """Compute IoU between two polygons using shapely if available, else fallback."""
    try:
        from shapely.geometry import Polygon as ShapelyPolygon
        p1 = ShapelyPolygon(poly1)
        p2 = ShapelyPolygon(poly2)
        if not p1.is_valid or not p2.is_valid:
            return 0.0
        intersection = p1.intersection(p2).area
        union = p1.union(p2).area
        return intersection / union if union > 0 else 0.0
    except ImportError:
        return _bbox_iou_fallback(poly1, poly2)


def _bbox_iou_fallback(
    poly1: list[tuple[float, float]],
    poly2: list[tuple[float, float]],
) -> float:
    """Fallback IoU using bounding boxes when shapely is unavailable."""
    if not poly1 or not poly2:
        return 0.0
    xs1 = [p[0] for p in poly1]
    ys1 = [p[1] for p in poly1]
    xs2 = [p[0] for p in poly2]
    ys2 = [p[1] for p in poly2]

    ax1, ay1 = min(xs1), min(ys1)
    ax2, ay2 = max(xs1), max(ys1)
    bx1, by1 = min(xs2), min(ys2)
    bx2, by2 = max(xs2), max(ys2)

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    intersection = (ix2 - ix1) * (iy2 - iy1)
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


def _sort_manga_reading_order(
    regions: list[DetectedRegion],
) -> list[DetectedRegion]:
    """Sort regions in manga reading order: right-to-left, top-to-bottom.

    Manga/manhwa pages are read from right to left, top to bottom.
    For vertical text (common in manga), we group by column first.
    """
    if not regions:
        return regions

    # First pass: detect if page has wide panels (single-column) or narrow (multi-column)
    # Group by approximate column position
    def sort_key(region: DetectedRegion) -> tuple[float, float]:
        _, y, w, _ = region.bbox
        x_center = region.bbox[0] + w / 2
        # Manga reads right-to-left, so negate x for column grouping
        col = -x_center
        row = y
        return (col, row)

    sorted_regions = sorted(regions, key=sort_key)

    # Assign reading order
    for i, region in enumerate(sorted_regions):
        region.reading_order = i

    return sorted_regions


# ═══════════════════════════════════════════════════════════════════════════
# Engine 1: YOLO (Ultralytics)
# ═══════════════════════════════════════════════════════════════════════════


class YOLODetector:
    """YOLO-based bubble detector using ultralytics.

    Detects bubbles and text regions with class labels for:
    speech, thought, narration, sfx, sign, title, poster.
    Returns bounding boxes converted to polygons.
    """

    def __init__(
        self,
        model_path: str | None = None,
        device: str = "cpu",
        confidence_threshold: float = 0.25,
        iou_threshold: float = 0.45,
    ) -> None:
        self.model_path = model_path or str(
            settings.MODELS_DIR / "bubble_detector.pt"
        )
        self.device = device
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self._model = None
        self._initialized = False

    def initialize(self) -> None:
        """Load the YOLO model."""
        if self._initialized:
            return

        try:
            from ultralytics import YOLO
            self._model = YOLO(self.model_path)
            self._initialized = True
            logger.info("YOLO detector loaded from: %s", self.model_path)
        except ImportError:
            logger.warning("ultralytics not installed. YOLO detector unavailable.")
            self._model = None
            self._initialized = False
        except Exception as e:
            logger.warning("Failed to load YOLO model: %s", e)
            self._model = None
            self._initialized = False

    def extract(
        self,
        image: Image.Image,
        target_types: list[str] | None = None,
    ) -> list[DetectedRegion]:
        """Detect bubbles and text regions on a page.

        Args:
            image: PIL Image of the manga page.
            target_types: Filter to specific bubble types (None = all).

        Returns:
            List of DetectedRegion with rectangular polygons from YOLO boxes.
        """
        start = time.perf_counter()
        if not self._initialized or self._model is None:
            return []

        try:
            results = self._model(
                np.array(image),
                conf=self.confidence_threshold,
                iou=self.iou_threshold,
                verbose=False,
                device=self.device,
            )

            regions: list[DetectedRegion] = []
            for result in results:
                boxes = result.boxes
                if boxes is None or len(boxes) == 0:
                    continue

                for i in range(len(boxes)):
                    conf = float(boxes.conf[i])
                    if conf < self.confidence_threshold:
                        continue

                    cls_id = int(boxes.cls[i]) if boxes.cls is not None else 0
                    bubble_type = YOLO_CLASS_MAP.get(cls_id, "speech")

                    if target_types and bubble_type not in target_types:
                        continue

                    # YOLO returns xyxy format
                    xyxy = boxes.xyxy[i].cpu().numpy()
                    x1, y1, x2, y2 = float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3])

                    polygon = _polygon_from_bbox(x1, y1, x2 - x1, y2 - y1)

                    # For SFX, try to get a more precise mask if available
                    mask = None
                    if result.masks is not None and i < len(result.masks):
                        try:
                            mask_np = result.masks.data[i].cpu().numpy()
                            mask = (mask_np > 0.5).astype(np.uint8)
                            # Convert mask to polygon
                            mask_poly = _mask_to_polygon(mask)
                            if mask_poly and len(mask_poly) >= 3:
                                polygon = mask_poly
                        except Exception:
                            pass

                    elapsed = (time.perf_counter() - start) * 1000
                    regions.append(DetectedRegion(
                        polygon=polygon,
                        confidence=conf,
                        bubble_type=bubble_type,
                        engine_name="yolo",
                        mask=mask,
                        processing_time_ms=elapsed,
                    ))

            return regions

        except Exception as e:
            logger.error("YOLO detection failed: %s", e)
            return []

    def cleanup(self) -> None:
        """Release model resources."""
        self._model = None
        self._initialized = False
        logger.info("YOLO detector resources released")


# ═══════════════════════════════════════════════════════════════════════════
# Engine 2: SAM2 (Segment Anything Model 2)
# ═══════════════════════════════════════════════════════════════════════════


class SAM2Detector:
    """SAM2-based segmentation for precise bubble polygons.

    SAM2 can be used in two modes:
    1. Automatic mask generation — segment everything, classify with heuristics
    2. Prompt-based — given boxes/points from YOLO, refine to precise polygons

    For manga optimization:
    - Prefers larger connected regions (bubbles tend to be 2-40% of page area)
    - Filters long/straight regions (likely panel borders, not bubbles)
    - Classifies by shape analysis (round=speech/thought, rect=narration/sign)
    """

    def __init__(
        self,
        model_type: str = "sam2.1_tiny",
        device: str = "cpu",
    ) -> None:
        self.model_type = model_type
        self.device = device
        self._predictor = None
        self._initialized = False

    def initialize(self) -> None:
        """Load the SAM2 model."""
        if self._initialized:
            return

        try:
            from sam2.build_sam import build_sam2
            from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator
            from sam2.sam2_image_predictor import SAM2ImagePredictor

            # Try to find the model config
            import sam2
            sam2_dir = sam2.__path__[0]
            config_path = f"{sam2_dir}/configs/sam2.1/sam2.1_tiny.yaml"

            model = build_sam2(config_path, None, device=self.device)
            self._predictor = SAM2AutomaticMaskGenerator(
                model,
                points_per_side=32,
                pred_iou_thresh=0.7,
                stability_score_thresh=0.8,
                crop_n_layers=1,
                box_nms_thresh=0.7,
                crop_n_points_downscale_factor=2,
                min_mask_region_area=500,  # Filter tiny noise regions
            )
            self._image_predictor = SAM2ImagePredictor(model)
            self._initialized = True
            logger.info("SAM2 detector initialized (model: %s, device: %s)",
                        self.model_type, self.device)
        except ImportError:
            logger.warning(
                "sam2 not installed. SAM2 detector unavailable. "
                "Install with: pip install sam2"
            )
            self._initialized = False
        except Exception as e:
            logger.warning("Failed to initialize SAM2: %s", e)
            self._initialized = False

    def extract(
        self,
        image: Image.Image,
        prompt_boxes: list[tuple[float, float, float, float]] | None = None,
    ) -> list[DetectedRegion]:
        """Detect regions using SAM2.

        Args:
            image: PIL Image of the manga page.
            prompt_boxes: Optional (x, y, w, h) boxes from YOLO to refine.

        Returns:
            List of DetectedRegion with precise polygons and masks.
        """
        start = time.perf_counter()

        if not self._initialized or self._predictor is None:
            return []

        try:
            img_np = np.array(image.convert("RGB"))

            if prompt_boxes:
                # Prompt-based mode: use boxes from YOLO to segment
                regions = self._segment_with_boxes(img_np, prompt_boxes)
            else:
                # Automatic mode: segment everything
                masks = self._predictor.generate(img_np)
                regions = self._masks_to_regions(masks, img_np.shape[1], img_np.shape[0])

            elapsed = (time.perf_counter() - start) * 1000
            for r in regions:
                r.processing_time_ms = elapsed
                if not r.engine_name:
                    r.engine_name = "sam2"

            return regions

        except Exception as e:
            logger.error("SAM2 detection failed: %s", e)
            return []

    def _segment_with_boxes(
        self,
        image: np.ndarray,
        boxes: list[tuple[float, float, float, float]],
    ) -> list[DetectedRegion]:
        """Segment specific regions defined by bounding boxes."""
        if self._image_predictor is None:
            return []

        self._image_predictor.set_image(image)
        regions: list[DetectedRegion] = []

        for bbox in boxes:
            x, y, w, h = bbox
            # SAM2 expects xyxy format
            input_box = np.array([x, y, x + w, y + h])

            masks, scores, _ = self._image_predictor.predict(
                box=input_box[None, :],
                multimask_output=True,
            )

            if len(masks) == 0:
                continue

            # Pick the best mask
            best_idx = int(np.argmax(scores))
            mask = masks[best_idx]
            score = float(scores[best_idx])

            if score < 0.5:
                continue

            # Convert mask to polygon
            polygon = _mask_to_polygon(mask)
            if not polygon or len(polygon) < 3:
                polygon = _polygon_from_bbox(x, y, w, h)

            regions.append(DetectedRegion(
                polygon=polygon,
                confidence=score,
                bubble_type="speech",
                engine_name="sam2",
                mask=(mask > 0.5).astype(np.uint8),
            ))

        return regions

    def _masks_to_regions(
        self,
        masks: list[dict],
        img_width: int,
        img_height: int,
    ) -> list[DetectedRegion]:
        """Convert SAM2 automatic mask output to DetectedRegions.

        Uses manga-specific heuristics to classify and filter masks.
        """
        regions: list[DetectedRegion] = []
        page_area = img_width * img_height

        for mask_data in masks:
            mask = mask_data.get("segmentation", None)
            if mask is None:
                continue

            # Convert mask to polygon
            polygon = _mask_to_polygon(mask)
            if not polygon or len(polygon) < 3:
                continue

            # Compute area ratio
            mask_area = mask_data.get("area", 0)
            area_ratio = mask_area / page_area if page_area > 0 else 0

            # Manga bubble area heuristic: 0.2% - 40% of page
            if area_ratio < 0.002 or area_ratio > 0.40:
                continue

            bbox = mask_data.get("bbox", (0, 0, 0, 0))
            bw, bh = bbox[2], bbox[3]

            # Filter very thin regions (likely panel borders)
            if bw > 0 and bh > 0:
                aspect = bw / bh
                if aspect < 0.15 or aspect > 6.0:
                    continue

            # Classify by shape: roundness and aspect ratio
            bubble_type = _classify_bubble_shape(polygon, bw, bh, area_ratio)

            confidence = mask_data.get("predicted_iou", 0.0)

            regions.append(DetectedRegion(
                polygon=polygon,
                confidence=float(confidence),
                bubble_type=bubble_type,
                engine_name="sam2",
                mask=(mask > 0.5).astype(np.uint8),
            ))

        return regions

    def cleanup(self) -> None:
        """Release model resources."""
        self._predictor = None
        self._image_predictor = None
        self._initialized = False
        logger.info("SAM2 detector resources released")


# ═══════════════════════════════════════════════════════════════════════════
# Engine 3: GroundingDINO
# ═══════════════════════════════════════════════════════════════════════════


class GroundingDINODetector:
    """GroundingDINO-based zero-shot detection for text regions.

    Can detect arbitrary bubble types by text prompts:
    - "speech bubble . text bubble"
    - "narration box . caption box"
    - "sound effect . onomatopoeia"
    - "sign . placard"
    - etc.

    Optimized for manga:
    - Uses specific manga/manhwa terminology in prompts
    - Filters small/noisy detections
    - Aggregates overlapping detections
    """

    def __init__(
        self,
        model_id: str = "IDEA-Research/grounding-dino-tiny",
        device: str = "cpu",
        box_threshold: float = 0.25,
        text_threshold: float = 0.20,
    ) -> None:
        self.model_id = model_id
        self.device = device
        self.box_threshold = box_threshold
        self.text_threshold = text_threshold
        self._processor = None
        self._model = None
        self._initialized = False

    def initialize(self) -> None:
        """Load the GroundingDINO model."""
        if self._initialized:
            return

        try:
            import torch
            from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor

            logger.info("Loading GroundingDINO model: %s", self.model_id)
            self._processor = AutoProcessor.from_pretrained(self.model_id)
            self._model = AutoModelForZeroShotObjectDetection.from_pretrained(
                self.model_id
            ).to(self.device)
            self._model.eval()
            self._initialized = True
            logger.info("GroundingDINO initialized on device: %s", self.device)
        except ImportError:
            logger.warning(
                "transformers or torch not installed. "
                "GroundingDINO detector unavailable."
            )
            self._initialized = False
        except Exception as e:
            logger.warning("Failed to initialize GroundingDINO: %s", e)
            self._initialized = False

    def extract(
        self,
        image: Image.Image,
        target_types: list[str] | None = None,
    ) -> list[DetectedRegion]:
        """Detect regions using GroundingDINO.

        Builds a combined text prompt from target types and runs detection.

        Args:
            image: PIL Image of the manga page.
            target_types: Bubble types to detect (None = all).

        Returns:
            List of DetectedRegion with polygons from bounding boxes.
        """
        start = time.perf_counter()
        if not self._initialized or self._model is None or self._processor is None:
            return []

        try:
            types_to_detect = target_types or BUBBLE_TYPES
            prompts = [GROUNDING_PROMPTS.get(t, t) for t in types_to_detect]
            text_prompt = " . ".join(prompts)

            import torch
            inputs = self._processor(
                images=image.convert("RGB"),
                text=text_prompt,
                return_tensors="pt",
            ).to(self.device)

            with torch.no_grad():
                outputs = self._model(**inputs)

            # Post-process results
            w, h = image.size
            results = self._processor.post_process_grounded_object_detection(
                outputs,
                inputs.input_ids,
                box_threshold=self.box_threshold,
                text_threshold=self.text_threshold,
                target_sizes=[(h, w)],
            )[0]

            regions: list[DetectedRegion] = []

            boxes = results.get("boxes", [])
            scores = results.get("scores", [])
            labels = results.get("labels", [])

            for i in range(len(boxes)):
                if i >= len(scores):
                    break

                score = float(scores[i])
                if score < self.box_threshold:
                    continue

                box = boxes[i].cpu().numpy()
                # boxes are in xyxy format
                x1, y1, x2, y2 = float(box[0]), float(box[1]), float(box[2]), float(box[3])
                polygon = _polygon_from_bbox(x1, y1, x2 - x1, y2 - y1)

                # Determine bubble type from label
                label = labels[i] if i < len(labels) else ""
                bubble_type = _map_grounding_label_to_type(label, types_to_detect)

                elapsed = (time.perf_counter() - start) * 1000
                regions.append(DetectedRegion(
                    polygon=polygon,
                    confidence=score,
                    bubble_type=bubble_type,
                    engine_name="groundingdino",
                    text_prompt=str(label),
                    processing_time_ms=elapsed,
                ))

            return regions

        except Exception as e:
            logger.error("GroundingDINO detection failed: %s", e)
            return []

    def cleanup(self) -> None:
        """Release model resources."""
        self._model = None
        self._processor = None
        self._initialized = False
        logger.info("GroundingDINO detector resources released")


# ── Helper functions ─────────────────────────────────────────────────────


def _mask_to_polygon(
    mask: np.ndarray,
    min_vertices: int = 3,
    max_vertices: int = 128,
    epsilon_factor: float = 0.002,
) -> list[tuple[float, float]]:
    """Convert a binary mask to a simplified polygon.

    Uses OpenCV's findContours + approxPolyDP for simplification.
    Falls back to bounding box rectangle if OpenCV unavailable.

    Args:
        mask: Binary mask (2D numpy array, values 0/1 or bool).
        min_vertices: Minimum polygon vertices.
        max_vertices: Maximum vertices (simplify to this).
        epsilon_factor: Approximation accuracy factor (fraction of perimeter).

    Returns:
        List of (x, y) vertex tuples forming the polygon.
    """
    try:
        import cv2

        # Ensure binary uint8 mask
        if mask.dtype == bool:
            mask = mask.astype(np.uint8) * 255
        elif mask.dtype != np.uint8:
            mask = (mask > 0.5).astype(np.uint8) * 255

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return _mask_bbox_polygon(mask)

        # Pick the largest contour
        largest = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest)
        if area < 50:  # Too small
            return _mask_bbox_polygon(mask)

        # Simplify contour
        perimeter = cv2.arcLength(largest, closed=True)
        epsilon = epsilon_factor * perimeter
        approx = cv2.approxPolyDP(largest, epsilon, closed=True)

        vertices = [(float(pt[0][0]), float(pt[0][1])) for pt in approx]

        # Limit vertices
        if len(vertices) > max_vertices:
            step = len(vertices) / max_vertices
            vertices = [vertices[int(i * step)] for i in range(max_vertices)]

        if len(vertices) >= min_vertices:
            return vertices

        return _mask_bbox_polygon(mask)

    except ImportError:
        # OpenCV not available, use bounding box
        return _mask_bbox_polygon(mask)
    except Exception as e:
        logger.debug("Mask to polygon failed: %s", e)
        return _mask_bbox_polygon(mask)


def _mask_bbox_polygon(mask: np.ndarray) -> list[tuple[float, float]]:
    """Get a rectangular polygon from mask bounding box."""
    rows = np.any(mask, axis=1)
    cols = np.any(mask, axis=0)
    if not rows.any() or not cols.any():
        return []
    y_min, y_max = np.where(rows)[0][[0, -1]]
    x_min, x_max = np.where(cols)[0][[0, -1]]
    return _polygon_from_bbox(float(x_min), float(y_min),
                              float(x_max - x_min), float(y_max - y_min))


def _classify_bubble_shape(
    polygon: list[tuple[float, float]],
    width: float,
    height: float,
    area_ratio: float,
) -> str:
    """Classify a region's bubble type based on geometric heuristics.

    For manga-optimized detection:
    - Round/oval shapes with tails → speech or thought
    - Rectangular boxes → narration or sign
    - Large, irregular shapes → SFX
    - Large banner-like → poster
    """
    if not polygon or len(polygon) < 3 or width <= 0 or height <= 0:
        return "speech"

    aspect = width / height

    # Calculate roundness: 4π * area / perimeter² (1.0 = perfect circle)
    perimeter = _polygon_perimeter(polygon)
    poly_area = _polygon_area(polygon)
    roundness = (4 * math.pi * poly_area) / (perimeter * perimeter) if perimeter > 0 else 0

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

    # Very tall → could be vertical text (signs in manga)
    if aspect < 0.5:
        return "sign"

    # Round regions → speech or thought
    if roundness > 0.6:
        # Thought bubbles tend to have more irregular (cloud-like) shapes
        if 0.6 < roundness < 0.75:
            return "thought"
        return "speech"

    # Rectangular → narration
    if aspect > 1.5 and roundness < 0.3:
        return "narration"

    return "speech"


def _polygon_area(polygon: list[tuple[float, float]]) -> float:
    """Shoelace formula for polygon area."""
    if len(polygon) < 3:
        return 0.0
    area = 0.0
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def _polygon_perimeter(polygon: list[tuple[float, float]]) -> float:
    """Compute polygon perimeter."""
    if len(polygon) < 2:
        return 0.0
    perim = 0.0
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        perim += math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
    return perim


def _map_grounding_label_to_type(
    label: str,
    target_types: list[str],
) -> str:
    """Map a GroundingDINO text label to a standardized bubble type."""
    label_lower = label.lower().strip()

    # Direct match
    for bt in target_types:
        if bt in label_lower:
            return bt

    # Keyword matching
    if any(w in label_lower for w in ["speech", "dialogue", "balloon", "bubble"]):
        return "speech"
    if any(w in label_lower for w in ["thought", "cloud", "thinking"]):
        return "thought"
    if any(w in label_lower for w in ["narration", "caption", "box"]):
        return "narration"
    if any(w in label_lower for w in ["sound", "sfx", "onomatopoeia", "effect"]):
        return "sfx"
    if any(w in label_lower for w in ["sign", "placard", "billboard"]):
        return "sign"
    if any(w in label_lower for w in ["title", "heading"]):
        return "title"
    if any(w in label_lower for w in ["poster", "banner"]):
        return "poster"

    return "speech"
