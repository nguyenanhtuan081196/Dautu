"""Async in-process scheduler for the Render Free web service.

The scheduler never runs crawler work on the ASGI event loop. A missed latest
weekday run is recovered from Atlas after a restart; successful dates are not
repeated. Render may restart a Free service at any time, so this state is durable.
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


async def price_scheduler_loop() -> None:
    """Poll gently; dispatch blocking VNstock/pandas work to a background thread."""
    attempted_dates: set[str] = set()
    while True:
        try:
            due_date = latest_due_weekday()
            if due_date is not None:
                scheduled_for = due_date.isoformat()
                if scheduled_for not in attempted_dates and not await asyncio.to_thread(
                    _has_successful_run, scheduled_for
                ):
                    attempted_dates.add(scheduled_for)
                    logger.info("Starting scheduled price sync for %s (Vietnam time)", scheduled_for)
                    from app.pipeline.price_job import run_price_job

                    result = await asyncio.to_thread(
                        run_price_job,
                        scheduled_for=scheduled_for,
                    )
                    if result.get("status") == "skipped":
                        # A prior process may still own an unexpired Atlas lease.
                        # Recheck on the next poll so an expired lease is recoverable.
                        attempted_dates.discard(scheduled_for)
                    logger.info(
                        "Scheduled price sync finished for %s: status=%s success=%s failed=%s",
                        scheduled_for,
                        result.get("status"),
                        result.get("symbols_success"),
                        result.get("symbols_failed"),
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Price scheduler iteration failed; it will retry on the next poll")
        await asyncio.sleep(POLL_SECONDS)
