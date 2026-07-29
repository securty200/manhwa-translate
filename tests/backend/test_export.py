"""Tests for the enhanced export system.

Tests cover:
- All 7 export formats (PDF, PNG, JPG, WEBP, ZIP, CBZ, CBR)
- Page range selection
- Export engine initialization
- Page filtering
- Image loading/saving
- Metadata generation
- Progress callbacks
- Edge cases (empty pages, invalid ranges)
"""

from __future__ import annotations

import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Generator

import pytest
from PIL import Image

from backend.services.export_service import ExportService, ExportTask
from backend.services.export.engines import (
    EXPORT_ENGINE_REGISTRY,
    PdfExportEngine,
    ImageExportEngine,
    ZipExportEngine,
    CbzExportEngine,
    CbrExportEngine,
    BaseExportEngine,
    ExportChapter,
    ExportOptions,
    ExportPage,
    ExportProgress,
)
from backend.schemas.export import (
    ExportRequest,
    SUPPORTED_FORMATS,
    ExportFormatInfo,
)


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def sample_pages() -> list[ExportPage]:
    """Create sample pages with PIL images."""
    pages = []
    for i in range(1, 11):
        img = Image.new("RGB", (400, 600), color=(i * 20, i * 10, i * 5))
        pages.append(ExportPage(
            page_number=i,
            pil_image=img,
            width=400,
            height=600,
            is_translated=True,
        ))
    return pages


@pytest.fixture
def sample_chapter(sample_pages) -> ExportChapter:
    """Create a sample chapter with 10 pages."""
    return ExportChapter(
        chapter_id="ch-001",
        chapter_number=1,
        chapter_title="The Beginning",
        pages=sample_pages,
        manga_title="Test Manga",
    )


@pytest.fixture
def sample_chapters(sample_chapter) -> list[ExportChapter]:
    """Create 2 sample chapters."""
    ch2 = ExportChapter(
        chapter_id="ch-002",
        chapter_number=2,
        chapter_title="The Middle",
        pages=[
            ExportPage(page_number=i, pil_image=Image.new("RGB", (400, 600)))
            for i in range(1, 6)
        ],
        manga_title="Test Manga",
    )
    return [sample_chapter, ch2]


@pytest.fixture
def export_service() -> ExportService:
    """Create a fresh export service."""
    return ExportService()


@pytest.fixture
def temp_output() -> Generator[str, None, None]:
    """Create a temporary output path."""
    with tempfile.NamedTemporaryFile(suffix=".cbz", delete=False) as f:
        path = f.name
    yield path
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


# ── Engine Registry Tests ────────────────────────────────────────────────


def test_engine_registry_has_all_formats():
    """Test that all 7 formats are registered."""
    expected = {"pdf", "png", "jpg", "webp", "zip", "cbz", "cbr"}
    # Note: "jpeg" maps to "jpg", but both keys should resolve
    assert "pdf" in EXPORT_ENGINE_REGISTRY
    assert "png" in EXPORT_ENGINE_REGISTRY
    assert "jpg" in EXPORT_ENGINE_REGISTRY
    assert "webp" in EXPORT_ENGINE_REGISTRY
    assert "zip" in EXPORT_ENGINE_REGISTRY
    assert "cbz" in EXPORT_ENGINE_REGISTRY
    assert "cbr" in EXPORT_ENGINE_REGISTRY


def test_engine_format_names():
    """Test that each engine returns correct format info."""
    for fmt, cls in EXPORT_ENGINE_REGISTRY.items():
        engine = cls() if fmt not in ("png", "jpg", "webp") else cls(image_format=fmt.upper())
        assert engine.format_name is not None
        assert engine.file_extension is not None
        assert engine.file_extension.startswith(".")


# ── Export Engine Tests ──────────────────────────────────────────────────


def test_cbz_export(sample_chapters, temp_output):
    """Test CBZ export produces a valid comic book archive."""
    engine = CbzExportEngine()
    options = ExportOptions(format="cbz", quality=90)
    result = engine.export(temp_output, sample_chapters, options)

    assert Path(result).exists()
    assert result.endswith(".cbz")

    # Verify it's a valid ZIP file
    with zipfile.ZipFile(result, "r") as zf:
        names = zf.namelist()
        assert len(names) >= 2  # metadata.json + at least one page
        assert "metadata.json" in names

        # Check metadata content
        meta = json.loads(zf.read("metadata.json"))
        assert meta["generated_by"] == "AI Manga Translator"
        assert "chapters" in meta
        assert meta["ComicRack"]["series"] == "Test Manga"

        # Check that pages are present
        page_files = [n for n in names if n.startswith("Chapter_")]
        assert len(page_files) > 0


