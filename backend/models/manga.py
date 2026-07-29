"""SQLAlchemy ORM models for manga data."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.session import Base


class JobStatus(str, PyEnum):
    """Possible states of a translation job."""

    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Manga(Base):
    """A manga series."""

    __tablename__ = "mangas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title_original: Mapped[str] = mapped_column(String(255), nullable=True)
    author: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    artist: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cover_image_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    source_language: Mapped[str] = mapped_column(String(10), default="ja")
    target_language: Mapped[str] = mapped_column(String(10), default="en")
    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    chapters: Mapped[list["Chapter"]] = relationship("Chapter", back_populates="manga", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Manga(id={self.id!r}, title={self.title!r})>"


class Chapter(Base):
    """A chapter within a manga series."""

    __tablename__ = "chapters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    manga_id: Mapped[str] = mapped_column(ForeignKey("mangas.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_number: Mapped[float] = mapped_column(Float, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    is_translated: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    manga: Mapped["Manga"] = relationship("Manga", back_populates="chapters")
    pages: Mapped[list["Page"]] = relationship("Page", back_populates="chapter", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Chapter(id={self.id!r}, number={self.chapter_number})>"


class Page(Base):
    """A single page (image) within a chapter."""

    __tablename__ = "pages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    chapter_id: Mapped[str] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    original_image_path: Mapped[str] = mapped_column(String(512), nullable=False)
    translated_image_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_translated: Mapped[bool] = mapped_column(Boolean, default=False)
    processing_time_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    chapter: Mapped["Chapter"] = relationship("Chapter", back_populates="pages")
    bubbles: Mapped[list["Bubble"]] = relationship("Bubble", back_populates="page", cascade="all, delete-orphan")
    segments: Mapped[list["TranslationSegment"]] = relationship(
        "TranslationSegment", back_populates="page", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Page(id={self.id!r}, page={self.page_number})>"


class Bubble(Base):
    """A detected speech/thought bubble on a page.

    Stores precise polygon coordinates for downstream use by
    inpainting (mask-based removal) and rendering (text wrapping).
    """

    __tablename__ = "bubbles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    page_id: Mapped[str] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), nullable=False, index=True)
    bubble_type: Mapped[str] = mapped_column(String(50), default="speech")
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    width: Mapped[float] = mapped_column(Float, nullable=False)
    height: Mapped[float] = mapped_column(Float, nullable=False)
    polygon_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=None)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    reading_order: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    original_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    translated_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_translated: Mapped[bool] = mapped_column(Boolean, default=False)
    rotation: Mapped[float] = mapped_column(Float, default=0.0)
    detector_engine: Mapped[str] = mapped_column(String(50), default="")
    has_precise_mask: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    page: Mapped["Page"] = relationship("Page", back_populates="bubbles")

    def __repr__(self) -> str:
        return f"<Bubble(id={self.id!r}, type={self.bubble_type})>"

    @property
    def polygon(self) -> list[tuple[float, float]]:
        """Get polygon as list of (x,y) tuples from stored JSON."""
        if not self.polygon_json:
            return [(self.x, self.y), (self.x + self.width, self.y),
                    (self.x + self.width, self.y + self.height), (self.x, self.y + self.height)]
        return [(p[0], p[1]) for p in self.polygon_json]


class TranslationJob(Base):
    """A job that tracks the translation process for a set of pages."""

    __tablename__ = "translation_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    chapter_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), default=JobStatus.PENDING, index=True
    )
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    total_pages: Mapped[int] = mapped_column(Integer, default=0)
    completed_pages: Mapped[int] = mapped_column(Integer, default=0)
    failed_pages: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_language: Mapped[str] = mapped_column(String(10), default="ja")
    target_language: Mapped[str] = mapped_column(String(10), default="en")
    options_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    segments: Mapped[list["TranslationSegment"]] = relationship(
        "TranslationSegment", back_populates="job", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<TranslationJob(id={self.id!r}, status={self.status})>"


class TranslationSegment(Base):
    """Individual translation segment within a job (a single bubble's translation)."""

    __tablename__ = "translation_segments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(
        ForeignKey("translation_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_id: Mapped[str] = mapped_column(
        ForeignKey("pages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bubble_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("bubbles.id", ondelete="SET NULL"), nullable=True
    )
    original_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    translated_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ocr_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    source_language: Mapped[str] = mapped_column(String(10), default="ja")
    target_language: Mapped[str] = mapped_column(String(10), default="en")
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.PENDING)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    processing_time_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    job: Mapped["TranslationJob"] = relationship("TranslationJob", back_populates="segments")
    page: Mapped["Page"] = relationship("Page", back_populates="segments")

    def __repr__(self) -> str:
        return f"<TranslationSegment(id={self.id!r}, status={self.status})>"
