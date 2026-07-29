"""Export engines for manga/manhwa chapters.

Supports:
- PDF — multi-page PDF with metadata
- PNG — individual page PNG files in a folder
- JPG/JPEG — individual page JPEG files
- WEBP — individual page WebP files
- ZIP — compressed ZIP archive
- CBZ — comic book ZIP archive
- CBR — comic book RAR archive (with RAR fallback to ZIP)
"""

from backend.services.export.engines import (
    EXPORT_ENGINE_REGISTRY,
    DEFAULT_EXPORT_PRIORITY,
    BaseExportEngine,
    PdfExportEngine,
    ImageExportEngine,
    ZipExportEngine,
    CbzExportEngine,
    CbrExportEngine,
)

__all__ = [
    "EXPORT_ENGINE_REGISTRY",
    "DEFAULT_EXPORT_PRIORITY",
    "BaseExportEngine",
    "PdfExportEngine",
    "ImageExportEngine",
    "ZipExportEngine",
    "CbzExportEngine",
    "CbrExportEngine",
]
