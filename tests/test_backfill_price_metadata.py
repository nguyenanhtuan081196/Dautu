"""Tests for the one-time, idempotent price metadata backfill."""
import unittest
from datetime import datetime, timezone

from scripts.backfill_price_metadata import backfill


class FakeCollection:
    def __init__(self, document=None):
        self.document = document
        self.updates = []

    def find_one(self, query):
        if self.document and self.document.get("_id") == query.get("_id"):
            if query.get("status") and self.document.get("status") != query["status"]:
                return None
            return self.document
        return None

    def update_one(self, query, update, upsert=False):
        self.updates.append((query, update, upsert))
        if self.document is None and upsert:
            self.document = dict(update["$setOnInsert"])


class BackfillTests(unittest.TestCase):
    def _db(self, metadata=None, run=None):
        from types import SimpleNamespace
        return SimpleNamespace(
            app_metadata=FakeCollection(metadata),
            pipeline_runs=FakeCollection(run),
        )

    def test_creates_metadata_from_successful_run(self):
        completed = datetime(2026, 11, 13, 15, 15, 30, tzinfo=timezone.utc)
        db = self._db(run={
            "_id": "price_sync:2026-11-13",
            "status": "succeeded",
            "completed_at": completed,
            "symbols_total": 99,
            "symbols_success": 99,
            "symbols_failed": 0,
        })
        result = backfill(db)
        self.assertEqual(result["status"], "created")
        self.assertEqual(db.app_metadata.document["last_updated"], completed)
        self.assertEqual(db.app_metadata.document["symbols_success"], 99)

    def test_preserves_existing_metadata(self):
        existing = {"_id": "price_sync", "run_id": "newer-run", "last_updated": "newer"}
        db = self._db(metadata=existing)
        result = backfill(db)
        self.assertEqual(result["status"], "already_present")
        self.assertEqual(db.app_metadata.updates, [])

    def test_refuses_incomplete_source_run(self):
        db = self._db(run={
            "_id": "price_sync:2026-11-13",
            "status": "succeeded",
            "completed_at": datetime.now(timezone.utc),
            "symbols_total": 99,
            "symbols_success": 98,
            "symbols_failed": 1,
        })
        with self.assertRaises(RuntimeError):
            backfill(db)


if __name__ == "__main__":
    unittest.main()
