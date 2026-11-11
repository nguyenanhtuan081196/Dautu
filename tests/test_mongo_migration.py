import unittest

from scripts.migrate_json_to_mongo import migrate


class MigrationDryRunTests(unittest.TestCase):
    def test_dry_run_does_not_require_mongodb_connection(self):
        # The dry-run path only inspects local JSON files and must never connect to Atlas.
        counts = migrate(apply=False)
        self.assertEqual(
            set(counts),
            {
                "stocks",
                "history_symbols",
                "history_bars",
                "financial_report_files",
                "financial_report_types",
                "screener_results",
                "simulations",
            },
        )
        self.assertTrue(all(isinstance(value, int) for value in counts.values()))


if __name__ == "__main__":
    unittest.main()
