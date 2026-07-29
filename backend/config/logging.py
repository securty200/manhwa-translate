"""Logging configuration for the application."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from backend.config import settings


def setup_logging() -> None:
    """Configure structured logging with both file and console handlers."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(settings.LOG_FORMAT))
    root_logger.addHandler(console_handler)

    # File handler with rotation
    log_file = settings.LOGS_DIR / "manga_translator.log"
    file_handler = RotatingFileHandler(
        filename=log_file,
        maxBytes=settings.LOG_MAX_BYTES,
        backupCount=settings.LOG_BACKUP_COUNT,
    )
    file_handler.setFormatter(logging.Formatter(settings.LOG_FORMAT))
    root_logger.addHandler(file_handler)

    # Set third-party log levels
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    logging.info("Logging configured. Log file: %s", log_file)
