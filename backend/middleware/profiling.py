"""Performance profiling middleware for CPU, RAM, GPU, and I/O monitoring.

Features:
- Per-request CPU time and wall-clock tracking
- Memory usage monitoring (RSS)
- GPU utilization tracking (NVIDIA SMI)
- Periodic profiling snapshots to logs and WebSocket
- Slow request detection and logging
- Automatic garbage collection after large requests
- Metrics aggregation for dashboard display
"""

from __future__ import annotations

import asyncio
import gc
import logging
import os
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from backend.config import settings

logger = logging.getLogger(__name__)

# ── Dataclasses ──────────────────────────────────────────────────────────


@dataclass
class ProfileSnapshot:
    """A snapshot of system performance metrics."""

    timestamp: float
    cpu_percent: float
    ram_used_mb: float
    ram_percent: float
    gpu_util_percent: Optional[float] = None
    gpu_memory_mb: Optional[float] = None
    active_tasks: int = 0
    active_connections: int = 0
    queue_size: int = 0
    cache_entries: int = 0
    cache_memory_mb: float = 0.0
    thread_pool_size: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": datetime.fromtimestamp(self.timestamp).isoformat(),
            "cpu_percent": self.cpu_percent,
            "ram_used_mb": round(self.ram_used_mb, 1),
            "ram_percent": round(self.ram_percent, 1),
            "gpu_util_percent": self.gpu_util_percent,
            "gpu_memory_mb": round(self.gpu_memory_mb, 1) if self.gpu_memory_mb else None,
            "active_tasks": self.active_tasks,
            "active_connections": self.active_connections,
            "queue_size": self.queue_size,
            "cache_entries": self.cache_entries,
            "cache_memory_mb": round(self.cache_memory_mb, 1),
            "thread_pool_size": self.thread_pool_size,
        }


@dataclass
class RequestProfile:
    """Performance data for a single HTTP request."""

    method: str
    path: str
    status_code: int
    duration_ms: float
    cpu_time_ms: float
    memory_delta_mb: float
    request_size_bytes: int = 0
    response_size_bytes: int = 0


# ── System Monitor ───────────────────────────────────────────────────────


