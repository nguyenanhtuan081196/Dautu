"""Tests for the Atlas-backed, memory-bounded Render Free price scheduler."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.pipeline.price_job import _chunks, _claim_run, _normalize_symbols, _utc_now
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

    def update_one(self, query, update, upsert=False):
        self.updated.append((query, update))
        doc = self.documents.get(query.get("_id"))
        if doc is None and upsert:
            doc = {"_id": query.get("_id")}
            self.documents[query.get("_id")] = doc
        if doc:
            doc.update(update.get("$set", {}))

    def find_one_and_update(self, query, update, return_document=None):
        doc = self.documents.get(query.get("_id"))
        if not doc:
            return None
        now = next(
            (condition["lease_until"]["$lte"] for condition in query.get("$or", [])
             if "lease_until" in condition and "$lte" in condition["lease_until"]),
            None,
        )
        lease = doc.get("lease_until")
        if lease is not None and lease.tzinfo is None:
            lease = lease.replace(tzinfo=timezone.utc)
        can_claim = doc.get("status") != "running" or (
            now is not None and (lease is None or lease <= now)
        ) or lease is None
        if not can_claim:
            return None
        doc.update(update.get("$set", {}))
        return doc


class RenderFreePriceJobTests(unittest.TestCase):
    def test_normalize_symbols_removes_blanks_duplicates_and_case(self):
        self.assertEqual(_normalize_symbols([" fpt ", "FPT", " mwg", "", "MWG"]), ["FPT", "MWG"])

    def test_symbols_are_processed_in_bounded_batches(self):
        batches = list(_chunks([f"S{i}" for i in range(23)], 5))
        self.assertEqual([len(batch) for batch in batches], [5, 5, 5, 5, 3])
        self.assertTrue(all(len(batch) <= 10 for batch in batches))

    def test_atlas_lease_blocks_duplicate_worker_using_naive_mongo_datetime(self):
        collection = FakeCollection()
        collection.documents["run-1"] = {
            "_id": "run-1",
            "status": "running",
            "lease_until": datetime.utcnow() + timedelta(minutes=20),
        }
        self.assertFalse(_claim_run(collection, "run-1", "2026-11-13", 1, 30))

    def test_expired_atlas_lease_can_be_recovered_after_restart(self):
        collection = FakeCollection()
        collection.documents["run-2"] = {
            "_id": "run-2",
            "status": "running",
            "lease_until": datetime(2000, 1, 1),
        }
        self.assertTrue(_claim_run(collection, "run-2", "2026-11-13", 1, 30))
        self.assertEqual(collection.documents["run-2"]["status"], "running")
        self.assertTrue(collection.documents["run-2"]["recovered_after_restart"])

    def test_scheduler_selects_latest_due_weekday_and_skips_weekends(self):
        friday_after_close = datetime.fromisoformat("2026-11-13T21:00:00+07:00")
        saturday = datetime.fromisoformat("2026-11-14T21:00:00+07:00")
        self.assertEqual(latest_due_weekday(friday_after_close), date(2026, 11, 13))
        self.assertEqual(latest_due_weekday(saturday), date(2026, 11, 13))

    @patch("app.database.job_io.database")
    @patch("fetch_data_local.main")
    def test_run_executes_five_symbol_batches_and_records_atlas_progress(self, crawler_main, get_db):
        collection = FakeCollection()
        db = SimpleNamespace(pipeline_runs=collection, app_metadata=FakeCollection())
        get_db.return_value = db
        def fake_crawler(argv, *, on_symbol_saved=None):
            symbols = argv[1].split(",")
            for symbol in symbols:
                if on_symbol_saved:
                    on_symbol_saved(symbol)
            return symbols

        crawler_main.side_effect = fake_crawler
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
        metadata = get_db.return_value.app_metadata.documents["price_sync"]
        self.assertEqual(metadata["status"], "succeeded")
        self.assertEqual(metadata["symbols_success"], 12)
        self.assertIsNotNone(metadata["last_updated"])

    @patch("app.database.job_io.database")
    @patch("fetch_data_local.main")
    def test_restart_resumes_only_symbols_not_already_persisted_in_atlas(self, crawler_main, get_db):
        collection = FakeCollection()
        collection.documents["price_sync:2026-11-13"] = {
            "_id": "price_sync:2026-11-13",
            "status": "partial",
            "successful_symbols": ["FPT"],
            "started_at": datetime.now(timezone.utc),
        }
        get_db.return_value = SimpleNamespace(pipeline_runs=collection, app_metadata=FakeCollection())

        def save_remaining(argv, *, on_symbol_saved):
            symbols = argv[1].split(",")
            for symbol in symbols:
                on_symbol_saved(symbol)
            return symbols

        crawler_main.side_effect = save_remaining
        from app.pipeline.price_job import run_price_job

        result = run_price_job(
            symbols=["FPT", "MWG"],
            batch_size=5,
            scheduled_for="2026-11-13",
        )
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["successful_symbols"], ["FPT", "MWG"])
        self.assertEqual(crawler_main.call_args.args[0][1], "MWG")

    @patch("app.database.job_io.database")
    @patch("fetch_data_local.main")
    def test_late_batch_error_preserves_confirmed_atlas_symbol_writes(self, crawler_main, get_db):
        collection = FakeCollection()
        get_db.return_value = SimpleNamespace(pipeline_runs=collection, app_metadata=FakeCollection())

        def save_then_fail(argv, *, on_symbol_saved):
            on_symbol_saved("FPT")
            raise RuntimeError("provider disconnected after first upsert")

        crawler_main.side_effect = save_then_fail
        from app.pipeline.price_job import run_price_job

        result = run_price_job(symbols=["FPT", "MWG"], batch_size=2)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["successful_symbols"], ["FPT"])
        self.assertEqual(result["failed_symbols"], ["MWG"])
        self.assertIn("provider disconnected", result["error"])

    @patch("app.database.job_io.database")
    @patch("fetch_data_local.main")
    def test_successful_scheduled_run_is_idempotently_skipped(self, crawler_main, get_db):
        collection = FakeCollection()
        collection.documents["price_sync:2026-11-13"] = {
            "_id": "price_sync:2026-11-13",
            "status": "succeeded",
        }
        get_db.return_value = SimpleNamespace(pipeline_runs=collection, app_metadata=FakeCollection())
        from app.pipeline.price_job import run_price_job

        result = run_price_job(symbols=["FPT"], scheduled_for="2026-11-13")
        self.assertEqual(result["status"], "skipped")
        crawler_main.assert_not_called()

    def test_crawler_has_no_local_dataset_file_writes(self):
        source = (ROOT / "fetch_data_local.py").read_text(encoding="utf-8-sig")
        for marker in ("json.dump(", "to_json(", "write_text(", "write_bytes("):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, source)

    def test_crawler_reads_one_stock_document_and_releases_memory(self):
        source = (ROOT / "fetch_data_local.py").read_text(encoding="utf-8-sig")
        self.assertIn('db.stocks.find_one({"_id": symbol})', source)
        self.assertNotIn("load_stocks(db)", source)
        self.assertIn("gc.collect()", source)
        self.assertIn("copy_on_write = True", source)
        self.assertIn('os.environ[_thread_env] = "1"', source)

    def test_free_architecture_has_no_paid_cron_blueprint(self):
        self.assertFalse((ROOT / "render.yaml").exists())
        source = (ROOT / "app/api/main.py").read_text(encoding="utf-8")
        self.assertIn("asyncio.create_task", source)
        self.assertIn("price_scheduler_loop", source)
        scheduler = (ROOT / "app/pipeline/scheduler.py").read_text(encoding="utf-8")
        self.assertIn("asyncio.to_thread", scheduler)


if __name__ == "__main__":
    unittest.main()
