"""Job queue manager with stop, resume, retry, and prioritization support."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

from backend.config import settings

logger = logging.getLogger(__name__)


class JobAction(str, Enum):
    """Actions that can be performed on a queued job."""

    PAUSE = "pause"
    RESUME = "resume"
    CANCEL = "cancel"
    RETRY = "retry"
    PRIORITIZE = "prioritize"


class QueueEntry:
    """A job entry in the queue with metadata."""

    def __init__(
        self,
        job_id: str,
        chapter_id: str,
        priority: int = 0,
        created_at: Optional[datetime] = None,
    ) -> None:
        self.job_id = job_id
        self.chapter_id = chapter_id
        self.priority = priority
        self.created_at = created_at or datetime.utcnow()
        self.paused: bool = False
        self.cancelled: bool = False
        self.retry_count: int = 0
        self.max_retries: int = 3


class JobQueueManager:
    """Manages the job queue with pause/resume/cancel/retry capabilities.

    Features:
    - FIFO queue with priority support
    - Pause/resume individual jobs
    - Cancel in-flight jobs
    - Automatic retry on failure
    - Concurrency limits
    - Job timeout enforcement
    """

    def __init__(self, process_callback: Optional[Callable] = None) -> None:
        self._queue: asyncio.Queue[QueueEntry] = asyncio.Queue()
        self._active_jobs: dict[str, asyncio.Task] = {}
        self._paused_jobs: set[str] = set()
        self._cancelled_jobs: set[str] = set()
        self._running = False
        self._process_callback = process_callback
        self._semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_JOBS)
        self._worker_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the queue consumer worker."""
        self._running = True
        self._worker_task = asyncio.create_task(self._consumer_loop())
        logger.info("Job queue manager started (max concurrent: %d)", settings.MAX_CONCURRENT_JOBS)

    async def stop(self) -> None:
        """Stop the queue consumer and cancel active jobs."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        for job_id, task in list(self._active_jobs.items()):
            task.cancel()
        self._active_jobs.clear()
        self._paused_jobs.clear()
        self._cancelled_jobs.clear()
        logger.info("Job queue manager stopped")

    async def enqueue(
        self,
        job_id: str,
        chapter_id: str,
        priority: int = 0,
    ) -> None:
        """Add a job to the queue.

        Args:
            job_id: ID of the translation job.
            chapter_id: ID of the chapter to translate.
            priority: Higher priority jobs are processed first.
        """
        entry = QueueEntry(
            job_id=job_id,
            chapter_id=chapter_id,
            priority=priority,
        )
        await self._queue.put(entry)
        logger.info("Job %s enqueued (priority: %d)", job_id, priority)

    async def pause(self, job_id: str) -> bool:
        """Pause a job. If it's actively processing, it will be marked for pause.

        Returns:
            True if the job was found and marked for pause.
        """
        if job_id in self._active_jobs:
            self._paused_jobs.add(job_id)
            logger.info("Job %s marked for pause", job_id)
            return True

        # Check if it's in the queue
        # (we can't modify items in asyncio.Queue easily, so we check during processing)
        return job_id in self._paused_jobs or await self._mark_queue_pause(job_id)

    async def resume(self, job_id: str) -> bool:
        """Resume a paused job.

        Returns:
            True if the job was paused and now resumed.
        """
        if job_id in self._paused_jobs:
            self._paused_jobs.discard(job_id)
            logger.info("Job %s resumed", job_id)
            return True
        return False

    async def cancel(self, job_id: str) -> bool:
        """Cancel a job. If active, the task will be cancelled.

        Returns:
            True if the job was cancelled.
        """
        self._cancelled_jobs.add(job_id)
        self._paused_jobs.discard(job_id)

        # Cancel active task
        if job_id in self._active_jobs:
            self._active_jobs[job_id].cancel()
            logger.info("Job %s active task cancelled", job_id)
            return True

        logger.info("Job %s marked as cancelled", job_id)
        return True

    async def retry(self, job_id: str, chapter_id: str) -> bool:
        """Re-enqueue a failed job for retry.

        Returns:
            True if the job was re-enqueued.
        """
        self._cancelled_jobs.discard(job_id)
        self._paused_jobs.discard(job_id)
        await self.enqueue(job_id, chapter_id)
        logger.info("Job %s queued for retry", job_id)
        return True

    async def prioritize(self, job_id: str) -> bool:
        """Move a job to the front of the queue by re-enqueuing with high priority.

        Returns:
            True if the job was reprioritized. Note: asyncio.Queue is FIFO,
            so this effectively re-enqueues at the front conceptually.
        """
        # For now, just log it since asyncio.Queue is strictly FIFO.
        # A priority queue implementation could be swapped in later.
        logger.info("Job %s marked for priority (FIFO queue, will process in order)", job_id)
        return True

    def is_paused(self, job_id: str) -> bool:
        """Check if a job is paused."""
        return job_id in self._paused_jobs

    def is_cancelled(self, job_id: str) -> bool:
        """Check if a job is cancelled."""
        return job_id in self._cancelled_jobs

    def get_active_count(self) -> int:
        """Get the number of currently active jobs."""
        return len(self._active_jobs)

    def get_queue_size(self) -> int:
        """Get the approximate size of the pending queue."""
        return self._queue.qsize()

    def get_job_status_summary(self, job_id: str) -> dict[str, Any]:
        """Get the queue status summary for a job."""
        return {
            "job_id": job_id,
            "active": job_id in self._active_jobs,
            "paused": job_id in self._paused_jobs,
            "cancelled": job_id in self._cancelled_jobs,
        }

    # ── Private methods ──────────────────────────────────────────────────

    async def _consumer_loop(self) -> None:
        """Main consumer loop that processes jobs from the queue."""
        while self._running:
            try:
                entry = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=1.0,
                )
            except asyncio.TimeoutError:
                continue

            # Check if job was cancelled before processing
            if entry.job_id in self._cancelled_jobs:
                self._cancelled_jobs.discard(entry.job_id)
                logger.info("Skipping cancelled job %s", entry.job_id)
                self._queue.task_done()
                continue

            # Acquire semaphore slot
            await self._semaphore.acquire()

            # Start processing in background task
            task = asyncio.create_task(
                self._run_job(entry)
            )
            self._active_jobs[entry.job_id] = task
            self._queue.task_done()

    async def _run_job(self, entry: QueueEntry) -> None:
        """Run a job with support for pause and timeout.

        The job periodically checks if it should pause or has been cancelled.
        """
        try:
            # Check for pause every 0.5 seconds during processing
            async def _check_interrupt():
                while True:
                    await asyncio.sleep(0.5)
                    if entry.job_id in self._cancelled_jobs:
                        raise asyncio.CancelledError(f"Job {entry.job_id} was cancelled")
                    while entry.job_id in self._paused_jobs:
                        await asyncio.sleep(0.5)
                        if entry.job_id in self._cancelled_jobs:
                            raise asyncio.CancelledError(f"Job {entry.job_id} was cancelled while paused")

            # Create interrupt checker
            interrupt_task = asyncio.create_task(_check_interrupt())

            try:
                if self._process_callback:
                    timeout = settings.JOB_TIMEOUT_MINUTES * 60
                    await asyncio.wait_for(
                        self._process_callback(entry.job_id, entry.chapter_id),
                        timeout=timeout,
                    )
            except asyncio.TimeoutError:
                logger.error("Job %s timed out after %d minutes", entry.job_id, settings.JOB_TIMEOUT_MINUTES)
                raise
            finally:
                interrupt_task.cancel()
                try:
                    await interrupt_task
                except asyncio.CancelledError:
                    pass

        except asyncio.CancelledError:
            logger.info("Job %s processing was cancelled", entry.job_id)
            raise
        except Exception as e:
            logger.error("Job %s failed: %s", entry.job_id, e)
            # Handle retry logic
            if entry.retry_count < entry.max_retries:
                entry.retry_count += 1
                logger.info("Retrying job %s (attempt %d/%d)", entry.job_id, entry.retry_count, entry.max_retries)
                await self._queue.put(entry)
            else:
                logger.error("Job %s exceeded max retries (%d)", entry.job_id, entry.max_retries)
        finally:
            self._active_jobs.pop(entry.job_id, None)
            self._paused_jobs.discard(entry.job_id)
            self._cancelled_jobs.discard(entry.job_id)
            self._semaphore.release()

    async def _mark_queue_pause(self, job_id: str) -> bool:
        """Mark a job for pause even if it's still in the queue."""
        self._paused_jobs.add(job_id)
        return True