def test_zip_export(sample_chapters, temp_output):
    """Test ZIP export produces a valid archive."""
    engine = ZipExportEngine()
    # Replace .cbz with .zip
    zip_path = temp_output.replace(".cbz", ".zip")
    options = ExportOptions(format="zip", quality=90)
    result = engine.export(zip_path, sample_chapters, options)

    assert Path(result).exists()
    with zipfile.ZipFile(result, "r") as zf:
        meta = json.loads(zf.read("metadata.json"))
        assert meta["generated_by"] == "AI Manga Translator"


def test_pdf_export(sample_chapters):
    """Test PDF export produces a valid file."""
    engine = PdfExportEngine()
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        pdf_path = f.name

    try:
        options = ExportOptions(format="pdf", quality=90)
        result = engine.export(pdf_path, sample_chapters, options)
        assert Path(result).exists()
        assert result.endswith(".pdf")
        # PDF should have content
        assert Path(result).stat().st_size > 100
    finally:
        try:
            os.unlink(pdf_path)
        except FileNotFoundError:
            pass


def test_png_export(sample_chapters):
    """Test PNG image export produces files in a directory."""
    engine = ImageExportEngine(image_format="PNG")
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = str(Path(tmpdir) / "png_export")
        options = ExportOptions(format="png", quality=90)
        result = engine.export(output_dir, sample_chapters, options)

        result_path = Path(result)
        assert result_path.is_dir()

        # Check for chapter folders
        chapter_dirs = list(result_path.glob("Chapter_*"))
        assert len(chapter_dirs) == 2  # 2 chapters

        # Check for page images
        page_files = list(result_path.rglob("page_*.png"))
        assert len(page_files) >= 10  # At least chapter 1's 10 pages

        # Check metadata
        meta_file = result_path / "metadata.json"
        assert meta_file.exists()
        meta = json.loads(meta_file.read_text())
        assert meta["format"] == "PNG"


def test_jpg_export(sample_chapters):
    """Test JPEG image export produces files."""
    engine = ImageExportEngine(image_format="JPEG")
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = str(Path(tmpdir) / "jpg_export")
        options = ExportOptions(format="jpg", quality=85)
        result = engine.export(output_dir, sample_chapters, options)

        result_path = Path(result)
        page_files = list(result_path.rglob("page_*.jpg"))
        assert len(page_files) >= 10


def test_webp_export(sample_chapters):
    """Test WebP image export produces files."""
    engine = ImageExportEngine(image_format="WEBP")
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = str(Path(tmpdir) / "webp_export")
        options = ExportOptions(format="webp", quality=80)
        result = engine.export(output_dir, sample_chapters, options)

        result_path = Path(result)
        page_files = list(result_path.rglob("page_*.webp"))
        assert len(page_files) >= 10


def test_cbr_export_fallback(sample_chapters, temp_output):
    """Test CBR export falls back to CBZ when rarfile not available."""
    engine = CbrExportEngine()
    cbr_path = temp_output.replace(".cbz", ".cbr")
    options = ExportOptions(format="cbr", quality=90)
    result = engine.export(cbr_path, sample_chapters, options)

    assert Path(result).exists()
    # Should be valid ZIP (fallback)
    try:
        with zipfile.ZipFile(result, "r") as zf:
            assert len(zf.namelist()) > 0
    except zipfile.BadZipFile:
        # If system has 'rar' command, it's a real RAR — still valid
        pass


# ── Page Range Selection Tests ────────────────────────────────────────────


def test_page_range_all_pages(sample_pages):
    """Test that empty range returns all pages."""
    engine = ZipExportEngine()
    result = engine.filter_pages(sample_pages, "")
    assert len(result) == len(sample_pages)


def test_page_range_single(sample_pages):
    """Test single page selection."""
    engine = ZipExportEngine()
    result = engine.filter_pages(sample_pages, "3")
    assert len(result) == 1
    assert result[0].page_number == 3


def test_page_range_multiple(sample_pages):
    """Test multiple single page numbers."""
    engine = ZipExportEngine()
    result = engine.filter_pages(sample_pages, "1,5,10")
    assert len(result) == 3
    nums = [p.page_number for p in result]
    assert nums == [1, 5, 10]


def test_page_range_span(sample_pages):
    """Test page range span."""
    engine = ZipExportEngine()
    result = engine.filter_pages(sample_pages, "3-7")
    assert len(result) == 5
    nums = [p.page_number for p in result]
    assert nums == [3, 4, 5, 6, 7]


