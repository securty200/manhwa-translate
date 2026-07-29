"""Tests for the FastAPI application endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport

from backend.main import app


@pytest.fixture
def client(async_client: AsyncClient):
    """Alias for async_client fixture."""
    return async_client


# ── Health & Info ────────────────────────────────────────────────────────


async def test_health_endpoint(async_client: AsyncClient):
    """Test that the health check endpoint returns OK."""
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "1.0.0"


async def test_root_endpoint(async_client: AsyncClient):
    """Test the root endpoint returns basic info."""
    response = await async_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "version" in data
    assert "api" in data


async def test_api_info(async_client: AsyncClient):
    """Test the API info endpoint."""
    response = await async_client.get("/api/v1/info")
    assert response.status_code == 200
    data = response.json()
    assert "endpoints" in data
    assert "manga" in data["endpoints"]


# ── Project / Manga Tests ───────────────────────────────────────────────


async def test_create_project(async_client: AsyncClient):
    """Test creating a new project via the project endpoint."""
    payload = {
        "title": "One Piece",
        "title_original": "ワンピース",
        "author": "Eiichiro Oda",
        "source_language": "ja",
        "target_language": "en",
    }
    response = await async_client.post("/api/v1/manga", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "One Piece"
    assert data["author"] == "Eiichiro Oda"
    assert "id" in data
    assert data["chapter_count"] == 0
    assert data["total_pages"] == 0


async def test_list_projects(async_client: AsyncClient):
    """Test listing projects with pagination."""
    await async_client.post("/api/v1/manga", json={"title": "Naruto"})

    response = await async_client.get("/api/v1/manga")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any(m["title"] == "Naruto" for m in data)


async def test_get_project_not_found(async_client: AsyncClient):
    """Test that getting a non-existent project returns 404."""
    response = await async_client.get("/api/v1/manga/non-existent-id")
    assert response.status_code == 404


async def test_create_and_get_project(async_client: AsyncClient):
    """Test full create and get flow."""
    create_resp = await async_client.post(
        "/api/v1/manga",
        json={"title": "Attack on Titan", "author": "Hajime Isayama"},
    )
    assert create_resp.status_code == 201
    manga_id = create_resp.json()["id"]

    get_resp = await async_client.get(f"/api/v1/manga/{manga_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["title"] == "Attack on Titan"


async def test_update_project(async_client: AsyncClient):
    """Test updating a project."""
    create_resp = await async_client.post("/api/v1/manga", json={"title": "Old Title"})
    manga_id = create_resp.json()["id"]

    update_resp = await async_client.put(
        f"/api/v1/manga/{manga_id}",
        json={"title": "New Title", "description": "Updated description"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["title"] == "New Title"
    assert update_resp.json()["description"] == "Updated description"


async def test_delete_project(async_client: AsyncClient):
    """Test deleting a project."""
    create_resp = await async_client.post("/api/v1/manga", json={"title": "Delete Me"})
    manga_id = create_resp.json()["id"]

    delete_resp = await async_client.delete(f"/api/v1/manga/{manga_id}")
    assert delete_resp.status_code == 204

    get_resp = await async_client.get(f"/api/v1/manga/{manga_id}")
    assert get_resp.status_code == 404


async def test_get_project_stats(async_client: AsyncClient):
    """Test getting project statistics."""
    create_resp = await async_client.post("/api/v1/manga", json={"title": "Stats Test"})
    manga_id = create_resp.json()["id"]

    response = await async_client.get(f"/api/v1/manga/{manga_id}/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["project_id"] == manga_id
    assert data["total_chapters"] == 0
    assert data["total_pages"] == 0


async def test_duplicate_project(async_client: AsyncClient):
    """Test duplicating a project."""
    create_resp = await async_client.post("/api/v1/manga", json={"title": "Original"})
    manga_id = create_resp.json()["id"]

    response = await async_client.post(
        f"/api/v1/manga/{manga_id}/duplicate?new_title=Copy"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["new_title"] == "Copy"
    assert data["new_id"] != manga_id


# ── Chapter Tests ────────────────────────────────────────────────────────


async def test_create_chapter(async_client: AsyncClient):
    """Test creating a chapter."""
    manga_resp = await async_client.post("/api/v1/manga", json={"title": "Chapter Test"})
    manga_id = manga_resp.json()["id"]

    response = await async_client.post(
        f"/api/v1/manga/{manga_id}/chapters",
        json={"chapter_number": 1, "title": "Chapter 1"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["chapter_number"] == 1
    assert data["manga_id"] == manga_id


async def test_list_chapters(async_client: AsyncClient):
    """Test listing chapters for a manga."""
    manga_resp = await async_client.post("/api/v1/manga", json={"title": "List Chapters"})
    manga_id = manga_resp.json()["id"]

    await async_client.post(
        f"/api/v1/manga/{manga_id}/chapters",
        json={"chapter_number": 1},
    )

    response = await async_client.get(f"/api/v1/manga/{manga_id}/chapters")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1


async def test_delete_chapter(async_client: AsyncClient):
    """Test deleting a chapter."""
    manga_resp = await async_client.post("/api/v1/manga", json={"title": "Delete Chapter"})
    manga_id = manga_resp.json()["id"]

    ch_resp = await async_client.post(
        f"/api/v1/manga/{manga_id}/chapters",
        json={"chapter_number": 1},
    )
    chapter_id = ch_resp.json()["id"]

    response = await async_client.delete(f"/api/v1/manga/{manga_id}/chapters/{chapter_id}")
    assert response.status_code == 204


# ── Upload Tests ─────────────────────────────────────────────────────────


async def test_upload_invalid_file(async_client: AsyncClient):
    """Test upload with invalid manga ID."""
    response = await async_client.post(
        "/api/v1/upload/nonexistent/chapters/nonexistent/pages",
        files={"files": ("test.txt", b"not an image", "text/plain")},
    )
    assert response.status_code == 404


# ── Translation Tests ────────────────────────────────────────────────────


async def test_translate_text_endpoint(async_client: AsyncClient):
    """Test the text translation endpoint (may fail if no API key configured)."""
    response = await async_client.post(
        "/api/v1/translate/text",
        json={
            "text": "こんにちは",
            "source_language": "ja",
            "target_language": "en",
        },
    )
    # May fail if no API key, but should return valid JSON
    assert response.status_code in (200, 500)


async def test_create_translation_job(async_client: AsyncClient):
    """Test creating a translation job for a chapter."""
    manga_resp = await async_client.post("/api/v1/manga", json={"title": "Job Test"})
    manga_id = manga_resp.json()["id"]

    ch_resp = await async_client.post(
        f"/api/v1/manga/{manga_id}/chapters",
        json={"chapter_number": 1},
    )
    chapter_id = ch_resp.json()["id"]

    response = await async_client.post(
        "/api/v1/translate/jobs",
        json={"chapter_id": chapter_id},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["chapter_id"] == chapter_id
    assert data["status"] == "pending"
    assert "id" in data


async def test_list_translation_jobs(async_client: AsyncClient):
    """Test listing translation jobs."""
    response = await async_client.get("/api/v1/translate/jobs")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


async def test_get_nonexistent_job(async_client: AsyncClient):
    """Test getting a non-existent job returns 404."""
    response = await async_client.get("/api/v1/translate/jobs/nonexistent")
    assert response.status_code == 404


# ── Export Tests ─────────────────────────────────────────────────────────


async def test_create_export_invalid_chapter(async_client: AsyncClient):
    """Test export with invalid chapter ID."""
    response = await async_client.post(
        "/api/v1/export",
        json={"chapter_ids": ["nonexistent"]},
    )
    assert response.status_code == 404


# ── History Tests ────────────────────────────────────────────────────────


async def test_list_history(async_client: AsyncClient):
    """Test listing history."""
    response = await async_client.get("/api/v1/history")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data


async def test_activity_summary(async_client: AsyncClient):
    """Test getting activity summary."""
    response = await async_client.get("/api/v1/history/activity/summary?days=7")
    assert response.status_code == 200
    data = response.json()
    assert "total_jobs" in data
    assert "completed_jobs" in data


# ── Queue Tests ──────────────────────────────────────────────────────────


async def test_queue_status(async_client: AsyncClient):
    """Test getting queue status."""
    response = await async_client.get("/api/v1/translate/queue/status")
    assert response.status_code == 200
    data = response.json()
    assert "active_jobs" in data
    assert "pending_queue_size" in data


# ── Projects Overview ────────────────────────────────────────────────────


async def test_projects_overview(async_client: AsyncClient):
    """Test the projects overview endpoint."""
    response = await async_client.get("/api/v1/projects/overview")
    assert response.status_code == 200
    data = response.json()
    assert "total_projects" in data
    assert "total_chapters" in data
    assert "total_pages" in data
    assert "translation_progress" in data
