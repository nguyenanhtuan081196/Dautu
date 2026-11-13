"""Tests for the Atlas-backed, memory-bounded Render Free price scheduler."""
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.pipeline.price_job import _chunks, _normalize_symbols
from app.pipeline.scheduler import latest_due_weekday

ROOT = Path(__file__).resolve().parents[1]


class FakeCollection:
    def __init__(self):
        self.documents = {}
        self.updated = []

    def find_one(self, query, projection=None):
        return self.documents.get(query.get("_id"))

    def insert_one(self, document):
        self.documents[document["_id"]] = document

    def update_one(self, query, update):
        self.updated.append((query, update))
        doc = self.documents.get(query.get("_id"))
        if doc:
            doc.update(update.get("$set", {}))


class RenderFreePriceJobTests(unittest.TestCase):
    def test_normalize_symbols_removes_blanks_duplicates_and_case(self):
        self.assertEqual(_normalize_symbols([" fpt ", "FPT", " mwg", "", "MWG"]), ["FPT", "MWG"])

    def test_symbols_are_processed_in_bounded_batches(self):
        batches = list(_chunks([f"S{i}" for i in range(23)], 5))
        self.assertEqual([len(batch) for batch in batches], [5, 5, 5, 5, 3])
        self.assertTrue(all(len(batch) <= 10 for batch in batches))

    def test_scheduler_selects_latest_due_weekday_and_skips_weekends(self):
        friday_after_close = datetime.fromisoformat("2026-11-13T21:00:00+07:00")
        saturday = datetime.fromisoformat("2026-11-14T21:00:00+07:00")
        self.assertEqual(latest_due_weekday(friday_after_close), date(2026, 11, 13))
        self.assertEqual(latest_due_weekday(saturday), date(2026, 11, 13))

    @patch("app.database.job_io.database")
    @patch("fetch_data_local.main")
    def test_run_executes_five_symbol_batches_and_records_atlas_progress(self, crawler_main, get_db):
        collection = FakeCollection()
        db = SimpleNamespace(pipeline_runs=collection)
        get_db.return_value = db
        crawler_main.side_effect = lambda argv: argv[1].split(",")
        from app.pipeline.price_job import run_price_job

        result = run_price_job(
            symbols=[f"S{i}" for i in range(12)],
            sessions=30,
            batch_size=5,
            scheduled_for="2026-11-13",
        )
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["symbols_success"], 12)
        self.assertEqual([call.args[0][1].count(",") + 1 for call in crawler_main.call_args_list], [5, 5, 2])
        self.assertEqual(collection.documents["price_sync:2026-11-13"]["status"], "succeeded")

    @patch("app.database.job_io.database")
    @patch("fetch_data_local.main")
    def test_successful_scheduled_run_is_idempotently_skipped(self, crawler_main, get_db):
        collection = FakeCollection()
        collection.documents["price_sync:2026-11-13"] = {
            "_id": "price_sync:2026-11-13",
            "status": "succeeded",
        }
        get_db.return_value = SimpleNamespace(pipeline_runs=collection)
        from app.pipeline.price_job import run_price_job

        result = run_price_job(symbols=["FPT"], scheduled_for="2026-11-13")
        self.assertEqual(result["status"], "skipped")
        crawler_main.assert_not_called()

    def test_crawler_has_no_local_dataset_file_writes(self):
        source = (ROOT / "fetch_data_local.py").read_text(encoding="utf-8-sig")
        for marker in ("json.dump(", "to_json(", "write_text(", "write_bytes("):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, source)

    def test_free_architecture_has_no_paid_cron_blueprint(self):
        self.assertFalse((ROOT / "render.yaml").exists())
        source = (ROOT / "app/api/main.py").read_text(encoding="utf-8")
        self.assertIn("asyncio.create_task", source)
        self.assertIn("price_scheduler_loop", source)


if __name__ == "__main__":
    unittest.main()
