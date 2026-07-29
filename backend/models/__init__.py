"""SQLAlchemy ORM models for the manga translator."""

from __future__ import annotations

from backend.models.manga import (
    Manga,
    Chapter,
    Page,
    Bubble,
    TranslationJob,
    TranslationSegment,
)

__all__ = [
    "Manga",
    "Chapter",
    "Page",
    "Bubble",
    "TranslationJob",
    "TranslationSegment",
]
