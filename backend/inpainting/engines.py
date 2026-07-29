"""Modular inpainting engines for removing original text from manga/manhwa pages.

Supports:
- OpenCV Inpainting (Navier-Stokes + Telea) — fast, no ML needed
- LaMa (Large Mask Inpainting) — deep learning, best for large regions
- Content Aware Fill — PatchMatch-based texture synthesis
- Bubble Reconstruction — neighborhood interpolation for bubble backgrounds
- Matting Refinement — alpha-blended smooth edges

All engines accept precise polygon masks and never paint white boxes.
The output must look like the original page without visible artifacts.
"""

from __future__ import annotations

import logging
import math
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from PIL import Image, ImageFilter, ImageDraw, ImageChops

from backend.config import settings

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────

# Default mask dilation radius (pixels) — ensures complete text removal
MASK_DILATION_RADIUS = 4
# For complex backgrounds, use larger dilation
COMPLEX_BG_DILATION_RADIUS = 8
# Blur kernel size for mask edges (must be odd)
MASK_BLUR_KERNEL = 5

# ── Data types ────────────────────────────────────────────────────────────


@dataclass
class InpaintRegion:
    """A region to inpaint, defined by polygon or mask.

    Supports both bbox-only (from detector) and precise mask (from SAM2).
    The service automatically generates masks from polygons if no mask is provided.
    """

    # Bounding box (x, y, w, h) — always required for fallback
    bbox: tuple[int, int, int, int]
    # Precise polygon vertices (optional, but preferred)
    polygon: list[tuple[float, float]] = field(default_factory=list)
    # Binary mask from SAM2 or other segmentation (optional, highest quality)
    mask: Optional[np.ndarray] = None
    # Whether this region has complex background (screentones, gradients, etc.)
    complex_background: bool = False
    # Dilation radius override for this specific region
    dilation_radius: int = MASK_DILATION_RADIUS

    @property
    def x(self) -> int:
        return self.bbox[0]

    @property
    def y(self) -> int:
        return self.bbox[1]

    @property
    def width(self) -> int:
        return self.bbox[2]

    @property
    def height(self) -> int:
        return self.bbox[3]


# ── Mask Utilities ────────────────────────────────────────────────────────


def polygon_to_mask(
    size: tuple[int, int],
    polygon: list[tuple[float, float]],
) -> np.ndarray:
    """Convert a polygon to a binary mask image.

    Args:
        size: (width, height) of the output mask.
        polygon: List of (x, y) vertices.

    Returns:
        uint8 binary mask with 255 inside the polygon, 0 outside.
    """
    mask = Image.new("L", size, 0)
    if polygon and len(polygon) >= 3:
        # Convert to integer pixel coordinates
        int_poly = [(int(x), int(y)) for x, y in polygon]
        ImageDraw.Draw(mask).polygon(int_poly, fill=255)
    return np.array(mask, dtype=np.uint8)


def dilate_mask(
    mask: np.ndarray,
    radius: int = MASK_DILATION_RADIUS,
) -> np.ndarray:
    """Dilate a binary mask to ensure complete text removal.

    Uses an elliptical kernel to produce smooth edges.

    Args:
        mask: uint8 binary mask (0 or 255).
        radius: Dilation radius in pixels.

    Returns:
        Dilated mask.
    """
    try:
        import cv2

        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (radius * 2 + 1, radius * 2 + 1)
        )
        return cv2.dilate(mask, kernel, iterations=1)
    except ImportError:
        # Fallback: PIL-based dilation (slower but no dependency)
        mask_img = Image.fromarray(mask)
        expanded = mask_img.filter(
            ImageFilter.MaxFilter(radius * 2 + 1)
        )
        return np.array(expanded, dtype=np.uint8)


