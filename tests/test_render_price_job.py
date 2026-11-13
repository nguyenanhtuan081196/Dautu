"""Tests for the isolated Render price-crawler entry point."""
from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.pipeline.price_job import _jittered_sleep, _normalize_symbols, run_price_job


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

    def test_jittered_sleep_uses_randomized_backoff_bounds(self):
        sleeper = Mock()
        randomizer = Mock(return_value=1.1)
        _jittered_sleep(1.0, sleep_fn=sleeper, random_fn=randomizer)
        randomizer.assert_called_once_with(0.8, 1.2)
        sleeper.assert_called_once_with(1.1)

    @patch("app.database.job_io.database")
    @patch("fetch_data_local.main")
    def test_successful_run_records_per_symbol_counts(self, crawler_main, get_db):
        import fetch_data_local as crawler
        get_db.return_value = self.db
        original_save = crawler.save_stock
        crawler.save_stock = Mock()

        def simulate_crawler():
            crawler.save_stock(self.db, "FPT", {"symbol": "FPT"})
            crawler.save_stock(self.db, "MWG", {"symbol": "MWG"})

        crawler_main.side_effect = simulate_crawler
        try:
            result = run_price_job(symbols=["FPT", "MWG"], sessions=30)
        finally:
            crawler.save_stock = original_save

        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["symbols_success"], 2)
        self.assertEqual(result["symbols_failed"], 0)
        self.assertEqual(self.pipeline_runs.inserted[0]["status"], "running")
        self.assertEqual(self.pipeline_runs.updated[0][1]["$set"]["status"], "succeeded")

    @patch("app.database.job_io.database")
    @patch("fetch_data_local.main")
    def test_partial_run_marks_missing_symbols_failed(self, crawler_main, get_db):
        import fetch_data_local as crawler
        get_db.return_value = self.db
        original_save = crawler.save_stock
        crawler.save_stock = Mock()
        crawler_main.side_effect = lambda: crawler.save_stock(self.db, "FPT", {})
        try:
            result = run_price_job(symbols=["FPT", "MWG"], sessions=30)
        finally:
            crawler.save_stock = original_save

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


if __name__ == "__main__":
    unittest.main()
