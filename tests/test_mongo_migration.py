import unittest
from pathlib import Path

from app.database.mongo import _normalize_mongodb_uri, normalize_mongodb_uri
from scripts.migrate_json_to_mongo import inspect_sources, migrate


class MigrationDryRunTests(unittest.TestCase):
    def test_dry_run_does_not_require_mongodb_connection(self):
        counts = migrate(apply=False)
        self.assertEqual(
            set(counts),
            {"stocks", "history_symbols", "history_bars", "financial_report_files",
             "financial_report_types", "screener_results", "simulations"},
        )
        self.assertTrue(all(isinstance(value, int) for value in counts.values()))

    def test_dry_run_finds_legacy_source_files(self):
        counts = inspect_sources(Path(__file__).resolve().parents[1])
        self.assertGreater(counts["stocks"], 0)
        self.assertGreater(counts["history_symbols"], 0)
        self.assertGreater(counts["financial_report_files"], 0)
        self.assertGreater(counts["history_bars"], 0)

    def test_uri_removes_empty_options_and_adds_retry_writes(self):
        normalized = _normalize_mongodb_uri(
            "mongodb+srv://user:pass@example.mongodb.net/dautu?retryWrites=&w=majority&&"
        )
        self.assertIn("retryWrites=true", normalized)
        self.assertIn("w=majority", normalized)
        self.assertNotIn("&&", normalized)
        self.assertNotIn("retryWrites=&", normalized)

    def test_uri_does_not_duplicate_retry_writes(self):
        normalized = normalize_mongodb_uri(
            "mongodb://localhost:27017/dautu?retryWrites=false"
        )
        self.assertEqual(normalized.count("retryWrites="), 1)
        self.assertIn("retryWrites=false", normalized)

    def test_uri_rejects_invalid_scheme_and_missing_host(self):
        with self.assertRaisesRegex(ValueError, "mongodb://"):
            normalize_mongodb_uri("https://example.test")
        with self.assertRaisesRegex(ValueError, "host"):
            normalize_mongodb_uri("mongodb:///dautu")


if __name__ == "__main__":
    unittest.main()
