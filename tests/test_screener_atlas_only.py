"""Regression tests preventing the Quant Screener from writing local datasets."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ScreenerAtlasOnlyTests(unittest.TestCase):
    def test_screener_persists_operational_results_to_atlas(self):
        source = (ROOT / "advanced_screener.py").read_text(encoding="utf-8")
        self.assertIn("save_screener(db, results)", source)

    def test_screener_does_not_export_csv_or_local_dataset_files(self):
        source = (ROOT / "advanced_screener.py").read_text(encoding="utf-8")
        self.assertNotIn("OUTPUT_CSV", source)
        self.assertNotIn(".to_csv(", source)
        self.assertNotIn("screener_summary.csv", source)


if __name__ == "__main__":
    unittest.main()
