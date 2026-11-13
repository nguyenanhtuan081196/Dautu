"""Tests for the Atlas-only Render price-crawler entry point."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import ANY, Mock, patch

from app.pipeline.price_job import _normalize_symbols, run_price_job


ROOT = Path(__file__).resolve().parents[1]


class FakeCollection:
    def __init__(self):
        self.inserted = []
        self.updated = []

    def insert_one(self, document):
        self.inserted.append(document)

    def update_one(self, query, update):
        self.updated.append((query, update))


class RenderPriceJobTests(unittest.TestCase):
    def setUp(self):
        self.pipeline_runs = FakeCollection()
        self.db = SimpleNamespace(pipeline_runs=self.pipeline_runs)

    def test_normalize_symbols_removes_blanks_duplicates_and_case(self):
        self.assertEqual(
            _normalize_symbols([" fpt ", "FPT", " mwg", "", "MWG"]),
            ["FPT", "MWG"],
        )

    @patch("app.database.job_io.database")
    @patch("fetch_data_local.main")
    def test_successful_run_records_per_symbol_counts(self, crawler_main, get_db):
        get_db.return_value = self.db
        crawler_main.return_value = ["FPT", "MWG"]

        result = run_price_job(symbols=["FPT", "MWG"], sessions=30)

        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["symbols_success"], 2)
        self.assertEqual(result["symbols_failed"], 0)
        self.assertEqual(self.pipeline_runs.inserted[0]["status"], "running")
        self.assertEqual(
            self.pipeline_runs.updated[0][1]["$set"]["status"], "succeeded"
        )
        crawler_main.assert_called_once_with(
            ["--symbols", "FPT,MWG", "--sessions", "30"],
            on_symbol_saved=ANY,
        )

    @patch("app.database.job_io.database")
    @patch("fetch_data_local.main", return_value=["FPT"])
    def test_partial_run_marks_missing_symbols_failed(self, crawler_main, get_db):
        get_db.return_value = self.db

        result = run_price_job(symbols=["FPT", "MWG"], sessions=30)

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["successful_symbols"], ["FPT"])
        self.assertEqual(result["failed_symbols"], ["MWG"])
        self.assertEqual(self.pipeline_runs.updated[0][1]["$set"]["symbols_failed"], 1)

    @patch("app.database.job_io.database")
    @patch("fetch_data_local.main", side_effect=RuntimeError("provider unavailable"))
    def test_fatal_run_is_logged_before_returning_failure(self, crawler_main, get_db):
        get_db.return_value = self.db

        result = run_price_job(symbols=["FPT"], sessions=30)

        self.assertEqual(result["status"], "failed")
        self.assertIn("provider unavailable", result["error"])
        self.assertEqual(self.pipeline_runs.updated[0][1]["$set"]["status"], "failed")

    @patch("app.database.job_io.database")
    @patch("fetch_data_local.main")
    def test_fatal_late_error_preserves_symbols_already_upserted(self, crawler_main, get_db):
        get_db.return_value = self.db

        def save_then_fail(argv, *, on_symbol_saved):
            on_symbol_saved("FPT")
            raise RuntimeError("failure after first symbol")

        crawler_main.side_effect = save_then_fail
        result = run_price_job(symbols=["FPT", "MWG"], sessions=30)

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["successful_symbols"], ["FPT"])
        self.assertEqual(result["failed_symbols"], ["MWG"])
        self.assertIn("failure after first symbol", result["error"])

    def test_price_crawler_jitters_every_sleep_without_global_monkeypatching(self):
        import fetch_data_local as crawler

        sleeper = Mock()
        randomizer = Mock(return_value=1.1)
        crawler.jittered_sleep(1.0, sleep_fn=sleeper, random_fn=randomizer)

        randomizer.assert_called_once_with(0.8, 1.2)
        sleeper.assert_called_once_with(1.1)

    def test_price_crawler_has_no_local_dataset_file_writes(self):
        source = (ROOT / "fetch_data_local.py").read_text(encoding="utf-8-sig")
        forbidden = ("json.dump(", "to_json(", "write_text(", "write_bytes(", "open(")
        for marker in forbidden:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, source)

    def test_render_blueprint_runs_price_sync_on_isolated_weekday_cron(self):
        blueprint = (ROOT / "render.yaml").read_text(encoding="utf-8")
        self.assertIn("type: cron", blueprint)
        self.assertIn("name: dautu-price-sync", blueprint)
        self.assertIn('schedule: "30 12 * * 1-5"', blueprint)
        self.assertIn("region: singapore", blueprint)
        self.assertIn("plan: standard", blueprint)
        self.assertIn("python -m app.pipeline.price_job --sessions 30", blueprint)
        self.assertIn("key: MONGODB_URI", blueprint)
        self.assertIn("key: FHSC_API_KEY", blueprint)
        self.assertIn("sync: false", blueprint)


if __name__ == "__main__":
    unittest.main()
