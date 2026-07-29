"""Shared fixtures and configuration for backend tests."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# ── IMPORTANT: Set env vars BEFORE any backend imports ───────────────────
# The database URL must be set before the backend module is imported
# because the engine is created at import time.
# Using a temp file avoids Unicode path issues on Windows.
_test_db_fd, _test_db_path = tempfile.mkstemp(suffix="_test.db")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_test_db_path}"
os.environ["ENV"] = "testing"
os.environ["DEBUG"] = "false"

# Now safe to import backend modules
from backend.database.session import Base, create_tables, drop_tables


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    """Ensure tables exist before tests and clean up afterward."""
    await create_tables()
    yield
    await drop_tables()


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an async test client for the FastAPI application."""
    from backend.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def sample_manga_data():
    """Provide sample manga data for tests."""
    return {
        "title": "Test Manga",
        "title_original": "テスト漫画",
        "author": "Test Author",
        "source_language": "ja",
        "target_language": "en",
    }


@pytest.fixture
def sample_page_image():
    """Create a simple test image."""
    from PIL import Image
    return Image.new("RGB", (800, 1200), color="white")


# Cleanup temp database
def pytest_unconfigure(config):
    """Clean up temp database file after tests."""
    try:
        os.close(_test_db_fd)
    except (OSError, Exception):
        pass
    try:
        os.unlink(_test_db_path)
    except (OSError, Exception):
        pass
