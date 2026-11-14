"""Async in-process scheduler for the Render Free web service.

The scheduler never runs crawler work on the ASGI event loop. A missed latest
weekday run is recovered from Atlas after a restart; successful dates are not
repeated. Metadata publication is a separate idempotent step so a process crash
between crawling and publication is recoverable on the next poll.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.database.job_io import database

logger = logging.getLogger(__name__)
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
POLL_SECONDS = max(15, int(os.getenv("PRICE_SCHEDULER_POLL_SECONDS", "60")))


def _scheduled_time() -> time:
    raw = os.getenv("PRICE_SYNC_TIME", "20:30").strip()
    hour, minute = (int(part) for part in raw.split(":", 1))
    return time(hour=hour, minute=minute)


def latest_due_weekday(now: datetime | None = None) -> date | None:
    """Return the most recent weekday schedule that has already become due."""
    current = now.astimezone(VN_TZ) if now else datetime.now(VN_TZ)
    schedule_at = _scheduled_time()
    for offset in range(0, 8):
        candidate = current.date() - timedelta(days=offset)
        if candidate.weekday() >= 5:
            continue
        due_at = datetime.combine(candidate, schedule_at, tzinfo=VN_TZ)
        if due_at <= current:
            return candidate
    return None


def _has_successful_run(scheduled_for: str) -> bool:
    db = database()
    return db.pipeline_runs.find_one(
        {
            "job_name": "price_sync",
            "scheduled_for": scheduled_for,
            "status": "succeeded",
        },
        {"_id": 1},
    ) is not None


def _ensure_price_metadata(scheduled_for: str) -> dict:
    """Publish metadata from a durable successful run, without clobbering newer data."""
    from app.pipeline.price_metadata import ensure_price_metadata

    return ensure_price_metadata(database(), scheduled_for)


async def price_scheduler_loop() -> None:
    """Poll gently; dispatch crawler and metadata I/O to background threads."""
    attempted_dates: set[str] = set()
    while True:
        # Let FastAPI finish startup and begin serving requests before any Atlas polling.
        await asyncio.sleep(POLL_SECONDS)
        scheduled_for = None
        try:
            due_date = latest_due_weekday()
            if due_date is None:
                continue

            scheduled_for = due_date.isoformat()
            if scheduled_for in attempted_dates:
                continue

            already_done = await asyncio.to_thread(_has_successful_run, scheduled_for)
            if already_done:
                # Covers a crash after the crawler committed success but before
                # the metadata write. This path is intentionally retried if it fails.
                metadata_result = await asyncio.to_thread(
                    _ensure_price_metadata, scheduled_for
                )
                attempted_dates.add(scheduled_for)
                logger.info(
                    "Recovered price metadata for %s: %s",
                    scheduled_for,
                    metadata_result.get("status"),
                )
                continue

            logger.info(
                "Starting scheduled price sync for %s (Vietnam time)", scheduled_for
            )
            from app.pipeline.price_job import run_price_job

            result = await asyncio.to_thread(
                run_price_job,
                scheduled_for=scheduled_for,
            )
            status = result.get("status")
            if status != "succeeded":
                # Partial/failed runs retain their Atlas checkpoints and are retried
                # on the next poll. Metadata is published only after full success.
                attempted_dates.discard(scheduled_for)
                logger.warning(
                    "Scheduled price sync for %s is %s; recovery will retry "
                    "(success=%s failed=%s)",
                    scheduled_for,
                    status,
                    result.get("symbols_success"),
                    result.get("symbols_failed"),
                )
                continue

            # A crash here is safe: the next poll sees the successful durable run
            # and takes the already_done recovery branch above.
            metadata_result = await asyncio.to_thread(
                _ensure_price_metadata, scheduled_for
            )
            attempted_dates.add(scheduled_for)
            logger.info(
                "Scheduled price sync and metadata finished for %s: "
                "success=%s failed=%s metadata=%s",
                scheduled_for,
                result.get("symbols_success"),
                result.get("symbols_failed"),
                metadata_result.get("status"),
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            if scheduled_for:
                # Retry both failed crawls and metadata publication on the next poll.
                attempted_dates.discard(scheduled_for)
            logger.exception(
                "Price scheduler iteration failed; it will retry on the next poll"
            )