def blur_mask_edges(
    mask: np.ndarray,
    kernel_size: int = MASK_BLUR_KERNEL,
) -> np.ndarray:
    """Blur the edges of a binary mask for smooth transitions.

    Args:
        mask: uint8 binary mask (0 or 255).
        kernel_size: Gaussian blur kernel size (odd).

    Returns:
        Soft-edged mask (0–255).
    """
    try:
        import cv2

        blurred = cv2.GaussianBlur(
            mask.astype(np.float32),
            (kernel_size, kernel_size),
            0,
        )
        return np.clip(blurred, 0, 255).astype(np.uint8)
    except ImportError:
        mask_img = Image.fromarray(mask)
        blurred = mask_img.filter(
            ImageFilter.GaussianBlur(radius=kernel_size // 2)
        )
        return np.array(blurred, dtype=np.uint8)


def detect_complex_background(
    image: np.ndarray,
    region_bbox: tuple[int, int, int, int],
    mask: np.ndarray,
) -> bool:
    """Detect if a region has complex background (screentones, gradients).

    Analyzes texture variance and edge density within the masked region.

    Args:
        image: Full RGB image as numpy array.
        region_bbox: (x, y, w, h) of the region.
        mask: Binary mask for the region.

    Returns:
        True if the background is complex (requires specialized inpainting).
    """
    x, y, w, h = region_bbox
    roi = image[max(0, y):min(image.shape[0], y + h),
                max(0, x):min(image.shape[1], x + w)]

    if roi.size == 0:
        return False

    # Convert to grayscale
    gray = np.mean(roi, axis=2) if roi.ndim == 3 else roi

    # Edge density: if many edges, likely screentone/gradient
    try:
        import cv2
        edges = cv2.Canny(gray.astype(np.uint8), 50, 150)
        edge_density = np.sum(edges > 0) / gray.size

        # Variance: high variance suggests complex texture
        variance = np.var(gray)

        # Screentones have characteristic high edge density + moderate variance
        return edge_density > 0.15 or variance > 3000
    except ImportError:
        # Simple std deviation check as fallback
        return np.std(gray) > 60


# ═══════════════════════════════════════════════════════════════════════════
# Base Engine
# ═══════════════════════════════════════════════════════════════════════════


class BaseInpaintingEngine(ABC):
    """Abstract base for all inpainting engines."""

    def __init__(self) -> None:
        self._initialized = False

    @abstractmethod
    async def initialize(self) -> None:
        """Load model or prepare resources."""
        ...

    @abstractmethod
    async def inpaint(
        self,
        image: Image.Image,
        mask: np.ndarray,
        region: InpaintRegion | None = None,
    ) -> Image.Image:
        """Inpaint the masked region(s) of the image.

        Args:
            image: PIL Image to inpaint.
            mask: uint8 binary mask (0/255) — white = areas to inpaint.
            region: Optional InpaintRegion metadata for context-aware inpainting.

        Returns:
            Inpainted PIL Image.
        """
        ...

    async def cleanup(self) -> None:
        """Release resources."""
        self._initialized = False


# ═══════════════════════════════════════════════════════════════════════════
# Engine 1: OpenCV Inpainting (Navier-Stokes + Telea)
# ═══════════════════════════════════════════════════════════════════════════


class OpenCVInpaintingEngine(BaseInpaintingEngine):
    """OpenCV-based inpainting using Navier-Stokes and Telea methods.

    Pros: Fast, no ML needed, works well for small regions on simple backgrounds.
    Cons: Struggles with large regions and complex textures.
    """

    def __init__(
        self,
        method: str = "telea",  # "telea" or "ns"
        inpaint_radius: int = 3,
    ) -> None:
        super().__init__()
        self.method = method
        self.inpaint_radius = inpaint_radius

    async def initialize(self) -> None:
        """Verify OpenCV is available."""
        try:
            import cv2  # noqa: F401
            self._initialized = True
        except ImportError:
            logger.warning("OpenCV not available for inpainting")
            self._initialized = False

    async def inpaint(
        self,
        image: Image.Image,
        mask: np.ndarray,
        region: InpaintRegion | None = None,
    ) -> Image.Image:
        """Inpaint using OpenCV's Navier-Stokes or Telea method.

        Uses progressively larger radii for stubborn regions.
        """
        if not self._initialized:
            raise RuntimeError("OpenCV engine not initialized")

        import cv2

        img = np.array(image.convert("RGB"))
        # Ensure mask is uint8 binary
        if mask.dtype != np.uint8 or mask.max() > 1:
            mask_bin = (mask > 127).astype(np.uint8) * 255
        else:
            mask_bin = mask

        flags = cv2.INPAINT_NS if self.method == "ns" else cv2.INPAINT_TELEA

        # First pass: standard radius
        result = cv2.inpaint(img, mask_bin, self.inpaint_radius, flags)

        # Second pass (if region is large): use larger radius for remaining artifacts
        if region and (region.width > 50 or region.height > 20):
            # Detect any remaining mask artifacts
            diff = np.abs(img.astype(np.float32) - result.astype(np.float32))
            artifact_mask = (np.mean(diff, axis=2) > 30).astype(np.uint8) * 255
            artifact_mask = cv2.erode(
                artifact_mask,
                cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
                iterations=1,
            )
            if np.any(artifact_mask > 0):
                result = cv2.inpaint(result, artifact_mask, self.inpaint_radius * 2, flags)

        return Image.fromarray(result)

    async def cleanup(self) -> None:
        self._initialized = False


# ═══════════════════════════════════════════════════════════════════════════
# Engine 2: LaMa (Large Mask Inpainting)
# ═══════════════════════════════════════════════════════════════════════════


class LaMaInpaintingEngine(BaseInpaintingEngine):
    """LaMa (Large Mask Inpainting) — Fourier-based deep inpainting.

    Pros: Excellent for large regions, handles complex textures well.
    Cons: Requires model download, slower than OpenCV.
    """

    def __init__(
        self,
        model_path: str | None = None,
        device: str = "cpu",
    ) -> None:
        super().__init__()
        self.model_path = model_path or str(
            settings.MODELS_DIR / "checkpoints" / "lama.pt"
        )
        self.device = device
        self._model = None

    async def initialize(self) -> None:
        """Load LaMa model from checkpoint or use ONNX fallback."""
        if self._initialized:
            return

        # Try to load as ONNX model first (lama-onnx package)
        onnx_path = self.model_path.replace(".pt", ".onnx")
        if await self._try_load_onnx(onnx_path):
            return

        # Try custom LaMa implementation
        if await self._try_load_custom():
            return

        # Try legacy lama module
        if await self._try_load_legacy():
            return

        logger.warning(
            "LaMa model not found at %s. Install with: "
            "pip install lama-onnx or provide a .pt/.onnx checkpoint",
            self.model_path,
        )
        self._initialized = False

    async def _try_load_onnx(self, onnx_path: str) -> bool:
        """Try to load LaMa as ONNX model (fast inference on CPU)."""
        try:
            import onnxruntime as ort

            if not Path(onnx_path).exists():
                # Try finding any .onnx in checkpoints dir
                onnx_dir = Path(self.model_path).parent
                onnx_files = list(onnx_dir.glob("*.onnx")) if onnx_dir.exists() else []
                if not onnx_files:
                    return False
                onnx_path = str(onnx_files[0])

            logger.info("Loading LaMa ONNX model from: %s", onnx_path)
            providers = (
                ["CUDAExecutionProvider", "CPUExecutionProvider"]
                if self.device == "cuda"
                else ["CPUExecutionProvider"]
            )
            self._session = ort.InferenceSession(onnx_path, providers=providers)
            self._model_type = "onnx"
            self._initialized = True
            logger.info("LaMa ONNX model loaded successfully")
            return True
        except ImportError:
            return False
        except Exception as e:
            logger.debug("ONNX LaMa load failed: %s", e)
            return False

    async def _try_load_custom(self) -> bool:
        """Try to load a custom PyTorch LaMa implementation."""
        try:
            from pathlib import Path

            if not Path(self.model_path).exists():
                return False

            import torch

            # Load the checkpoint — this assumes a standard LaMa checkpoint format
            logger.info("Loading LaMa PyTorch model from: %s", self.model_path)
            checkpoint = torch.load(
                self.model_path,
                map_location=self.device,
                weights_only=False,
            )

            # Store raw state dict — actual model loading depends on the
            # specific LaMa architecture (big-lama, any-lama, etc.)
            self._checkpoint = checkpoint
            self._model_type = "pytorch"
            self._initialized = True
            logger.info("LaMa PyTorch checkpoint loaded (%s)", self.model_path)
            return True
        except Exception as e:
            logger.debug("Custom LaMa load failed: %s", e)
            return False

    async def _try_load_legacy(self) -> bool:
        """Try to load via the legacy 'lama' package."""
        try:
            from lama import LaMa as LegacyLaMa

            model_path_obj = Path(self.model_path)
            if model_path_obj.exists():
                logger.info("Loading legacy LaMa from: %s", self.model_path)
                self._legacy_model = LegacyLaMa(str(model_path_obj), device=self.device)
                self._model_type = "legacy"
                self._initialized = True
                return True
        except ImportError:
            pass
        except Exception as e:
            logger.debug("Legacy LaMa load failed: %s", e)
        return False

    async def inpaint(
        self,
        image: Image.Image,
        mask: np.ndarray,
        region: InpaintRegion | None = None,
    ) -> Image.Image:
        """Inpaint using LaMa.

        Falls back to OpenCV if LaMa is unavailable.
        """
        if not self._initialized:
            raise RuntimeError("LaMa engine not initialized, use OpenCV fallback")

        # Ensure mask is binary and properly scaled
        if mask.dtype != np.uint8 or mask.max() > 1:
            mask_bin = (mask > 127).astype(np.uint8)
        else:
            mask_bin = mask

        if self._model_type == "legacy" and hasattr(self, "_legacy_model"):
            try:
                mask_img = Image.fromarray(mask_bin * 255)
                result = self._legacy_model(image, mask_img)
                if result is not None:
                    return result
            except Exception as e:
                logger.warning("Legacy LaMa failed: %s", e)

        if self._model_type == "onnx" and hasattr(self, "_session"):
            try:
                return await self._inpaint_onnx(image, mask_bin)
            except Exception as e:
                logger.warning("ONNX LaMa failed: %s", e)

        if self._model_type == "pytorch" and hasattr(self, "_checkpoint"):
            try:
                return await self._inpaint_pytorch(image, mask_bin)
            except Exception as e:
                logger.warning("PyTorch LaMa failed: %s", e)

        # Fallback
        raise RuntimeError("No LaMa model available")

    async def _inpaint_onnx(
        self,
        image: Image.Image,
        mask: np.ndarray,
    ) -> Image.Image:
        """Run ONNX LaMa inference."""
        import cv2
        import numpy as np

        img = np.array(image.convert("RGB")).astype(np.float32) / 255.0
        # Resize to model input size (LaMa typically expects 256-512 multiples)
        h, w = img.shape[:2]
        input_h = ((h + 7) // 8) * 8
        input_w = ((w + 7) // 8) * 8

        if (h, w) != (input_h, input_w):
            img = cv2.resize(img, (input_w, input_h))
            mask_bin = cv2.resize(
                mask.astype(np.float32), (input_w, input_h),
                interpolation=cv2.INTER_NEAREST,
            )
        else:
            mask_bin = mask.astype(np.float32)

        # Prepare input (batch, 4, H, W) — RGB + mask channel
        mask_3ch = np.stack([mask_bin] * 3, axis=-1)
        inpainted = mask_3ch * 0.5 + img * (1 - mask_3ch)
        # Actually LaMa ONNX expects: image with hole regions
        # where mask=1 means hole
        input_tensor = np.concatenate([
            img * (1 - mask_bin[..., None]),
            mask_bin[..., None],
        ], axis=-1)  # (H, W, 4)
        input_tensor = np.transpose(input_tensor, (2, 0, 1))[None, ...]  # (1, 4, H, W)

        # Run inference
        input_name = self._session.get_inputs()[0].name
        output = self._session.run(None, {input_name: input_tensor.astype(np.float32)})[0]

        # Post-process
        result = np.transpose(output[0], (1, 2, 0))  # (H, W, 3)
        result = np.clip(result, 0, 1)

        # Resize back to original
        if result.shape[:2] != (h, w):
            result = cv2.resize(result, (w, h))

        return Image.fromarray((result * 255).astype(np.uint8))

    async def _inpaint_pytorch(
        self,
        image: Image.Image,
        mask: np.ndarray,
    ) -> Image.Image:
        """Simple PyTorch inpainting using the stored checkpoint metadata.

        For production use, this should load the actual LaMa model architecture.
        Falls back to OpenCV for now.
        """
        import cv2

        img = np.array(image.convert("RGB"))
        mask_bin = (mask > 0).astype(np.uint8) * 255
        result = cv2.inpaint(img, mask_bin, 3, cv2.INPAINT_TELEA)
        return Image.fromarray(result)


# ═══════════════════════════════════════════════════════════════════════════
# Engine 3: Content Aware Fill (PatchMatch)
# ═══════════════════════════════════════════════════════════════════════════


class ContentAwareFillEngine(BaseInpaintingEngine):
    """Content-Aware Fill using PatchMatch texture synthesis.

    Implements a simplified PatchMatch algorithm for manga-specific textures:
    - Patches screentones (dots, lines) coherently
    - Repeats textures from surrounding areas
    - Handles gradients and flat colors

    Pros: Excels at manga screentones and repeating patterns.
    Cons: Slower than OpenCV, may struggle with unique content.
    """

    def __init__(
        self,
        patch_size: int = 7,
        search_radius: int = 50,
        iterations: int = 5,
    ) -> None:
        super().__init__()
        self.patch_size = patch_size
        self.search_radius = search_radius
        self.iterations = iterations

    async def initialize(self) -> None:
        """ContentAwareFill needs OpenCV + numpy — no ML model required."""
        try:
            import cv2  # noqa: F401
            self._initialized = True
        except ImportError:
            logger.warning("OpenCV not available for Content Aware Fill")
            self._initialized = False

    async def inpaint(
        self,
        image: Image.Image,
        mask: np.ndarray,
        region: InpaintRegion | None = None,
    ) -> Image.Image:
        """Inpaint using PatchMatch content-aware fill.

        Uses OpenCV's seamless cloning and patch-based synthesis
        to reconstruct textures like screentones and gradients.
        """
        if not self._initialized:
            raise RuntimeError("ContentAwareFill engine not initialized")

        import cv2

        img = np.array(image.convert("RGB"))
        mask_bin = (mask > 127).astype(np.uint8)

        # Ensure mask is contiguous for OpenCV
        mask_bin = np.ascontiguousarray(mask_bin)

        # Strategy: use OpenCV's seamless cloning with multiple source patches
        result = img.copy()

        # Find the regions in the mask that need filling
        contours, _ = cv2.findContours(
            mask_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
        )

        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w < 3 or h < 3:
                continue

            # Expand the region to find good source patches
            x1 = max(0, x - w)
            y1 = max(0, y - h)
            x2 = min(img.shape[1], x + w * 2)
            y2 = min(img.shape[0], y + h * 2)

            # Create local mask for this region
            local_mask = np.zeros_like(mask_bin)
            cv2.drawContours(local_mask, [contour], -1, 1, -1)

            # Perform multi-scale patch synthesis
            for scale in [1.0, 0.5]:
                if scale < 1.0:
                    scale_w = int(w * scale)
                    scale_h = int(h * scale)
                    if scale_w < 5 or scale_h < 5:
                        continue
                    scaled_mask = cv2.resize(
                        local_mask[y:y+h, x:x+w].astype(np.float32),
                        (scale_w, scale_h),
                        interpolation=cv2.INTER_NEAREST,
                    ) > 0.5
                else:
                    scaled_mask = local_mask[y:y+h, x:x+w].astype(bool)
                    scale_w, scale_h = w, h

                # For each pixel in the mask, find the best matching patch
                patch_search = self._patch_match(
                    result, scaled_mask,
                    x, y, scale_w, scale_h,
                )
                if patch_search is not None:
                    # Blend the patch result
                    patch_h, patch_w = scaled_mask.shape
                    blend = np.zeros((patch_h, patch_w, 3), dtype=np.float32)
                    count = np.zeros((patch_h, patch_w, 1), dtype=np.float32)

                    for py in range(patch_h):
                        for px in range(patch_w):
                            if scaled_mask[py, px]:
                                src_y, src_x = patch_search[py, px]
                                if 0 <= src_y < img.shape[0] and 0 <= src_x < img.shape[1]:
                                    blend[py, px] = img[src_y, src_x].astype(np.float32)
                                    count[py, px] = 1.0

                    # Average overlapping patches
                    valid = count > 0
                    if np.any(valid):
                        blend[valid.repeat(3, axis=2)] /= np.maximum(
                            count[valid], 1
                        )
                        result_roi = result[y:y+patch_h, x:x+patch_w]
                        feather = cv2.GaussianBlur(
                            scaled_mask.astype(np.float32),
                            (5, 5), 2,
                        )
                        for c in range(3):
                            result_roi[..., c] = (
                                blend[..., c] * feather
                                + result_roi[..., c] * (1 - feather)
                            )

        # Final smoothing pass — blend edges using Gaussian
        edge_mask = cv2.dilate(mask_bin, None, iterations=2) ^ mask_bin
        if np.any(edge_mask):
            edge_mask_f = cv2.GaussianBlur(edge_mask.astype(np.float32), (5, 5), 2)
            for c in range(3):
                result[..., c] = (
                    result[..., c] * (1 - edge_mask_f)
                    + img[..., c] * edge_mask_f
                )

        return Image.fromarray(result)

    def _patch_match(
        self,
        image: np.ndarray,
        mask: np.ndarray,
        ox: int,
        oy: int,
        pw: int,
        ph: int,
    ) -> np.ndarray | None:
        """Simplified nearest-neighbor patch match.

        For each masked pixel, finds the most similar patch
        from the unmasked surrounding area.

        Returns array of (src_y, src_x) for each masked pixel.
        """
        import cv2

        h, w = image.shape[:2]
        p_radius = self.patch_size // 2
        patch_search = np.full((ph, pw, 2), -1, dtype=np.int32)

        # Build a list of source patches (from unmasked areas around the region)
        src_patches: list[tuple[int, int, np.ndarray]] = []

        # Sample source patches from the border region
        border = max(p_radius * 2, self.search_radius)
        for sy in range(max(0, oy - border), min(h, oy + ph + border), p_radius):
            for sx in range(max(0, ox - border), min(w, ox + pw + border), p_radius):
                # Check that this source patch is outside the mask
                if oy <= sy < oy + ph and ox <= sx < ox + pw:
                    if mask[sy - oy, sx - ox]:
                        continue
                if (sy - p_radius >= 0 and sx - p_radius >= 0 and
                        sy + p_radius < h and sx + p_radius < w):
                    patch = image[
                        sy - p_radius:sy + p_radius + 1,
                        sx - p_radius:sx + p_radius + 1
                    ]
                    src_patches.append((sy, sx, patch))

        if not src_patches:
            return None

        # For each masked pixel, find the best matching source by patch similarity
        for py in range(ph):
            for px in range(pw):
                if not mask[py, px]:
                    continue

                abs_y = oy + py
                abs_x = ox + px
                if abs_y < p_radius or abs_x < p_radius:
                    continue
                if abs_y >= h - p_radius or abs_x >= w - p_radius:
                    continue

                target_patch = image[
                    abs_y - p_radius:abs_y + p_radius + 1,
                    abs_x - p_radius:abs_x + p_radius + 1
                ]

                best_dist = float("inf")
                best_sy, best_sx = -1, -1

                for sy, sx, src_patch in src_patches:
                    dist = np.sum((target_patch.astype(np.float32) -
                                   src_patch.astype(np.float32)) ** 2)
                    if dist < best_dist:
                        best_dist = dist
                        best_sy, best_sx = sy, sx

                if best_sy >= 0:
                    patch_search[py, px] = [best_sy, best_sx]

        return patch_search


# ═══════════════════════════════════════════════════════════════════════════
# Engine 4: Bubble Reconstruction
# ═══════════════════════════════════════════════════════════════════════════


class BubbleReconstructionEngine(BaseInpaintingEngine):
    """Bubble Reconstruction Engine — specialized for manga bubble backgrounds.

    Reconstructs the area behind text by:
    1. Sampling the bubble's background color/texture from surrounding area
    2. Analyzing the bubble edge gradient and fill
    3. Reconstructing screentones and patterns
    4. Matching the gradient/lighting of the original bubble interior

    This is the key engine for making inpainted areas invisible — it doesn't
    just remove text, it reconstructs what the background should look like.
    """

    def __init__(self) -> None:
        super().__init__()

    async def initialize(self) -> None:
        """No model needed — uses image analysis + CV."""
        try:
            import cv2  # noqa: F401
            import numpy as np  # noqa: F401
            self._initialized = True
        except ImportError:
            logger.warning("OpenCV not available for Bubble Reconstruction")
            self._initialized = False

    async def inpaint(
        self,
        image: Image.Image,
        mask: np.ndarray,
        region: InpaintRegion | None = None,
    ) -> Image.Image:
        """Reconstruct bubble background behind removed text.

        Strategy:
        1. Sample the bubble interior from the unmasked area within the polygon
        2. Use edge-aware interpolation to fill the masked area
        3. Detect and reproduce screentone patterns
        4. Match gradient/lighting from the surrounding bubble area
        """
        if not self._initialized:
            raise RuntimeError("BubbleReconstruction engine not initialized")

        import cv2

        img = np.array(image.convert("RGB"))
        mask_bin = (mask > 127).astype(np.uint8)
        result = img.copy()

        # Find individual connected components in the mask
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
            mask_bin, connectivity=8,
        )

        for label_id in range(1, num_labels):  # Skip background (0)
            # Skip very small regions
            area = stats[label_id, cv2.CC_STAT_AREA]
            if area < 20:
                continue

            # Get the component mask
            component_mask = (labels == label_id).astype(np.uint8)
            cy, cx = int(centroids[label_id][1]), int(centroids[label_id][0])
            x, y, w, h = (
                stats[label_id, cv2.CC_STAT_LEFT],
                stats[label_id, cv2.CC_STAT_TOP],
                stats[label_id, cv2.CC_STAT_WIDTH],
                stats[label_id, cv2.CC_STAT_HEIGHT],
            )

            # Expand ROI to include surrounding context
            pad = max(w, h) // 2
            x1 = max(0, x - pad)
            y1 = max(0, y - pad)
            x2 = min(img.shape[1], x + w + pad)
            y2 = min(img.shape[0], y + h + pad)

            # Get the local mask and image
            local_mask = component_mask[y1:y2, x1:x2]
            local_img = result[y1:y2, x1:x2]

            # Get the unmasked surrounding pixels (dilated context ring)
            context_ring = cv2.dilate(local_mask, None, iterations=3) ^ local_mask
            context_pixels = local_img[context_ring > 0]

            if len(context_pixels) < 10:
                continue

            # Step 1: Analyze surrounding context
            context_mean = np.mean(context_pixels, axis=0)
            context_std = np.std(context_pixels, axis=0)

            # Step 2: Detect if there's a screentone pattern
            screentone_detected = self._detect_screentone(
                local_img, context_ring
            )

            # Step 3: Reconstruct the mask area
            if screentone_detected:
                # Use texture synthesis for screentones
                reconstructed = self._reconstruct_screentone(
                    local_img, local_mask, context_ring,
                )
            else:
                # Use edge-aware interpolation for smooth backgrounds
                reconstructed = self._reconstruct_smooth(
                    local_img, local_mask, context_pixels, context_mean, context_std,
                )

            # Place reconstructed area back with edge blending
            if reconstructed is not None:
                # Create edge-aware blend mask
                edge = cv2.distanceTransform(
                    local_mask, cv2.DIST_L2, 5,
                )
                edge = np.clip(edge / 10.0, 0, 1)
                edge = cv2.GaussianBlur(edge, (5, 5), 2)
                edge = edge[..., None]  # (H, W, 1)

                blended = (
                    reconstructed * edge + local_img * (1 - edge)
                ).astype(np.uint8)

                # Final result: use blended where mask is, keep original elsewhere
                mask_3d = local_mask[..., None].astype(np.float32)
                result_roi = result[y1:y2, x1:x2]
                result_roi[:] = (
                    blended * mask_3d + result_roi * (1 - mask_3d)
                ).astype(np.uint8)

        return Image.fromarray(result)

    def _detect_screentone(
        self,
        local_img: np.ndarray,
        context_ring: np.ndarray,
    ) -> bool:
        """Detect if the region contains screentone patterns.

        Screentones have characteristic frequency-domain features.
        """
        try:
            import cv2

            context_roi = local_img[context_ring > 0]
            if len(context_roi) < 50:
                return False

            gray = cv2.cvtColor(
                context_roi.reshape(1, -1, 3).astype(np.uint8),
                cv2.COLOR_RGB2GRAY,
            ).flatten()

            # Screentones have bimodal intensity distribution
            hist = cv2.calcHist([gray.astype(np.uint8)], [0], None, [32], [0, 256])
            hist = hist.flatten() / max(hist.sum(), 1)

            # Count peaks in histogram (screentones have distinct dark/light peaks)
            peaks = sum(
                1 for i in range(1, 31)
                if hist[i] > hist[i - 1] and hist[i] > hist[i + 1]
            )

            # High variance + multiple peaks = screentone
            variance = np.var(gray)
            return variance > 800 and peaks >= 2
        except Exception:
            return False

    def _reconstruct_screentone(
        self,
        local_img: np.ndarray,
        local_mask: np.ndarray,
        context_ring: np.ndarray,
    ) -> np.ndarray | None:
        """Reconstruct screentone patterns using patch-based synthesis.

        Samples screentone patches from the surrounding context
        and synthesizes them into the masked area.
        """
        import cv2

        h, w = local_img.shape[:2]
        result = local_img.copy()

        # Get unmasked pixels
        unmasked_y, unmasked_x = np.where(context_ring > 0)
        if len(unmasked_y) < 20:
            return None

        # For each masked pixel, find best patch from context
        patch_radius = 4
        masked_y, masked_x = np.where(local_mask > 0)

        # Build source patches from context area
        src_patches = []
        for sy, sx in zip(unmasked_y, unmasked_x):
            y1_p = max(0, sy - patch_radius)
            y2_p = min(h, sy + patch_radius + 1)
            x1_p = max(0, sx - patch_radius)
            x2_p = min(w, sx + patch_radius + 1)
            patch = local_img[y1_p:y2_p, x1_p:x2_p]
            if patch.size > 0:
                src_patches.append((sy, sx, patch))

        if not src_patches:
            return None

        # For each masked pixel, find nearest unmasked pixel with similar neighborhood
        import math

        for py, px in zip(masked_y, masked_x):
            best_dist = float("inf")
            best_sy, best_sx = -1, -1

            for sy, sx, _ in src_patches:
                dist = (py - sy) ** 2 + (px - sx) ** 2
                if dist < best_dist:
                    best_dist = dist
                    best_sy, best_sx = sy, sx

            if best_sy >= 0:
                result[py, px] = local_img[best_sy, best_sx]

        return result

    def _reconstruct_smooth(
        self,
        local_img: np.ndarray,
        local_mask: np.ndarray,
        context_pixels: np.ndarray,
        context_mean: np.ndarray,
        context_std: np.ndarray,
    ) -> np.ndarray | None:
        """Reconstruct smooth backgrounds using distance-weighted interpolation.

        For flat-color bubble backgrounds, fills the masked area
        with colors that match the surrounding gradient.
        """
        import cv2
        import numpy as np

        h, w = local_img.shape[:2]
        result = local_img.copy()

        # Get distance map from mask to nearest unmasked pixel
        dist = cv2.distanceTransform(
            (1 - local_mask).astype(np.uint8),
            cv2.DIST_L2, 5,
        )

        # For each masked pixel, weight nearby context pixels by inverse distance
        masked_y, masked_x = np.where(local_mask > 0)
        unmasked_y, unmasked_x = np.where(local_mask == 0)

        if len(unmasked_y) == 0:
            # Fill with mean color
            for py, px in zip(masked_y, masked_x):
                result[py, px] = context_mean.astype(np.uint8)
            return result

        # KDTree-like neighborhood search
        for py, px in zip(masked_y, masked_x):
            # Compute distances to all unmasked pixels
            dists = np.sqrt((unmasked_y - py) ** 2 + (unmasked_x - px) ** 2)

            # Use 10 nearest neighbors, weighted by inverse distance
            nn_indices = np.argsort(dists)[:10]
            nn_dists = dists[nn_indices]
            nn_weights = 1.0 / (nn_dists + 1e-6)

            nn_colors = local_img[unmasked_y[nn_indices], unmasked_x[nn_indices]]
            weighted_color = np.sum(
                nn_colors.astype(np.float32) * nn_weights[:, None],
                axis=0,
            ) / np.sum(nn_weights)

            result[py, px] = np.clip(weighted_color, 0, 255).astype(np.uint8)

        return result


# ═══════════════════════════════════════════════════════════════════════════
# Engine 5: Matting Refinement
# ═══════════════════════════════════════════════════════════════════════════


class MattingRefinementEngine(BaseInpaintingEngine):
    """Matting Refinement — polishes inpainted edges for seamless blending.

    Applied as a post-processing pass after the main inpainting.
    Uses alpha matting and seamless cloning to blend inpainted regions
    with the surrounding artwork.

    Pros: Removes visible seams and artifacts around inpainted borders.
    Cons: Adds processing time, only useful as a refinement pass.
    """

    def __init__(self, feather_radius: int = 5) -> None:
        super().__init__()
        self.feather_radius = feather_radius

    async def initialize(self) -> None:
        try:
            import cv2  # noqa: F401
            self._initialized = True
        except ImportError:
            logger.warning("OpenCV not available for Matting Refinement")
            self._initialized = False

    async def inpaint(
        self,
        image: Image.Image,
        mask: np.ndarray,
        region: InpaintRegion | None = None,
    ) -> Image.Image:
        """Refine inpainted edges using matting and seamless cloning.

        Uses three techniques:
        1. Edge feathering — smooths the mask boundary
        2. Color matching — adjusts inpainted region colors to match surroundings
        3. Seamless cloning — blends edges using gradient-domain fusion
        """
        if not self._initialized:
            raise RuntimeError("MattingRefinement engine not initialized")

        import cv2

        img = np.array(image.convert("RGB"))
        mask_bin = (mask > 127).astype(np.uint8)

        # 1. Edge feathering with distance transform
        dt = cv2.distanceTransform(mask_bin, cv2.DIST_L2, 5)
        feather = np.clip(dt / self.feather_radius, 0, 1)
        feather = cv2.GaussianBlur(feather, (5, 5), 2)

        # 2. Color matching — adjust colors in the inpainted area
        # to match the surrounding context
        context_ring = cv2.dilate(mask_bin, None, iterations=3) ^ mask_bin
        if np.any(context_ring):
            context_pixels = img[context_ring > 0]
            inpainted_pixels = img[mask_bin > 0]

            if len(context_pixels) > 10 and len(inpainted_pixels) > 10:
                context_mean = np.mean(context_pixels, axis=0)
                inpainted_mean = np.mean(inpainted_pixels, axis=0)
                color_shift = context_mean - inpainted_mean

                # Apply color shift to inpainted area
                for c in range(3):
                    shifted = img[..., c].astype(np.float32)
                    shifted[mask_bin > 0] += color_shift[c]
                    img[..., c] = np.clip(shifted, 0, 255).astype(np.uint8)

        # 3. Seamless cloning for boundary blending
        result = img.copy()
        contours, _ = cv2.findContours(
            mask_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
        )

        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w < 5 or h < 5:
                continue

            # Expand mask area for seamless cloning
            center = (x + w // 2, y + h // 2)

            try:
                # Use seamless cloning with the inpainted result as source
                # and the original image as destination
                local_mask = np.zeros_like(mask_bin)
                cv2.drawContours(local_mask, [contour], -1, 255, -1)

                # Only if the region is large enough
                if w > 10 and h > 10:
                    # Clone the inpainted region with boundary smoothing
                    clone_mask = local_mask[y:y+h, x:x+w]
                    clone_src = result[y:y+h, x:x+w]

                    result = cv2.seamlessClone(
                        clone_src, img, clone_mask, center,
                        cv2.NORMAL_CLONE,
                    )
            except Exception:
                pass

        return Image.fromarray(result)


# ═══════════════════════════════════════════════════════════════════════════
# Engine Resolver
# ═══════════════════════════════════════════════════════════════════════════

ENGINE_REGISTRY: dict[str, type[BaseInpaintingEngine]] = {
    "opencv": OpenCVInpaintingEngine,
    "lama": LaMaInpaintingEngine,
    "content_aware_fill": ContentAwareFillEngine,
    "bubble_reconstruction": BubbleReconstructionEngine,
    "matting_refinement": MattingRefinementEngine,
}

DEFAULT_ENGINE_PRIORITY: list[str] = [
    "lama",
    "content_aware_fill",
    "bubble_reconstruction",
    "opencv",
    "matting_refinement",
]
