"""Application configuration."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Global application settings loaded from environment variables."""

    # ── Project ──────────────────────────────────────────────────────────
    PROJECT_NAME: str = "AI Manga Translator"
    VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENV: Literal["development", "production", "testing"] = "development"

    # ── Paths ────────────────────────────────────────────────────────────
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    ASSETS_DIR: Path = BASE_DIR / "assets"
    FONTS_DIR: Path = ASSETS_DIR / "fonts"
    MODELS_DIR: Path = BASE_DIR / "models"
    CACHE_DIR: Path = BASE_DIR / "cache"
    LOGS_DIR: Path = BASE_DIR / "logs"

    # ── Server ───────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # ── Database ─────────────────────────────────────────────────────────
    DATABASE_URL: Optional[str] = None
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_ECHO: bool = False

    # ── Redis / Cache ────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_POOL_SIZE: int = 10
    REDIS_CONNECT_TIMEOUT: float = 3.0
    CACHE_TTL_SECONDS: int = 3600

    # ── OCR ──────────────────────────────────────────────────────────────
    # Deprecated: kept for backward compatibility. Use OCR_ENGINE_PRIORITY.
    OCR_ENGINE: str = "paddleocr"
    OCR_ENGINE_PRIORITY: list[str] = ["paddleocr", "easyocr", "tesseract"]
    OCR_DEVICE: Literal["cpu", "cuda", "mps"] = "cpu"
    OCR_BATCH_SIZE: int = 4
    OCR_AUTO_CHOOSE_BEST: bool = True
    OCR_LANGUAGES: list[str] = ["ja", "en"]
    OCR_CONFIDENCE_THRESHOLD: float = 0.3

    # ── Translation ──────────────────────────────────────────────────────
    # Deprecated: kept for backward compatibility. Use TRANSLATOR_ENGINE_PRIORITY.
    TRANSLATOR_BACKEND: str = "openai"
    TRANSLATOR_ENGINE_PRIORITY: list[str] = [
        "openai", "claude", "gemini",
        "deepl", "google", "libre",
        "ollama",
        "nllb", "m2m100", "marianmt", "argos",
    ]
    TRANSLATOR_ENGINE_TYPE: str = "auto"  # auto, offline_only, cloud_only
    TRANSLATOR_AUTO_DETECT: bool = True
    TRANSLATOR_PRESERVE_NAMES: bool = True
    TRANSLATOR_PRESERVE_EMOTIONS: bool = True
    TRANSLATOR_BATCH_CONCURRENCY: int = 5
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-3-haiku-20240307"
    GOOGLE_API_KEY: str = ""
    DEEPL_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_MODEL: str = "deepseek-chat"
    LIBRETRANSLATE_URL: str = "https://libretranslate.com"
    LIBRETRANSLATE_API_KEY: str = ""
    OLLAMA_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2"
    LOCAL_MODEL_PATH: str = ""
    NLLB_MODEL_NAME: str = "facebook/nllb-200-distilled-600M"
    M2M100_MODEL_NAME: str = "facebook/m2m100_418M"
    MAX_TEXT_LENGTH: int = 5000
    TRANSLATION_TIMEOUT_SECONDS: int = 30

    # ── Text / Bubble Detector ───────────────────────────────────────────
    # Deprecated: kept for backward compatibility. Use DETECTOR_ENGINE_PRIORITY.
    DETECTOR_MODEL: Literal["craft", "dbnet", "yolo"] = "yolo"
    DETECTOR_ENGINE_PRIORITY: list[str] = ["yolo", "groundingdino", "sam2"]
    DETECTOR_CONFIDENCE_THRESHOLD: float = 0.3
    DETECTOR_MERGE_IOU_THRESHOLD: float = 0.5
    DETECTOR_USE_FALLBACK: bool = True
    DETECTOR_TARGET_TYPES: list[str] = [
        "speech", "thought", "narration", "sfx", "sign", "title", "poster",
    ]
    DETECTOR_YOLO_MODEL_PATH: str = ""  # Auto-resolves to models/bubble_detector.pt
    DETECTOR_SAM2_MODEL_TYPE: str = "sam2.1_tiny"
    DETECTOR_GROUNDINGDINO_MODEL_ID: str = "IDEA-Research/grounding-dino-tiny"

    # ── Inpainting ───────────────────────────────────────────────────────
    # Primary routing is now via INPAINTING_ENGINE_PRIORITY.
    # INPAINTING_MODEL is kept for backward compatibility but the
    # "sd_inpainting" option requires adding to ENGINE_REGISTRY.
    INPAINTING_MODEL: Literal["lama", "sd_inpainting"] = "lama"
    INPAINTING_DEVICE: Literal["cpu", "cuda", "mps"] = "cpu"
    INPAINTING_ENGINE_PRIORITY: list[str] = [
        "lama",
        "content_aware_fill",
        "bubble_reconstruction",
        "opencv",
        "matting_refinement",
    ]
    INPAINTING_REFINEMENT_PASSES: int = 2
    INPAINTING_DILATION_RADIUS: int = 4
    INPAINTING_COMPLEX_BG_DILATION_RADIUS: int = 8
    INPAINTING_MASK_BLUR_KERNEL: int = 5

    # ── Rendering ────────────────────────────────────────────────────────
    DEFAULT_FONT: str = "default.ttf"
    FONT_SIZE_RANGE: tuple[int, int] = (12, 48)
    MAX_BUBBLE_WIDTH_RATIO: float = 0.85
    LINE_HEIGHT_RATIO: float = 1.4
    PADDING_RATIO: float = 0.08
    # Font fallback chains
    MANGA_FONT_CHAIN: list[str] = ["manga.ttf", "manga_bold.ttf", "komika.ttf", "anime.ttf", "default.ttf"]
    SFX_FONT_CHAIN: list[str] = ["sfx_bold.ttf", "sfx.ttf", "impact.ttf", "arialbd.ttf", "default.ttf"]
    CJK_FONT_CHAIN: list[str] = ["noto-sans-cjk.ttf", "notosanscjk.ttf", "source-han-sans.ttf", "msgothic.ttc", "meiryo.ttc", "default.ttf"]
    # Rendering effects
    RENDER_ENABLE_OUTLINE: bool = True
    RENDER_ENABLE_SHADOW: bool = True
    RENDER_DEFAULT_OUTLINE_WIDTH: int = 2
    RENDER_DEFAULT_SHADOW_OFFSET_X: int = 1
    RENDER_DEFAULT_SHADOW_OFFSET_Y: int = 1
    # Vertical text (tategaki)
    RENDER_ENABLE_VERTICAL_TEXT: bool = True
    RENDER_VERTICAL_AUTO_DETECT: bool = True
    # Quality
    RENDER_POLYGON_CLIP: bool = True
    RENDER_MASK_BLUR_RADIUS: int = 2

    # ── Workers ──────────────────────────────────────────────────────────
    MAX_CONCURRENT_JOBS: int = 3
    JOB_TIMEOUT_MINUTES: int = 10
    POLL_INTERVAL_SECONDS: float = 1.0

    # ── Job Queue ────────────────────────────────────────────────────────
    JOB_MAX_RETRIES: int = 3
    JOB_RETRY_DELAY_SECONDS: float = 5.0
    QUEUE_POLL_INTERVAL: float = 0.5

    # ── Upload ───────────────────────────────────────────────────────────
    UPLOAD_MAX_FILE_SIZE_MB: int = 50
    UPLOAD_ALLOWED_EXTENSIONS: str = ".jpg,.jpeg,.png,.webp,.bmp,.tiff"
    UPLOAD_IMAGE_MAX_DIMENSION: int = 10000
    UPLOAD_COVER_MAX_WIDTH: int = 400
    UPLOAD_COVER_MAX_HEIGHT: int = 600

    # ── Export ───────────────────────────────────────────────────────────
    EXPORT_JPEG_QUALITY: int = 90
    EXPORT_MAX_CHAPTERS: int = 50
    EXPORT_CLEANUP_AGE_HOURS: int = 24
    EXPORT_DEFAULT_FORMAT: str = "cbz"
    EXPORT_SUPPORTED_FORMATS: list[str] = ["pdf", "png", "jpg", "webp", "zip", "cbz", "cbr"]
    EXPORT_PAGE_RANGE_MAX: int = 1000  # Max pages in a single export
    EXPORT_USE_PYMUPDF: bool = True  # Use PyMuPDF for better PDFs
    EXPORT_ZIP_COMPRESSION_LEVEL: int = 6  # 0-9 (ZIP_DEFLATED)

    # ── WebSocket ────────────────────────────────────────────────────────
    WS_HEARTBEAT_INTERVAL: int = 30
    WS_MAX_QUEUE_SIZE: int = 100

    # ── Performance / Caching ────────────────────────────────────────────
    # Cache limits (MB)
    CACHE_OCR_MAX_MB: int = 50
    CACHE_TRANSLATION_MAX_MB: int = 100
    CACHE_IMAGE_MAX_MB: int = 500
    CACHE_MODEL_MAX_MB: int = 1024
    CACHE_DETECTION_MAX_MB: int = 100
    # Cache TTLs (seconds)
    CACHE_OCR_TTL: int = 600  # 10 min
    CACHE_TRANSLATION_TTL: int = 3600  # 1 hour
    CACHE_IMAGE_TTL: int = 1800  # 30 min
    CACHE_DETECTION_TTL: int = 300  # 5 min
    # Cache eviction strategy
    CACHE_EVICT_BATCH_SIZE: int = 20  # Entries to evict per cycle

    # ── Profiling / Monitoring ────────────────────────────────────────────
    PROFILE_ENABLED: bool = True
    PROFILE_SNAPSHOT_INTERVAL: float = 5.0  # seconds
    PROFILE_MAX_HISTORY: int = 360  # 30 min at 5s intervals
    PROFILE_SLOW_REQUEST_MS: float = 1000.0  # Log requests slower than this
    PROFILE_MEMORY_WARN_MB: int = 1024  # Warn when memory exceeds this
    PROFILE_GC_THRESHOLD_MB: float = 50.0  # GC after requests this heavy
    ENABLE_GPU_PROFILING: bool = False  # Enable nvidia-smi monitoring

    # ── Batch Processing ──────────────────────────────────────────────────
    BATCH_OCR_SIZE: int = 4  # Pages to OCR in parallel
    BATCH_TRANSLATION_SIZE: int = 5  # Texts to translate concurrently
    BATCH_INPAINT_SIZE: int = 2  # Pages to inpaint concurrently
    BATCH_DETECTION_SIZE: int = 2  # Pages to detect concurrently
    BATCH_CHECKPOINT_INTERVAL: int = 10  # Save checkpoint every N pages
    BATCH_MAX_RETRIES: int = 3
    BATCH_RETRY_BACKOFF: float = 1.5  # Exponential backoff multiplier

    # ── Memory Management ─────────────────────────────────────────────────
    MAX_IMAGE_CACHE_PAGES: int = 20  # Max pages held in image cache
    MAX_BUBBLES_PER_PAGE: int = 200  # Safety limit for bubble detection
    MAX_OCR_REGIONS_PER_PAGE: int = 100  # Safety limit for OCR results
    STREAM_CHUNK_SIZE: int = 8192  # Bytes per chunk for streaming
    LAZY_LOAD_IMAGES: bool = True  # Only load images when needed
    GC_INTERVAL_SECONDS: int = 300  # Force GC every N seconds

    # ── GPU / Hardware Acceleration ───────────────────────────────────────
    CUDA_ENABLED: bool = False
    CUDA_DEVICE_ID: int = 0
    CUDA_MEMORY_FRACTION: float = 0.8  # Max GPU memory to use
    ENABLE_TORCH_COMPILE: bool = False  # torch.compile for model acceleration
    TORCH_NUM_THREADS: int = 4  # CPU threads for PyTorch
    ENABLE_ONNX: bool = True  # Use ONNX runtime when available
    ONNX_EXECUTION_PROVIDERS: list[str] = ["CPUExecutionProvider"]

    # ── Concurrency ───────────────────────────────────────────────────────
    MAX_THREAD_POOL_WORKERS: int = 8
    MAX_ASYNC_SEMAPHORE: int = 16
    CONNECTION_POOL_MAX_SIZE: int = 20
    HTTP_KEEP_ALIVE_TIMEOUT: int = 30

    # ── Logging ──────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_MAX_BYTES: int = 10 * 1024 * 1024  # 10 MB
    LOG_BACKUP_COUNT: int = 5
    LOG_PERFORMANCE_METRICS: bool = True  # Log perf metrics to separate file

    # ── Streaming ─────────────────────────────────────────────────────────
    STREAM_ENABLE: bool = True
    STREAM_BUFFER_SIZE: int = 65536  # 64KB buffer for file streaming
    STREAM_MAX_FILE_SIZE_MB: int = 2048  # Max file size for streaming (2GB)
    EXPORT_STREAM_CHUNK_SIZE: int = 1048576  # 1MB chunks for export downloads

    @property
    def effective_database_url(self) -> str:
        """Return the effective database URL.

        Uses DATABASE_URL from env if set, otherwise builds a safe path.
        Handles Unicode paths by encoding them properly for SQLite.
        """
        if self.DATABASE_URL:
            return self.DATABASE_URL
        db_dir = self.BASE_DIR / "database"
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = db_dir / "manga_translator.db"
        safe_path = str(db_path.as_posix())
        return f"sqlite+aiosqlite:///{safe_path}"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "case_sensitive": True}


settings = Settings()

for _dir in [settings.ASSETS_DIR, settings.FONTS_DIR, settings.MODELS_DIR,
             settings.CACHE_DIR, settings.LOGS_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)
