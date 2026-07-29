"""Pydantic schemas for the enhanced translation module."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class TranslateRequest(BaseModel):
    """Request to translate a single text string."""

    text: str = Field(..., min_length=1, description="Text to translate")
    source_language: str = Field(
        default="auto", max_length=10,
        description="Source language code ('auto' for auto-detect)",
    )
    target_language: str = Field(default="en", max_length=10, description="Target language code")
    context: Optional[str] = Field(None, description="Manga context (genre, setting, characters)")


class TranslateResponse(BaseModel):
    """Response for a single translation."""

    translated_text: str = Field(..., description="Translated text")
    source_language: str = Field("", description="Detected or provided source language")
    target_language: str = Field("en", description="Target language")
    confidence: float = Field(0.0, description="Translation confidence")
    engine_name: str = Field("", description="Translation engine used")
    processing_time_ms: float = Field(0.0, description="Processing time")
    detected_source_language: str = Field("", description="Auto-detected source language")


class BatchTranslateRequest(BaseModel):
    """Request to translate multiple text strings."""

    texts: list[str] = Field(..., min_length=1, max_length=100, description="Texts to translate")
    source_language: str = Field(default="auto", description="Source language code ('auto' for auto-detect)")
    target_language: str = Field(default="en", description="Target language code")
    context: Optional[str] = Field(None, description="Manga context")


class BatchTranslateResponse(BaseModel):
    """Response for batch translation."""

    translations: list[TranslateResponse] = Field(default_factory=list)
    total_time_ms: float = Field(0.0, description="Total processing time")
    engine_used: str = Field("", description="Engine used")
    source_language_detected: str = Field("", description="Auto-detected source language")


class PageTranslationRequest(BaseModel):
    """Request to translate all bubbles on a page."""

    page_id: str = Field("", description="Page ID (from database)")
    bubbles: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of bubbles: [{'id': str, 'original_text': str, 'bubble_type': str}, ...]",
    )
    source_language: str = Field(default="auto", description="Source language code")
    target_language: str = Field(default="en", description="Target language code")
    manga_context: Optional[str] = Field(None, description="Manga context for the translation")
    preserve_names: bool = Field(default=True, description="Preserve character names")
    preserve_emotions: bool = Field(default=True, description="Preserve emotional tone")


class PageTranslationResponse(BaseModel):
    """Response for page-level translation."""

    page_id: str = Field("", description="Page ID")
    bubbles: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Translated bubbles: [{'id': ..., 'original_text': ..., 'translated_text': ...}]",
    )
    total_time_ms: float = Field(0.0, description="Total processing time")
    engine_used: str = Field("", description="Engine used")
    source_language_detected: str = Field("", description="Auto-detected source language")


class EngineInfo(BaseModel):
    """Information about a translation engine."""

    name: str = Field(..., description="Engine name")
    type: str = Field(..., description="Engine type: 'offline' or 'cloud'")
    available: bool = Field(False, description="Whether the engine is available")
    languages: Optional[list[str]] = Field(None, description="Supported language codes")
    requires_api_key: bool = Field(False, description="Whether an API key is required")
    is_configured: bool = Field(False, description="Whether the engine is properly configured")


class TranslationStats(BaseModel):
    """Statistics about translations performed."""

    total_translations: int = Field(0, description="Total translations performed")
    by_engine: dict[str, int] = Field(default_factory=dict, description="Count by engine")
    by_language_pair: dict[str, int] = Field(default_factory=dict, description="Count by language pair")
    total_chars_translated: int = Field(0, description="Total characters translated")
    avg_processing_time_ms: float = Field(0.0, description="Average processing time")
