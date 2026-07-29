"""Speech bubble detection module for manga and manhwa pages.

Supports YOLO, SAM2, and GroundingDINO with precise polygon output.
Detects: speech bubbles, thought bubbles, narration boxes, sound effects,
signs, titles, and posters.
"""

from backend.detector.service import DetectionService, DetectionPageResult
from backend.detector.engines import (
    BUBBLE_TYPES,
    DetectedRegion,
    YOLODetector,
    SAM2Detector,
    GroundingDINODetector,
    _polygon_iou,
    _sort_manga_reading_order,
)

__all__ = [
    "DetectionService",
    "DetectionPageResult",
    "DetectedRegion",
    "YOLODetector",
    "SAM2Detector",
    "GroundingDINODetector",
    "BUBBLE_TYPES",
    "_polygon_iou",
    "_sort_manga_reading_order",
]