class SystemMonitor:
    """Monitors system resources: CPU, RAM, GPU.

    Collects periodic snapshots that can be streamed via WebSocket
    or queried via API.
    """

    def __init__(
        self,
        snapshot_interval: float = 5.0,
        max_history: int = 360,  # 30 min at 5s intervals
        enable_gpu: bool = False,
    ) -> None:
        self.snapshot_interval = snapshot_interval
        self.max_history = max_history
        self.enable_gpu = enable_gpu or settings.ENABLE_GPU_PROFILING

        self._history: deque[ProfileSnapshot] = deque(maxlen=max_history)
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._gpu_available = False
        self._listeners: list[callable] = []

        # Current snapshot (updated on each tick)
        self.current: ProfileSnapshot = ProfileSnapshot(
            timestamp=time.time(),
            cpu_percent=0.0,
            ram_used_mb=0.0,
            ram_percent=0.0,
        )

    async def start(self) -> None:
        """Start the monitoring loop."""
        if self._running:
            return

        self._running = True
        self._gpu_available = await self._check_gpu()
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info(
            "System monitor started (interval=%ds, gpu=%s)",
            self.snapshot_interval, self._gpu_available,
        )

    async def stop(self) -> None:
        """Stop the monitoring loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("System monitor stopped")

    def add_listener(self, callback: callable) -> None:
        """Add a listener for new snapshots.

        The callback is called with each new ProfileSnapshot.
        """
        self._listeners.append(callback)

    def remove_listener(self, callback: callable) -> None:
        """Remove a listener."""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def get_history(self, seconds: int = 60) -> list[dict[str, Any]]:
        """Get profiling history for the last N seconds."""
        cutoff = time.time() - seconds
        return [
            s.to_dict() for s in self._history
            if s.timestamp >= cutoff
        ]

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of current system performance."""
        snapshots = list(self._history)
        if not snapshots:
            return {"current": self.current.to_dict(), "averages": {}}

        avg_cpu = sum(s.cpu_percent for s in snapshots) / len(snapshots)
        avg_ram = sum(s.ram_used_mb for s in snapshots) / len(snapshots)
        max_ram = max(s.ram_used_mb for s in snapshots)

        return {
            "current": self.current.to_dict(),
            "averages": {
                "cpu_percent": round(avg_cpu, 1),
                "ram_used_mb": round(avg_ram, 1),
                "max_ram_mb": round(max_ram, 1),
            },
            "sample_count": len(snapshots),
            "duration_seconds": round(
                snapshots[-1].timestamp - snapshots[0].timestamp,
            ) if len(snapshots) > 1 else 0,
        }

    async def _monitor_loop(self) -> None:
        """Continuous monitoring loop."""
        import psutil

        process = psutil.Process(os.getpid())

        while self._running:
            try:
                # CPU
                cpu_percent = process.cpu_percent(interval=0.1)

                # RAM
                mem_info = process.memory_info()
                ram_used_mb = mem_info.rss / (1024 * 1024)
                system_mem = psutil.virtual_memory()
                ram_percent = system_mem.percent

                # GPU
                gpu_util = None
                gpu_mem = None
                if self._gpu_available:
                    gpu_util, gpu_mem = await self._get_gpu_stats()

                # Thread pool
                loop = asyncio.get_event_loop()
                thread_pool = getattr(loop, "_default_executor", None)
                tps = getattr(thread_pool, "_max_workers", 0) if thread_pool else 0

                self.current = ProfileSnapshot(
                    timestamp=time.time(),
                    cpu_percent=cpu_percent,
                    ram_used_mb=ram_used_mb,
                    ram_percent=ram_percent,
                    gpu_util_percent=gpu_util,
                    gpu_memory_mb=gpu_mem,
                    active_tasks=len(asyncio.all_tasks(loop)),
                    thread_pool_size=tps,
                )

                self._history.append(self.current)

                # Notify listeners
                for listener in self._listeners:
                    try:
                        await listener(self.current)
                    except Exception as e:
                        logger.debug("Profile listener error: %s", e)

                # Log slow increase in memory
                if ram_used_mb > settings.PROFILE_MEMORY_WARN_MB:
                    logger.warning(
                        "High memory usage: %.0f MB (limit: %d MB)",
                        ram_used_mb,
                        settings.PROFILE_MEMORY_WARN_MB,
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("Profile monitor error: %s", e)

            await asyncio.sleep(self.snapshot_interval)

    async def _check_gpu(self) -> bool:
        """Check if NVIDIA GPU monitoring is available."""
        if not self.enable_gpu:
            return False
        try:
            import subprocess
            result = await asyncio.create_subprocess_exec(
                "nvidia-smi", "--query-gpu=index", "--format=csv,noheader",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await result.wait()
            return result.returncode == 0
        except Exception:
            return False

    async def _get_gpu_stats(self) -> tuple[Optional[float], Optional[float]]:
        """Get GPU utilization and memory from nvidia-smi."""
        try:
            import subprocess
            result = await asyncio.create_subprocess_exec(
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used",
                "--format=csv,noheader,nounits",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await result.communicate()
            if stdout:
                parts = stdout.decode().strip().split(", ")
                if len(parts) >= 2:
                    return float(parts[0]), float(parts[1])
        except Exception:
            pass
        return None, None


# Global system monitor instance
system_monitor = SystemMonitor(
    snapshot_interval=settings.PROFILE_SNAPSHOT_INTERVAL,
    max_history=settings.PROFILE_MAX_HISTORY,
    enable_gpu=settings.ENABLE_GPU_PROFILING,
)


# ── FastAPI Middleware ────────────────────────────────────────────────────


class ProfilingMiddleware(BaseHTTPMiddleware):
    """Middleware that profiles each HTTP request.

    Tracks:
    - Request duration (wall clock)
    - CPU time consumed
    - Memory delta before/after
    - Request/response sizes

    Logs slow requests (>1s) as warnings.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip profiling for health/static endpoints
        path = request.url.path
        if path in ("/api/v1/health", "/health", "/api/v1/info") or path.startswith(
            "/static/"
        ):
            return await call_next(request)

        import psutil

        process = psutil.Process(os.getpid())

        start_time = time.perf_counter()
        start_cpu = process.cpu_times()
        start_mem = process.memory_info().rss

        # Read request body size if possible
        request_size = 0
        try:
            content_length = request.headers.get("content-length")
            if content_length:
                request_size = int(content_length)
        except (ValueError, TypeError):
            pass

        response = await call_next(request)

        end_time = time.perf_counter()
        end_cpu = process.cpu_times()
        end_mem = process.memory_info().rss

        duration_ms = (end_time - start_time) * 1000
        cpu_ms = (
            (end_cpu.user - start_cpu.user) + (end_cpu.system - start_cpu.system)
        ) * 1000
        mem_delta_mb = (end_mem - start_mem) / (1024 * 1024)

        # Get response size
        response_size = 0
        if hasattr(response, "body"):
            body = response.body
            if body:
                response_size = len(body)

        # Log slow requests
        if duration_ms > settings.PROFILE_SLOW_REQUEST_MS:
            logger.warning(
                "SLOW REQUEST: %s %s — %.0fms (cpu=%.0fms, mem=%+.1fMB, req=%d, resp=%d)",
                request.method, path, duration_ms, cpu_ms, mem_delta_mb,
                request_size, response_size,
            )

        # Force garbage collection for memory-heavy requests
        if mem_delta_mb > settings.PROFILE_GC_THRESHOLD_MB:
            gc.collect()
            collected = gc.collect()
            if collected > 0:
                logger.debug(
                    "GC collected %d objects after %s %s (delta=%+.1fMB)",
                    collected, request.method, path, mem_delta_mb,
                )

        # Add performance headers in debug mode
        if settings.DEBUG:
            response.headers["X-Profiler-Duration-Ms"] = str(int(duration_ms))
            response.headers["X-Profiler-Cpu-Ms"] = str(int(cpu_ms))
            response.headers["X-Profiler-Memory-Delta-Kb"] = str(int(mem_delta_mb * 1024))

        return response


# ── Convenience ──────────────────────────────────────────────────────────


@asynccontextmanager
async def profile_operation(name: str):
    """Context manager to profile a specific async operation.

    Usage:
        async with profile_operation("ocr_page_5"):
            result = await ocr_service.extract_text(...)

    Logs the duration at DEBUG level.
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        duration = (time.perf_counter() - start) * 1000
        if duration > settings.PROFILE_SLOW_REQUEST_MS:
            logger.warning("PROFILE [%s]: %.0fms", name, duration)
        else:
            logger.debug("PROFILE [%s]: %.0fms", name, duration)


async def get_performance_dashboard() -> dict[str, Any]:
    """Get a comprehensive performance dashboard summary.

    Returns metrics from the system monitor, cache stats, and
    profiling history.
    """
    from backend.services.cache_service import get_all_cache_stats

    return {
        "system": system_monitor.get_summary(),
        "caches": await get_all_cache_stats(),
        "history": system_monitor.get_history(seconds=60),
    }
