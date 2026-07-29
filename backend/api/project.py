"""Alternative project management API routes (simpler interface)."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.session import get_session
from backend.models.manga import Manga, Chapter, Page

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/overview")
async def get_projects_overview(
    session: AsyncSession = Depends(get_session),
):
    """Get a high-level overview of all projects."""
    total_projects = (await session.execute(select(func.count(Manga.id)))).scalar() or 0
    total_chapters = (await session.execute(select(func.count(Chapter.id)))).scalar() or 0
    total_pages = (await session.execute(select(func.count(Page.id)))).scalar() or 0
    translated_pages = (
        await session.execute(
            select(func.count(Page.id)).where(Page.is_translated == True)
        )
    ).scalar() or 0

    # Language distribution
    lang_result = await session.execute(
        select(Manga.source_language, Manga.target_language, func.count(Manga.id))
        .group_by(Manga.source_language, Manga.target_language)
    )
    language_pairs = [
        {"source": row[0], "target": row[1], "count": row[2]}
        for row in lang_result.all()
    ]

    return {
        "total_projects": total_projects,
        "total_chapters": total_chapters,
        "total_pages": total_pages,
        "translated_pages": translated_pages,
        "translation_progress": round((translated_pages / total_pages * 100), 1) if total_pages > 0 else 0,
        "language_pairs": language_pairs,
    }
