"""Enhanced Image Inpainting Service — removes original text without artifacts.

Pipeline:
1. Generate precise masks from polygons / SAM2 masks
2. Dilate masks to ensure complete text coverage
3. Detect complex backgrounds (screentones, gradients)
4. Run progressive multi-pass inpainting:
   - Pass 1: Main removal (LaMa / ContentAwareFill / OpenCV)
   - Pass 2: Artifact cleanup (Bubble Reconstruction)
   - Pass 3: Edge matting (Matting Refinement)
5. Verify no artifacts remain on difficult backgrounds

Key principles:
- NEVER paint white boxes — always use actual inpainting
- Polygon/mask-based removal, not just bbox
- Multi-pass for complex backgrounds
- Edge blending for seamless transitions
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

from backend.config import settings
from backend.inpainting.engines import (
    ENGINE_REGISTRY,
    DEFAULT_ENGINE_PRIORITY,
    MASK_DILATION_RADIUS,
    COMPLEX_BG_DILATION_RADIUS,
    MASK_BLUR_KERNEL,
    BaseInpaintingEngine,
    InpaintRegion,
    polygon_to_mask,
    dilate_mask,
    blur_mask_edges,
    detect_complex_background,
)

logger = logging.getLogger(__name__)


class InpaintResult:
    """Result of an inpainting operation."""

    def __init__(
        self,
        image: Image.Image,
        regions_inpainted: int = 0,
        processing_time_ms: float = 0.0,
        engine_used: str = "",
        masks_used: int = 0,
        polygons_used: int = 0,
        refinement_passes: int = 1,
        region_details: list[dict] | None = None,
    ) -> None:
        self.image = image
        self.regions_inpainted = regions_inpainted
        self.processing_time_ms = processing_time_ms
        self.engine_used = engine_used
        self.masks_used = masks_used
        self.polygons_used = polygons_used
        self.refinement_passes = refinement_passes
        self.region_details = region_details or []


class InpaintingService:
    """Enhanced service for removing original text from manga pages.

    Uses a modular multi-engine strategy with progressive refinement:
    1. Generate masks from polygons or SAM2 masks
    2. Run primary engine (LaMa → ContentAwareFill → OpenCV)
    3. Run Bubble Reconstruction for natural-looking backgrounds
    4. Run Matting Refinement for seamless edges

    Supports per-region masks (from SAM2) for pixel-perfect inpainting,
    and polygon-based masks for precise text removal.
    """

    def __init__(
        self,
        engine_priority: list[str] | None = None,
        device: str | None = None,
        refinement_passes: int = 2,
    ) -> None:
        self.engine_priority = engine_priority or list(DEFAULT_ENGINE_PRIORITY)
        self.device = device or settings.INPAINTING_DEVICE
        self.refinement_passes = refinement_passes
        self._engines: dict[str, BaseInpaintingEngine] = {}
        self._initialized: dict[str, bool] = {}

    async def initialize(self) -> None:
        """Initialize all inpainting engines in priority order.

        Engines that fail to initialize are skipped silently.
        At least one engine must be available.
        """
        for engine_name in self.engine_priority:
            if engine_name in self._engines:
                continue

            engine_class = ENGINE_REGISTRY.get(engine_name)
            if engine_class is None:
                logger.warning("Unknown inpainting engine: %s", engine_name)
                continue

            try:
                if engine_name == "lama":
                    engine = engine_class(device=self.device)
                elif engine_name == "opencv":
                    engine = engine_class()
                elif engine_name == "content_aware_fill":
                    engine = engine_class()
                elif engine_name == "bubble_reconstruction":
                    engine = engine_class()
                elif engine_name == "matting_refinement":
                    engine = engine_class()
                else:
                    continue

                await engine.initialize()
                if engine._initialized:
                    self._engines[engine_name] = engine
                    self._initialized[engine_name] = True
                    logger.info("Inpainting engine ready: %s", engine_name)
                else:
                    self._initialized[engine_name] = False

            except Exception as e:
                logger.info(
                    "Inpainting engine %s not available: %s",
                    engine_name, e,
                )
                self._initialized[engine_name] = False

        available = [n for n, v in self._initialized.items() if v]
        if not available:
            logger.warning(
                "No inpainting engines available! Install OpenCV or a deep "
                "learning inpainting model."
            )

    def _tile_image(
        self,
        image: Image.Image,
        tile_size: int = 1024,
    ) -> list[dict]:
        """Split a large image into overlapping tiles for memory-efficient processing.

        Useful for very large images (>4K resolution) that would exceed
        GPU memory. Processes each tile independently then stitches results.

        Args:
            image: Large PIL Image to tile.
            tile_size: Size of each tile in pixels (square).

        Returns:
            List of dicts with 'x', 'y', 'tile' keys.
        """
        w, h = image.size
        if w <= tile_size and h <= tile_size:
            return [{"x": 0, "y": 0, "tile": image}]

        overlap = tile_size // 8  # 12.5% overlap for seamlessness
        step = tile_size - overlap
        tiles = []

        for y in range(0, h, step):
            for x in range(0, w, step):
                x1 = x
                y1 = y
                x2 = min(x + tile_size, w)
                y2 = min(y + tile_size, h)
                tile = image.crop((x1, y1, x2, y2))
                tiles.append({"x": x1, "y": y1, "tile": tile})

        logger.debug(
            "Image tiled: %dx%d -> %d tiles (tile_size=%d)",
            w, h, len(tiles), tile_size,
        )
        return tiles

    def _stitch_tiles(
        self,
        tiles: list[dict],
        original_image: Image.Image,
    ) -> Image.Image:
        """Stitch processed tiles back into a full image with blending at overlaps.

        Uses the original image as the base so seams blend naturally.
        """
        w, h = original_image.size
        result = original_image.copy()
        mask_accum = Image.new("L", (w, h), 0)

        for tile_info in tiles:
            tile = tile_info["tile"]
            tx, ty = tile_info["x"], tile_info["y"]
            tw, th = tile.size

            # Create feathering mask for edge blending
            tile_mask = Image.new("L", (tw, th), 255)
            feather = min(tw, th) // 16
            if feather > 0:
                from PIL import ImageDraw
                draw = ImageDraw.Draw(tile_mask)
                # Fade edges
                draw.rectangle([0, 0, tw, feather], fill=0)
                draw.rectangle([0, th - feather, tw, th], fill=0)
                draw.rectangle([0, 0, feather, th], fill=0)
                draw.rectangle([tw - feather, 0, tw, th], fill=0)
                from PIL import ImageFilter
                tile_mask = tile_mask.filter(
                    ImageFilter.GaussianBlur(radius=feather // 2)
                )

            result.paste(tile, (tx, ty), tile_mask)
            mask_accum.paste(tile_mask, (tx, ty))

        # Fill any gaps (from non-overlapping tiles)
        import numpy as np
        mask_arr = np.array(mask_accum)
        gaps = mask_arr == 0
        if np.any(gaps):
            # Inpaint gaps with neighbor pixels
            import cv2
            gap_mask = (gaps * 255).astype(np.uint8)
            result_arr = np.array(result)
            filled = cv2.inpaint(result_arr, gap_mask, 3, cv2.INPAINT_TELEA)
            result = Image.fromarray(filled)

        return result

    async def inpaint_page(
        self,
        image: Image.Image,
        regions: list[InpaintRegion],
        refinement_passes: int | None = None,
    ) -> InpaintResult:
        """Inpaint (remove text from) all regions on a page.

        Performance-optimized with:
        - Tiling for large images (>4K) to prevent OOM on GPU
        - Early exit for pages with no regions
        - Memory-efficient mask generation
        - CUDA/GPU acceleration when available

        Args:
            image: PIL Image of the page to inpaint.
            regions: List of InpaintRegion to remove text from.
            refinement_passes: Number of refinement passes (default: from init).

        Returns:
            InpaintResult with the inpainted image.
        """
        start_time = time.perf_counter()
        num_passes = refinement_passes or self.refinement_passes

        if not self._engines:
            await self.initialize()

        if not self._engines:
            logger.error("No inpainting engines available!")
            return InpaintResult(
                image=image,
                regions_inpainted=0,
                processing_time_ms=0,
                engine_used="none",
            )

        # ── Step 1: Generate masks for all regions ───────────────────────
        page_mask = np.zeros((image.height, image.width), dtype=np.uint8)
        region_details = []

        for reg_idx, region in enumerate(regions):
            region_mask = None

            # Priority 1: Use SAM2 mask if available (highest quality)
            if region.mask is not None:
                mask = region.mask
                if mask.shape[:2] != (image.height, image.width):
                    mask_img = Image.fromarray(
                        (mask > 127).astype(np.uint8) * 255
                    )
                    mask = np.array(
                        mask_img.resize((image.width, image.height),
                                        Image.NEAREST),
                        dtype=np.uint8,
                    )
                else:
                    mask = (mask > 127).astype(np.uint8) * 255
                region_mask = mask

            # Priority 2: Use polygon if available (precise boundaries)
            elif region.polygon and len(region.polygon) >= 3:
                region_mask = polygon_to_mask(
                    (image.width, image.height),
                    region.polygon,
                )

            # Priority 3: Use bbox (fallback)
            else:
                x, y, w, h = region.bbox
                region_mask = np.zeros(
                    (image.height, image.width), dtype=np.uint8
                )
                y1 = max(0, y)
                x1 = max(0, x)
                y2 = min(image.height, y + h)
                x2 = min(image.width, x + w)
                region_mask[y1:y2, x1:x2] = 255

            if region_mask is None:
                continue

            is_complex = region.complex_background or detect_complex_background(
                np.array(image),
                region.bbox,
                region_mask,
            )

            dilation = (
                region.dilation_radius
                if region.dilation_radius > MASK_DILATION_RADIUS
                else (COMPLEX_BG_DILATION_RADIUS if is_complex
                      else MASK_DILATION_RADIUS)
            )

            region_mask = dilate_mask(region_mask, radius=dilation)
            region_mask = blur_mask_edges(region_mask, kernel_size=MASK_BLUR_KERNEL)
            page_mask = np.maximum(page_mask, region_mask)

            region_details.append({
                "index": reg_idx,
                "bbox": list(region.bbox),
                "has_mask": region.mask is not None,
                "has_polygon": len(region.polygon) >= 3,
                "complex_background": is_complex,
                "dilation_radius": dilation,
            })

        if not np.any(page_mask > 0):
            logger.info("No regions to inpaint")
            return InpaintResult(
                image=image,
                regions_inpainted=0,
                processing_time_ms=(time.perf_counter() - start_time) * 1000,
                engine_used="none",
            )

        # ── Step 2: Decide whether to tile (for large images) ────────────
        w, h = image.size
        should_tile = (w > 2048 or h > 2048) and settings.INPAINTING_DEVICE == "cpu"

        if should_tile:
            # Process as tiles to prevent memory issues
            tiles = self._tile_image(image, tile_size=1024)
            processed_tiles = []

            for tile_info in tiles:
                tx, ty = tile_info["x"], tile_info["y"]
                tile_img = tile_info["tile"]

                # Extract mask for this tile region
                tw, th = tile_img.size
                tile_mask = page_mask[ty:ty+th, tx:tx+tw]

                if not np.any(tile_mask > 0):
                    processed_tiles.append({"x": tx, "y": ty, "tile": tile_img})
                    continue

                # Process this tile
                current_tile = tile_img.copy()
                for engine_name in [e for e in self.engine_priority if e in self._engines]:
                    engine = self._engines.get(engine_name)
                    if engine is None:
                        continue
                    try:
                        inpaint_region = InpaintRegion(
                            bbox=(0, 0, tw, th),
                            polygon=[],
                            mask=tile_mask,
                            complex_background=True,
                        )
                        current_tile = await engine.inpaint(
                            current_tile, tile_mask, inpaint_region,
                        )
                        break
                    except Exception as e:
                        logger.debug("Tile engine %s failed: %s", engine_name, e)
                        continue

                processed_tiles.append({"x": tx, "y": ty, "tile": current_tile})

            current_image = self._stitch_tiles(processed_tiles, image)
            engine_used = "tiled"
        else:
            # Standard processing (full image)
            current_image = image.copy()
            engine_order = list(self.engine_priority)
            primary_engines = [e for e in engine_order if e != "matting_refinement"]
            refinement_engines = [
                e for e in self._engines
                if e in ("bubble_reconstruction",)
            ]
            final_engine = (
                "matting_refinement"
                if "matting_refinement" in self._engines
                else None
            )

            primary_engines = [
                e for e in primary_engines if e != "matting_refinement"
            ]

            engine_used = "none"

            # Pass 1: Main inpainting
            for engine_name in primary_engines:
                engine = self._engines.get(engine_name)
                if engine is None:
                    continue

                try:
                    inpaint_region = InpaintRegion(
                        bbox=(0, 0, image.width, image.height),
                        polygon=[],
                        mask=page_mask,
                        complex_background=True,
                    )
                    current_image = await engine.inpaint(
                        current_image, page_mask, inpaint_region,
                    )
                    engine_used = engine_name
                    break
                except Exception as e:
                    logger.warning(
                        "Primary engine %s failed: %s, trying next",
                        engine_name, e,
                    )
                    continue

            # Pass 2: Refinement passes
            remaining_mask = page_mask.copy()
            for _ in range(num_passes - 1):
                if not self._has_artifacts(current_image, image, remaining_mask):
                    break

                for engine_name in refinement_engines + primary_engines:
                    engine = self._engines.get(engine_name)
                    if engine is None:
                        continue

                    try:
                        current_image = await engine.inpaint(
                            current_image, remaining_mask, None,
                        )
                        break
                    except Exception:
                        continue

            # Pass 3: Matting refinement
            if final_engine and final_engine in self._engines:
                try:
                    current_image = await self._engines[final_engine].inpaint(
                        current_image, page_mask, None,
                    )
                    engine_used = f"{engine_used}+{final_engine}"
                except Exception as e:
                    logger.debug("Matting refinement skipped: %s", e)

        elapsed = (time.perf_counter() - start_time) * 1000

        logger.info(
            "Inpainting complete: %d regions, %d pass(es), %.0fms, engine=%s",
            len(regions), num_passes, elapsed, engine_used,
        )

        masks_count = sum(
            1 for r in region_details if r["has_mask"]
        )
        polygons_count = sum(
            1 for r in region_details if r["has_polygon"]
        )

        return InpaintResult(
            image=current_image,
            regions_inpainted=len(regions),
            processing_time_ms=elapsed,
            engine_used=engine_used,
            masks_used=masks_count,
            polygons_used=polygons_count,
            refinement_passes=num_passes,
            region_details=region_details,
        )

    async def inpaint_region(
        self,
        image: Image.Image,
        region: InpaintRegion,
    ) -> InpaintResult:
        """Inpaint a single region on the image.

        Convenience wrapper around inpaint_page for single regions.

        Args:
            image: PIL Image to inpaint.
            region: Single InpaintRegion.

        Returns:
            InpaintResult for the single region.
        """
        return await self.inpaint_page(image, [region])

    async def inpaint_batch(
        self,
        image: Image.Image,
        regions: list[InpaintRegion | tuple[int, int, int, int]],
    ) -> InpaintResult:
        """Inpaint multiple regions on an image.

        Accepts either InpaintRegion objects or legacy (x, y, w, h) tuples
        for backward compatibility.

        Args:
            image: PIL Image to inpaint.
            regions: List of InpaintRegion or (x, y, w, h) tuples.

        Returns:
            InpaintResult with the inpainted image.
        """
        inpaint_regions = []
        for r in regions:
            if isinstance(r, tuple):
                inpaint_regions.append(InpaintRegion(bbox=r))
            elif isinstance(r, InpaintRegion):
                inpaint_regions.append(r)
            else:
                raise TypeError(f"Unsupported region type: {type(r)}")

        return await self.inpaint_page(image, inpaint_regions)

    def _has_artifacts(
        self,
        inpainted: Image.Image,
        original: Image.Image,
        mask: np.ndarray,
        threshold: float = 20.0,
    ) -> bool:
        """Detect if there are visible artifacts in the inpainted area.

        Compares the inpainted result to the original, focusing
        on the masked regions. If the difference exceeds a threshold,
        there are remaining artifacts.

        Args:
            inpainted: The inpainted image.
            original: The original image (with text).
            mask: The inpainting mask.
            threshold: Maximum allowed mean pixel difference.

        Returns:
            True if artifacts remain.
        """
        import numpy as np

        imp = np.array(inpainted).astype(np.float32)
        orig = np.array(original).astype(np.float32)
        mask_bin = (mask > 0).astype(bool)

        if not np.any(mask_bin):
            return False

        diff = np.mean(np.abs(imp[mask_bin] - orig[mask_bin]))

        # If the inpainted area is very similar to original, text wasn't
        # removed — that could mean artifacts or just that the text area
        # was already clean. Check variance.
        if diff < threshold:
            # Likely well-inpainted, but check for remaining high-frequency content
            try:
                import cv2
                inpainted_gray = cv2.cvtColor(
                    (imp * mask_bin[..., None]).astype(np.uint8),
                    cv2.COLOR_RGB2GRAY,
                )
                edges = cv2.Canny(inpainted_gray, 50, 150)
                edge_ratio = np.sum(edges > 0) / max(np.sum(mask_bin), 1)
                # If there are significant edges remaining, artifacts exist
                return edge_ratio > 0.05
            except ImportError:
                pass

            return False

        return True

    async def cleanup(self) -> None:
        """Release all inpainting engine resources."""
        for engine_name, engine in self._engines.items():
            try:
                await engine.cleanup()
            except Exception as e:
                logger.debug("Cleanup %s: %s", engine_name, e)
        self._engines.clear()
        self._initialized.clear()
        logger.info("All inpainting resources released")



