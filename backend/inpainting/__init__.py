"""Image inpainting module for removing original text from manga pages.

Provides modular inpainting engines:
- OpenCV Inpainting (Navier-Stokes / Telea) — fast fallback
- LaMa (Large Mask Inpainting) — deep learning
- Content Aware Fill — PatchMatch texture synthesis
- Bubble Reconstruction — neighborhood interpolation
- Matting Refinement — edge blending

All engines support precise polygon/mask-based removal.
No white boxes are ever painted.
"""

from backend.inpainting.engines import (
    BaseInpaintingEngine,
    BubbleReconstructionEngine,
    ContentAwareFillEngine,
    DEFAULT_ENGINE_PRIORITY,
    ENGINE_REGISTRY,
    InpaintRegion,
    LaMaInpaintingEngine,
    MattingRefinementEngine,
    OpenCVInpaintingEngine,
    polygon_to_mask,
    dilate_mask,
    blur_mask_edges,
    detect_complex_background,
)

from backend.inpainting.service import (
    InpaintingService,
    InpaintResult,
)

from backend.inpainting.schemas import (
    InpaintRegionSchema,
    InpaintRequest,
    InpaintResponse,
    InpaintRegionResult,
    InpaintStats,
)

__all__ = [
    # Engines
    "BaseInpaintingEngine",
    "OpenCVInpaintingEngine",
    "LaMaInpaintingEngine",
    "ContentAwareFillEngine",
    "BubbleReconstructionEngine",
    "MattingRefinementEngine",
    "ENGINE_REGISTRY",
    "DEFAULT_ENGINE_PRIORITY",
    # Data types
    "InpaintRegion",
    # Utilities
    "polygon_to_mask",
    "dilate_mask",
    "blur_mask_edges",
    "detect_complex_background",
    # Service
    "InpaintingService",
    "InpaintResult",
    # Schemas
    "InpaintRegionSchema",
    "InpaintRequest",
    "InpaintResponse",
    "InpaintRegionResult",
    "InpaintStats",
]
