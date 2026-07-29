"""Individual OCR engine implementations with language support.

Each engine is a standalone module that can be initialized, used, and cleaned up
independently. Results are normalized into EngineResult dataclass.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from PIL import Image

from backend.config import settings

logger = logging.getLogger(__name__)


@dataclass
class EngineResult:
    """Normalized result from any OCR engine for a single text region."""

    text: str
    confidence: float = 0.0
    detected_language: str = "unknown"
    bbox: tuple[float, float, float, float] | None = None  # x, y, w, h
    rotation: float = 0.0  # degrees
    engine_name: str = ""
    processing_time_ms: float = 0.0
    raw_data: dict | None = None


# ── Language support mapping ─────────────────────────────────────────────

# Maps ISO codes to PaddleOCR language codes, EasyOCR codes, and Tesseract codes
LANGUAGE_MAP: dict[str, dict[str, str]] = {
    "ja": {"paddleocr": "japan", "easyocr": "ja", "tesseract": "jpn"},
    "zh": {"paddleocr": "ch", "easyocr": "ch_sim", "tesseract": "chi_sim"},
    "ko": {"paddleocr": "korean", "easyocr": "ko", "tesseract": "kor"},
    "en": {"paddleocr": "en", "easyocr": "en", "tesseract": "eng"},
    "ru": {"paddleocr": "ru", "easyocr": "ru", "tesseract": "rus"},
    "uz": {"paddleocr": "uz", "easyocr": "ch_sim", "tesseract": "uzb"},  # Uzbek fallback
    "es": {"paddleocr": "es", "easyocr": "es", "tesseract": "spa"},
    "fr": {"paddleocr": "fr", "easyocr": "fr", "tesseract": "fra"},
    "ar": {"paddleocr": "ar", "easyocr": "ar", "tesseract": "ara"},
    "th": {"paddleocr": "th", "easyocr": "th", "tesseract": "tha"},
    "vi": {"paddleocr": "vi", "easyocr": "vi", "tesseract": "vie"},
}

# Languages that PaddleOCR supports for auto-detection
PADDLE_MLANG = "japan,ch,korean,en,ru,es,fr,ar,th,vi"

# Tesseract PSM modes
TESSERACT_PSM = 6  # Assume uniform block of text
TESSERACT_OEM = 3  # Default OCR engine


def _safe_crop(image: Image.Image, region: tuple[int, int, int, int]) -> Image.Image:
    """Safely crop an image region with bounds checking."""
    x, y, w, h = region
    # Clamp to image bounds
    img_w, img_h = image.size
    x = max(0, min(x, img_w - 1))
    y = max(0, min(y, img_h - 1))
    w = min(w, img_w - x)
    h = min(h, img_h - y)
    if w <= 0 or h <= 0:
        return image
    return image.crop((x, y, x + w, y + h))


# ── PaddleOCR Engine ────────────────────────────────────────────────────


class PaddleOCREngine:
    """OCR engine using PaddleOCR with multilingual support."""

    def __init__(self, device: str | None = None) -> None:
        self.device = device or settings.OCR_DEVICE
        self._engine = None
        self._initialized = False

    def initialize(self, language: str = "japan") -> None:
        """Initialize PaddleOCR."""
        if self._initialized:
            return
        try:
            from paddleocr import PaddleOCR

            self._engine = PaddleOCR(
                use_angle_cls=True,
                lang=language,
                use_gpu=(self.device == "cuda"),
                show_log=False,
                det_db_thresh=0.3,
                det_db_box_thresh=0.5,
            )
            self._initialized = True
            logger.info("PaddleOCR initialized (lang=%s, device=%s)", language, self.device)
        except ImportError:
            logger.warning("paddleocr not installed")
            self._engine = None
        except Exception as e:
            logger.warning("PaddleOCR init failed: %s", e)
            self._engine = None

    def extract(self, image: Image.Image, languages: list[str] | None = None) -> list[EngineResult]:
        """Extract text using PaddleOCR.

        Returns one EngineResult per detected text region.
        """
        if self._engine is None:
            return []

        results: list[EngineResult] = []
        try:
            import numpy as np

            img_array = np.array(image.convert("RGB"))
            raw = self._engine.ocr(img_array, cls=True)

            if not raw or not raw[0]:
                return []

            for line in raw[0]:
                # line = [bbox, (text, confidence)]
                poly_points, (text, confidence) = line

                # Convert polygon to (x, y, w, h) bounding box
                xs = [p[0] for p in poly_points]
                ys = [p[1] for p in poly_points]
                x_min, x_max = min(xs), max(xs)
                y_min, y_max = min(ys), max(ys)

                # Estimate rotation from polygon
                rotation = _estimate_rotation(poly_points)

                # Detect language (PaddleOCR doesn't provide per-line language,
                # so we use the configured language or "unknown")
                detected_lang = languages[0] if languages else "unknown"

                results.append(EngineResult(
                    text=text.strip(),
                    confidence=max(0.0, min(1.0, float(confidence))),
                    detected_language=detected_lang,
                    bbox=(x_min, y_min, x_max - x_min, y_max - y_min),
                    rotation=rotation,
                    engine_name="paddleocr",
                ))

        except Exception as e:
            logger.warning("PaddleOCR extract error: %s", e)

        return results

    def cleanup(self) -> None:
        """Release PaddleOCR resources."""
        self._engine = None
        self._initialized = False
        logger.info("PaddleOCR resources released")


# ── EasyOCR Engine ──────────────────────────────────────────────────────


class EasyOCREngine:
    """OCR engine using EasyOCR with multilingual support."""

    def __init__(self, device: str | None = None) -> None:
        self.device = device or settings.OCR_DEVICE
        self._reader = None
        self._initialized = False

    def initialize(self, languages: list[str] | None = None) -> None:
        """Initialize EasyOCR reader with specified languages."""
        if self._initialized:
            return
        try:
            import easyocr

            lang_list = languages or ["ja", "en"]
            gpu = self.device == "cuda"
            self._reader = easyocr.Reader(
                lang_list,
                gpu=gpu,
                verbose=False,
            )
            self._initialized = True
            logger.info("EasyOCR initialized (langs=%s, device=%s)", lang_list, self.device)
        except ImportError:
            logger.warning("easyocr not installed")
            self._reader = None
        except Exception as e:
            logger.warning("EasyOCR init failed: %s", e)
            self._reader = None

    def extract(self, image: Image.Image) -> list[EngineResult]:
        """Extract text using EasyOCR.

        Returns one EngineResult per detected text region.
        """
        if self._reader is None:
            return []

        results: list[EngineResult] = []
        try:
            import numpy as np

            img_array = np.array(image.convert("RGB"))
            raw = self._reader.readtext(img_array)

            for (poly_points, text, confidence) in raw:
                if not text.strip():
                    continue

                # Convert polygon to (x, y, w, h) bounding box
                xs = [p[0] for p in poly_points]
                ys = [p[1] for p in poly_points]
                x_min, x_max = min(xs), max(xs)
                y_min, y_max = min(ys), max(ys)

                rotation = _estimate_rotation(poly_points)

                # EasyOCR provides language detection per result in some versions
                detected_language = "unknown"

                results.append(EngineResult(
                    text=text.strip(),
                    confidence=max(0.0, min(1.0, float(confidence))),
                    detected_language=detected_language,
                    bbox=(x_min, y_min, x_max - x_min, y_max - y_min),
                    rotation=rotation,
                    engine_name="easyocr",
                ))

        except Exception as e:
            logger.warning("EasyOCR extract error: %s", e)

        return results

    def cleanup(self) -> None:
        """Release EasyOCR resources."""
        self._reader = None
        self._initialized = False
        logger.info("EasyOCR resources released")


# ── Tesseract Engine ────────────────────────────────────────────────────


class TesseractEngine:
    """OCR engine using Tesseract with multilingual support."""

    def __init__(self) -> None:
        self._initialized = False

    def initialize(self) -> None:
        """Verify Tesseract is available."""
        if self._initialized:
            return
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            self._initialized = True
            logger.info("Tesseract initialized")
        except ImportError:
            logger.warning("pytesseract not installed")
        except Exception as e:
            logger.warning("Tesseract init failed: %s", e)

    def extract(
        self,
        image: Image.Image,
        language: str = "jpn",
        psm: int = TESSERACT_PSM,
    ) -> list[EngineResult]:
        """Extract text using Tesseract with detailed data.

        Returns one EngineResult per detected text block/line.
        """
        if not self._initialized:
            return []

        results: list[EngineResult] = []
        try:
            import pytesseract

            custom_config = f"--oem {TESSERACT_OEM} --psm {psm} -l {language}"
            data = pytesseract.image_to_data(image, config=custom_config, output_type="dict")

            n_boxes = len(data.get("level", []))
            for i in range(n_boxes):
                text = (data.get("text", [])[i] or "").strip()
                conf_str = data.get("conf", [])[i]
                if not text or conf_str == "-1":
                    continue

                try:
                    conf = float(conf_str) / 100.0
                except (ValueError, TypeError):
                    conf = 0.0

                x = float(data.get("left", [0])[i])
                y = float(data.get("top", [0])[i])
                w = float(data.get("width", [0])[i])
                h = float(data.get("height", [0])[i])

                # Tesseract doesn't provide rotation per block easily
                rotation = 0.0
                if data.get("rotate", []):
                    try:
                        rotation = float(data["rotate"][i] or 0)
                    except (ValueError, TypeError):
                        rotation = 0.0

                results.append(EngineResult(
                    text=text,
                    confidence=max(0.0, min(1.0, conf)),
                    detected_language=language,
                    bbox=(x, y, w, h),
                    rotation=rotation,
                    engine_name="tesseract",
                ))

        except Exception as e:
            logger.warning("Tesseract extract error: %s", e)

        return results

    def cleanup(self) -> None:
        """Release Tesseract resources."""
        self._initialized = False
        logger.info("Tesseract resources released")


# ── Utility functions ────────────────────────────────────────────────────


def _estimate_rotation(poly_points: list[list[float]]) -> float:
    """Estimate text rotation angle from polygon points.

    Uses the angle of the top edge of the bounding polygon.
    Returns degrees from horizontal (-45 to 45 typically).
    """
    if len(poly_points) < 2:
        return 0.0
    import math
    dx = poly_points[1][0] - poly_points[0][0]
    dy = poly_points[1][1] - poly_points[0][1]
    if dx == 0:
        return 90.0 if abs(dy) > 0 else 0.0
    angle = math.degrees(math.atan2(dy, dx))
    # Normalize to roughly -90 to 90
    if angle > 90:
        angle -= 180
    elif angle < -90:
        angle += 180
    return round(angle, 1)


def engine_for_language(engine_name: str, lang_code: str) -> str:
    """Get the engine-specific language code for a given ISO language code."""
    lang_map = LANGUAGE_MAP.get(lang_code, {})
    return lang_map.get(engine_name, lang_code)
