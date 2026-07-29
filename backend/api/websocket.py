"""Enhanced WebSocket endpoints for real-time job progress and events."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    """Manage WebSocket connections and broadcast messages with per-job rooms."""

    def __init__(self) -> None:
        self.active_connections: dict[str, list[WebSocket]] = {}
        self.global_connections: list[WebSocket] = []

    async def connect(self, job_id: str, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection for a job."""
        await websocket.accept()
        if job_id not in self.active_connections:
            self.active_connections[job_id] = []
        self.active_connections[job_id].append(websocket)
        logger.info(
            "WS connected: job=%s (connections: %d)",
            job_id, len(self.active_connections[job_id]),
        )

    async def connect_global(self, websocket: WebSocket) -> None:
        """Accept and register a global connection (receives all events)."""
        await websocket.accept()
        self.global_connections.append(websocket)
        logger.info("WS global connected (total: %d)", len(self.global_connections))

    def disconnect(self, job_id: str, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        if job_id in self.active_connections:
            self.active_connections[job_id].remove(websocket)
            if not self.active_connections[job_id]:
                del self.active_connections[job_id]

    def disconnect_global(self, websocket: WebSocket) -> None:
        """Remove a global connection."""
        if websocket in self.global_connections:
            self.global_connections.remove(websocket)

    async def broadcast(self, job_id: str, message: dict) -> None:
        """Send a JSON message to a specific job room and global listeners."""
        # Send to job-specific room
        disconnected: list[WebSocket] = []
        if job_id in self.active_connections:
            for connection in self.active_connections[job_id]:
                if not await self._safe_send(connection, message):
                    disconnected.append(connection)
            for conn in disconnected:
                self.disconnect(job_id, conn)

        # Send to global listeners
        global_disconnected: list[WebSocket] = []
        for connection in self.global_connections:
            if not await self._safe_send(connection, message):
                global_disconnected.append(connection)
        for conn in global_disconnected:
            self.disconnect_global(conn)

    async def broadcast_all(self, message: dict) -> None:
        """Broadcast a message to all connections across all jobs."""
        all_connections: list[tuple[str, WebSocket]] = []
        for job_id, conns in self.active_connections.items():
            for conn in conns:
                all_connections.append((job_id, conn))

        for job_id, conn in all_connections:
            if not await self._safe_send(conn, message):
                self.disconnect(job_id, conn)

    async def _safe_send(self, websocket: WebSocket, message: dict) -> bool:
        """Safely send a JSON message; returns False if connection is dead."""
        try:
            await websocket.send_json(message)
            return True
        except (WebSocketDisconnect, RuntimeError, Exception) as e:
            logger.debug("WS send failed: %s", e)
            return False


manager = ConnectionManager()


# ── Event type helpers ───────────────────────────────────────────────────

def job_progress_event(
    job_id: str,
    status: str,
    progress: float,
    current_page: int = 0,
    total_pages: int = 0,
    message: str = "",
    page_id: str | None = None,
    processing_time_ms: float | None = None,
) -> dict[str, Any]:
    """Create a job progress event payload."""
    return {
        "type": "job_progress",
        "job_id": job_id,
        "status": status,
        "progress": progress,
        "current_page": current_page,
        "total_pages": total_pages,
        "message": message,
        "page_id": page_id,
        "processing_time_ms": processing_time_ms,
        "timestamp": datetime.utcnow().isoformat(),
    }


def job_completed_event(
    job_id: str,
    total_pages: int,
    total_time_ms: float,
    manga_title: str = "",
    chapter_number: float = 0,
) -> dict[str, Any]:
    """Create a job completed event payload."""
    return {
        "type": "job_completed",
        "job_id": job_id,
        "status": "completed",
        "progress": 100.0,
        "total_pages": total_pages,
        "total_time_ms": total_time_ms,
        "manga_title": manga_title,
        "chapter_number": chapter_number,
        "timestamp": datetime.utcnow().isoformat(),
    }


def job_error_event(
    job_id: str,
    error_message: str,
    page_id: str | None = None,
) -> dict[str, Any]:
    """Create a job error event payload."""
    return {
        "type": "job_error",
        "job_id": job_id,
        "status": "error",
        "error_message": error_message,
        "page_id": page_id,
        "timestamp": datetime.utcnow().isoformat(),
    }


def page_processed_event(
    job_id: str,
    page_number: int,
    processing_time_ms: float,
    bubbles_detected: int = 0,
) -> dict[str, Any]:
    """Create a page processed event payload."""
    return {
        "type": "page_processed",
        "job_id": job_id,
        "page_number": page_number,
        "processing_time_ms": processing_time_ms,
        "bubbles_detected": bubbles_detected,
        "timestamp": datetime.utcnow().isoformat(),
    }


def bubble_translated_event(
    job_id: str,
    page_number: int,
    bubble_index: int,
    original_text: str = "",
    translated_text: str = "",
) -> dict[str, Any]:
    """Create a bubble translated event payload."""
    return {
        "type": "bubble_translated",
        "job_id": job_id,
        "page_number": page_number,
        "bubble_index": bubble_index,
        "original_text_preview": original_text[:50] + "..." if len(original_text) > 50 else original_text,
        "translated_text_preview": translated_text[:50] + "..." if len(translated_text) > 50 else translated_text,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── WebSocket endpoints ─────────────────────────────────────────────────


@router.websocket("/progress/{job_id}")
async def job_progress_websocket(websocket: WebSocket, job_id: str):
    """WebSocket endpoint for real-time progress updates on a specific job.

    The server sends typed JSON events:
    - job_progress: progress percentage and current page
    - job_completed: job finished successfully
    - job_error: error occurred
    - page_processed: individual page done
    - bubble_translated: individual bubble done
    - heartbeat: keep-alive ping

    Client can send:
    - {"type": "ping"} → server responds with {"type": "pong"}
    - {"type": "subscribe", "job_id": "..."} → subscribe to another job
    """
    await manager.connect(job_id, websocket)
    try:
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=settings.WS_HEARTBEAT_INTERVAL,
                )
                msg = json.loads(data)
                msg_type = msg.get("type")

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
                elif msg_type == "subscribe":
                    new_job_id = msg.get("job_id")
                    if new_job_id and new_job_id != job_id:
                        await manager.connect(new_job_id, websocket)
                        await websocket.send_json({
                            "type": "subscribed",
                            "job_id": new_job_id,
                        })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Unknown message type: {msg_type}",
                    })

            except asyncio.TimeoutError:
                # Send heartbeat
                try:
                    await websocket.send_json({
                        "type": "heartbeat",
                        "timestamp": datetime.utcnow().isoformat(),
                    })
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("WebSocket error for job %s: %s", job_id, e)
    finally:
        manager.disconnect(job_id, websocket)


@router.websocket("/global")
async def global_events_websocket(websocket: WebSocket):
    """WebSocket endpoint for receiving events from all jobs.

    Use this for a dashboard view that shows all translation activity.
    """
    await manager.connect_global(websocket)
    try:
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=settings.WS_HEARTBEAT_INTERVAL * 2,
                )
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                try:
                    await websocket.send_json({"type": "heartbeat"})
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("Global WebSocket error: %s", e)
    finally:
        manager.disconnect_global(websocket)
