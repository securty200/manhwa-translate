"""Global error handling middleware and custom exceptions."""

from __future__ import annotations

import logging
import traceback
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.config import settings

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base application error with status code and detail."""

    def __init__(
        self,
        detail: str = "An error occurred",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code: str = "internal_error",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.detail = detail
        self.status_code = status_code
        self.error_code = error_code
        self.metadata = metadata or {}
        super().__init__(self.detail)


class NotFoundError(AppError):
    """Resource not found error."""

    def __init__(self, resource: str = "Resource", resource_id: str | None = None) -> None:
        detail = f"{resource} not found"
        if resource_id:
            detail = f"{resource} with id '{resource_id}' not found"
        super().__init__(
            detail=detail,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="not_found",
        )


class ValidationError(AppError):
    """Data validation error."""

    def __init__(self, detail: str = "Validation failed") -> None:
        super().__init__(
            detail=detail,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="validation_error",
        )


class ConflictError(AppError):
    """Resource conflict error (e.g., duplicate)."""

    def __init__(self, detail: str = "Resource conflict") -> None:
        super().__init__(
            detail=detail,
            status_code=status.HTTP_409_CONFLICT,
            error_code="conflict",
        )


class JobError(AppError):
    """Translation job error."""

    def __init__(self, detail: str = "Job processing failed", job_id: str | None = None) -> None:
        metadata = {"job_id": job_id} if job_id else None
        super().__init__(
            detail=detail,
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="job_error",
            metadata=metadata,
        )


class FileTooLargeError(AppError):
    """File upload size exceeded error."""

    def __init__(self, max_size_mb: float = 50.0) -> None:
        super().__init__(
            detail=f"File too large. Maximum size is {max_size_mb:.0f} MB",
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            error_code="file_too_large",
        )


class UnsupportedFormatError(AppError):
    """Unsupported file format error."""

    def __init__(self, format: str = "") -> None:
        super().__init__(
            detail=f"Unsupported format: {format}" if format else "Unsupported file format",
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            error_code="unsupported_format",
        )


def setup_error_handlers(app: FastAPI) -> None:
    """Register global exception handlers on the FastAPI app."""

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        """Handle custom application errors."""
        logger.warning(
            "AppError: %s (code=%s, status=%d, path=%s)",
            exc.detail, exc.error_code, exc.status_code, request.url.path,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail,
                "error_code": exc.error_code,
                "metadata": exc.metadata,
                "path": str(request.url.path),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Handle Pydantic validation errors with detailed messages."""
        errors = []
        for error in exc.errors():
            field = ".".join(str(loc) for loc in error.get("loc", []))
            msg = error.get("msg", "Invalid value")
            errors.append({"field": field, "message": msg})

        logger.warning(
            "Validation error: %s (path=%s)", errors, request.url.path,
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": "Validation failed",
                "error_code": "validation_error",
                "errors": errors,
                "path": str(request.url.path),
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Handle unhandled exceptions (500)."""
        error_id = str(hash(str(exc)))[:8] if settings.DEBUG else "unknown"
        logger.error(
            "Unhandled exception [%s]: %s\n%s",
            error_id, exc, traceback.format_exc(),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "An unexpected error occurred",
                "error_code": "internal_error",
                "error_id": error_id,
                "path": str(request.url.path),
                "debug": str(exc) if settings.DEBUG else None,
            },
        )

    logger.info("Error handlers registered")