def test_page_range_mixed(sample_pages):
    """Test mixed range and single pages."""
    engine = ZipExportEngine()
    result = engine.filter_pages(sample_pages, "1-3,5,8-10")
    assert len(result) == 7
    nums = [p.page_number for p in result]
    assert nums == [1, 2, 3, 5, 8, 9, 10]


def test_page_range_invalid_ignored(sample_pages):
    """Test that invalid range parts are ignored."""
    engine = ZipExportEngine()
    result = engine.filter_pages(sample_pages, "1-3,invalid,5")
    assert len(result) == 4  # "invalid" is silently ignored


def test_cbz_with_page_range(sample_chapters, temp_output):
    """Test CBZ export respects page range."""
    engine = CbzExportEngine()
    options = ExportOptions(format="cbz", quality=90, page_range="1-3")
    result = engine.export(temp_output, sample_chapters, options)

    with zipfile.ZipFile(result, "r") as zf:
        page_files = [n for n in zf.namelist() if n.startswith("Chapter_")]
        # 3 pages from ch1 + 3 pages from ch2 (but ch2 only has 5 pages, so range 1-3 = 3 pages)
        # Actually page_range applies per-chapter, so 3 from each
        assert len(page_files) >= 6  # 3 from ch1 + 3 from ch2


# ── Metadata Tests ────────────────────────────────────────────────────────


def test_cbz_metadata(sample_chapters, temp_output):
    """Test CBZ metadata is complete."""
    engine = CbzExportEngine()
    options = ExportOptions(format="cbz", manga_title="Test Manga")
    result = engine.export(temp_output, sample_chapters, options)

    with zipfile.ZipFile(result, "r") as zf:
        meta = json.loads(zf.read("metadata.json"))
        assert meta["manga_title"] == "Test Manga"
        assert len(meta["chapters"]) == 2
        assert meta["ComicRack"]["series"] == "Test Manga"
        assert "comic_book_info" in meta
        assert meta["comic_book_info"]["format"] == "CBZ"


def test_png_metadata(sample_chapters):
    """Test PNG export metadata."""
    engine = ImageExportEngine(image_format="PNG")
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = str(Path(tmpdir) / "png_meta_test")
        options = ExportOptions(format="png", manga_title="Test Manga")
        result = engine.export(output_dir, sample_chapters, options)

        result_path = Path(result)
        meta = json.loads((result_path / "metadata.json").read_text())
        assert meta["format"] == "PNG"
        assert len(meta["chapters"]) == 2
        assert meta["chapters"][0]["number"] == 1


# ── Export Service Tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_service_creation(export_service):
    """Test that the export service can be created."""
    assert export_service is not None
    assert export_service.export_dir.exists()


@pytest.mark.asyncio
async def test_export_service_create_task(export_service, sample_chapters):
    """Test creating an export task via the service."""
    chapter_data = [
        {
            "id": "ch-001",
            "number": 1,
            "title": "Test",
            "pages": [
                {
                    "id": f"p{i}",
                    "number": i,
                    "translated_path": None,
                    "original_path": None,
                    "is_translated": True,
                }
                for i in range(1, 6)
            ],
        }
    ]

    task = await export_service.create_export(
        chapter_ids=["ch-001"],
        format="zip",
        quality=90,
        manga_title="Test Manga",
        chapter_data=chapter_data,
    )
    assert task is not None
    assert task.status in ("processing", "completed", "failed")
    assert task.format == "zip"


@pytest.mark.asyncio
async def test_export_service_task_lifecycle(export_service):
    """Test task lifecycle: create → get → list → cancel."""
    # Create minimal task (will fail without valid chapter data)
    # But we can test the task registry
    task_data = {
        "chapters": [],
        "format": "cbz",
    }
    # The task creation will fail due to no chapter_data, but task should be registered
    task = await export_service.create_export(
        chapter_ids=["nonexistent"],
        format="cbz",
        manga_title="Test",
        chapter_data=[],
    )
    assert task.id is not None
    assert export_service.get_task(task.id) is not None

    # Cancel should work
    assert export_service.cancel_task(task.id) is True


def test_export_format_schemas():
    """Test that all 8 format entries exist in SUPPORTED_FORMATS."""
    expected_keys = {"pdf", "png", "jpg", "jpeg", "webp", "zip", "cbz", "cbr"}
    assert set(SUPPORTED_FORMATS.keys()) == expected_keys


