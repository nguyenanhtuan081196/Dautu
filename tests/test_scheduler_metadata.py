"""Tests for scheduler-owned, retryable and non-destructive price metadata."""
import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.pipeline.price_metadata import ensure_price_metadata
from app.pipeline import scheduler


class FakeCollection:
    def __init__(self, document=None):
        self.document = document
        self.updates = []

    def find_one(self, query, projection=None):
        if self.document is None or self.document.get("_id") != query.get("_id"):
            return None
        for key, value in query.items():
            if key != "_id" and self.document.get(key) != value:
                return None
        return self.document

    def update_one(self, query, update, upsert=False):
        self.updates.append((query, update, upsert))
        if self.document is None and upsert:
            self.document = dict(update["$setOnInsert"])
            return SimpleNamespace(matched_count=0, upserted_id="price_sync")
        if self.document is None:
            return SimpleNamespace(matched_count=0, upserted_id=None)
        for key, value in query.items():
            if key != "_id" and self.document.get(key) != value:
                return SimpleNamespace(matched_count=0, upserted_id=None)
        if "$set" in update:
            self.document.update(update["$set"])
        return SimpleNamespace(matched_count=1, upserted_id=None)


def successful_run(day="2026-11-16", completed=None):
    completed = completed or datetime(2026, 11, 16, 14, 0, tzinfo=timezone.utc)
    return {
        "_id": f"price_sync:{day}",
        "job_name": "price_sync",
        "scheduled_for": day,
        "status": "succeeded",
        "completed_at": completed,
        "symbols_total": 100,
        "symbols_success": 100,
        "symbols_failed": 0,
    }


class PriceMetadataTests(unittest.TestCase):
    def db(self, run, metadata=None):
        return SimpleNamespace(
            pipeline_runs=FakeCollection(run),
            app_metadata=FakeCollection(metadata),
        )

    def test_creates_metadata_from_complete_successful_run(self):
        run = successful_run()
        db = self.db(run)
        result = ensure_price_metadata(db, "2026-11-16")
        self.assertEqual(result["status"], "created")
        self.assertEqual(db.app_metadata.document["run_id"], run["_id"])
        self.assertEqual(db.app_metadata.document["last_updated"], run["completed_at"])

    def test_same_run_metadata_is_never_overwritten(self):
        original = {
            "_id": "price_sync",
            "run_id": "price_sync:2026-11-16",
            "last_updated": datetime(2026, 11, 16, 14, 0, tzinfo=timezone.utc),
            "status": "succeeded",
            "symbols_success": 100,
        }
        db = self.db(successful_run(), original.copy())
        result = ensure_price_metadata(db, "2026-11-16")
        self.assertEqual(result["status"], "already_present")
        self.assertEqual(db.app_metadata.document, original)
        self.assertEqual(db.app_metadata.updates, [])

    def test_newer_existing_metadata_is_preserved(self):
        newer = {
            "_id": "price_sync",
            "run_id": "price_sync:2026-11-17",
            "last_updated": datetime(2026, 11, 17, 14, 0, tzinfo=timezone.utc),
            "status": "succeeded",
            "symbols_success": 100,
        }
        db = self.db(successful_run(), newer.copy())
        result = ensure_price_metadata(db, "2026-11-16")
        self.assertEqual(result["status"], "preserved_existing")
        self.assertEqual(db.app_metadata.document, newer)
        self.assertEqual(db.app_metadata.updates, [])

    def test_older_metadata_advances_to_new_successful_run(self):
        older = {
            "_id": "price_sync",
            "run_id": "price_sync:2026-11-13",
            "last_updated": datetime(2026, 11, 13, 14, 0, tzinfo=timezone.utc),
        }
        db = self.db(successful_run(), older.copy())
        result = ensure_price_metadata(db, "2026-11-16")
        self.assertEqual(result["status"], "updated")
        self.assertEqual(db.app_metadata.document["run_id"], "price_sync:2026-11-16")

    def test_incomplete_or_failed_run_never_writes_metadata(self):
        run = successful_run()
        run["symbols_success"] = 99
        run["symbols_failed"] = 1
        db = self.db(run)
        with self.assertRaises(RuntimeError):
            ensure_price_metadata(db, "2026-11-16")
        self.assertIsNone(db.app_metadata.document)

    def test_scheduler_retries_partial_run_on_next_poll(self):
        async def scenario():
            partial = {"status": "partial", "symbols_success": 90, "symbols_failed": 10}
            with (
                patch.object(scheduler, "POLL_SECONDS", 15),
                patch.object(scheduler, "latest_due_weekday", return_value=datetime(2026, 11, 16).date()),
                patch.object(scheduler, "_has_successful_run", side_effect=[False, False]),
                patch.object(scheduler, "_ensure_price_metadata") as ensure,
                patch("app.pipeline.price_job.run_price_job", side_effect=[partial, asyncio.CancelledError()]) as run_job,
                patch.object(scheduler.asyncio, "sleep", new=AsyncMock(side_effect=[None, None, asyncio.CancelledError()])),
            ):
                with self.assertRaises(asyncio.CancelledError):
                    await scheduler.price_scheduler_loop()
                self.assertEqual(run_job.call_count, 2)
                ensure.assert_not_called()

        asyncio.run(scenario())


    def test_scheduler_retries_metadata_after_successful_run_if_first_write_fails(self):
        async def scenario():
            with (
                patch.object(scheduler, "POLL_SECONDS", 15),
                patch.object(scheduler, "latest_due_weekday", return_value=datetime(2026, 11, 16).date()),
                patch.object(scheduler, "_has_successful_run", return_value=False),
                patch.object(scheduler, "_ensure_price_metadata", side_effect=[RuntimeError("Atlas transient error"), {"status": "created"}]) as ensure,
                patch("app.pipeline.price_job.run_price_job", return_value={"status": "succeeded", "symbols_success": 100, "symbols_failed": 0}) as run_job,
                patch.object(scheduler.asyncio, "sleep", new=AsyncMock(side_effect=[None, None, asyncio.CancelledError()])),
            ):
                with self.assertRaises(asyncio.CancelledError):
                    await scheduler.price_scheduler_loop()
                self.assertEqual(run_job.call_count, 1)
                self.assertEqual(ensure.call_count, 2)

        asyncio.run(scenario())

    def test_scheduler_repairs_metadata_when_run_already_succeeded(self):
        async def scenario():
            with (
                patch.object(scheduler, "POLL_SECONDS", 15),
                patch.object(scheduler, "latest_due_weekday", return_value=datetime(2026, 11, 16).date()),
                patch.object(scheduler, "_has_successful_run", return_value=True),
                patch.object(scheduler, "_ensure_price_metadata", return_value={"status": "created"}) as ensure,
                patch.object(scheduler.asyncio, "sleep", new=AsyncMock(side_effect=[None, asyncio.CancelledError()])),
            ):
                with self.assertRaises(asyncio.CancelledError):
                    await scheduler.price_scheduler_loop()
                ensure.assert_called_once_with("2026-11-16")

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