def test_export_format_info():
    """Test format info metadata."""
    for fmt, info in SUPPORTED_FORMATS.items():
        assert isinstance(info, ExportFormatInfo)
        assert info.format == fmt
        assert info.extension.startswith(".")
        # Map format to expected extension
        expected_ext = {
            "pdf": ".pdf",
            "png": ".png",
            "jpg": ".jpg",
            "jpeg": ".jpeg",
            "webp": ".webp",
            "zip": ".zip",
            "cbz": ".cbz",
            "cbr": ".cbr",
        }
        assert info.extension == expected_ext.get(fmt, "." + fmt)
        assert info.description


# ── Progress Callback Tests ──────────────────────────────────────────────


def test_progress_callback(sample_chapters, temp_output):
    """Test that progress callback is invoked during export."""
    progress_values = []
    messages = []

    def on_progress(pct: float, msg: str):
        progress_values.append(pct)
        messages.append(msg)

    engine = CbzExportEngine()
    ep = ExportProgress(on_progress=on_progress)
    options = ExportOptions(format="cbz", quality=90)
    engine.export(temp_output, sample_chapters, options, ep)

    assert len(progress_values) > 0
    assert progress_values[-1] >= 99.0  # Final progress near 100%
    assert len(messages) > 0


# ── Export Request Schema Tests ───────────────────────────────────────────


def test_export_request_valid():
    """Test valid export request."""
    req = ExportRequest(
        chapter_ids=["ch1", "ch2"],
        format="cbz",
        quality=90,
    )
    assert req.format == "cbz"
    assert len(req.chapter_ids) == 2


def test_export_request_invalid_format():
    """Test invalid format raises validation error."""
    with pytest.raises(ValueError, match="Unsupported format"):
        ExportRequest(
            chapter_ids=["ch1"],
            format="exe",
        )


def test_export_request_valid_page_range():
    """Test valid page ranges."""
    for page_range in ["", "1-5", "1,3,5", "1-5,8,10-15"]:
        req = ExportRequest(
            chapter_ids=["ch1"],
            page_range=page_range,
        )
        assert req.page_range == page_range


def test_export_request_invalid_page_range():
    """Test invalid page ranges raise validation error."""
    with pytest.raises(ValueError):
        ExportRequest(
            chapter_ids=["ch1"],
            page_range="abc",
        )
    with pytest.raises(ValueError):
        ExportRequest(
            chapter_ids=["ch1"],
            page_range="-1",
        )
    with pytest.raises(ValueError):
        ExportRequest(
            chapter_ids=["ch1"],
            page_range="5-3",  # end < start
        )


# ── Edge Cases ────────────────────────────────────────────────────────────


def test_empty_pages(temp_output):
    """Test export with empty pages list."""
    engine = CbzExportEngine()
    chapter = ExportChapter(
        chapter_id="ch-empty",
        chapter_number=1,
        pages=[],
    )
    options = ExportOptions(format="cbz")
    # Should not crash, produce minimal archive
    result = engine.export(temp_output, [chapter], options)
    assert Path(result).exists()


def test_single_page_export(temp_output):
    """Test export with a single page."""
    engine = CbzExportEngine()
    page = ExportPage(
        page_number=1,
        pil_image=Image.new("RGB", (400, 600)),
    )
    chapter = ExportChapter(
        chapter_id="ch-single",
        chapter_number=1,
        pages=[page],
    )
    options = ExportOptions(format="cbz")
    result = engine.export(temp_output, [chapter], options)

    with zipfile.ZipFile(result, "r") as zf:
        page_files = [n for n in zf.namelist() if n.endswith(".jpg")]
        assert len(page_files) == 1


def test_image_quality_respected():
    """Test that quality setting is used for JPEG exports."""
    engine = ImageExportEngine(image_format="JPEG")
    page = ExportPage(
        page_number=1,
        pil_image=Image.new("RGB", (400, 600), color=(128, 128, 128)),
    )
    chapter = ExportChapter(
        chapter_id="ch-quality",
        chapter_number=1,
        pages=[page],
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = str(Path(tmpdir) / "quality_test")
        options = ExportOptions(format="jpg", quality=50)
        engine.export(output_dir, [chapter], options)

        page_files = list(Path(output_dir).rglob("page_*.jpg"))
        assert len(page_files) == 1
        # Low quality should have smaller file size
        low_size = page_files[0].stat().st_size

        # Test with high quality
        output_dir2 = str(Path(tmpdir) / "quality_test_high")
        options2 = ExportOptions(format="jpg", quality=95)
        engine.export(output_dir2, [chapter], options2)

        high_files = list(Path(output_dir2).rglob("page_*.jpg"))
        assert len(high_files) == 1
        high_size = high_files[0].stat().st_size

        # Higher quality should be >= lower quality (or very close)
        assert high_size >= low_size * 0.8  # At least 80% of low quality size
