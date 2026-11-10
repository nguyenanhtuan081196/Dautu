import json
import math
import tempfile
import unittest
from pathlib import Path

from financial_metrics import extract_advanced_metrics_from_bctc


class FinancialMetricsTests(unittest.TestCase):
    def _write_report(self, folder, cash_periods=None, profit_periods=None):
        cash_periods = cash_periods or {
            "2025-Q4": 10_000_000_000, "2026-Q1": 20_000_000_000, "2026-Q2": -5_000_000_000, "2026-Q3": 15_000_000_000
        }
        profit_periods = profit_periods or {
            "2025-Q4": 8_000_000_000, "2026-Q1": 9_000_000_000, "2026-Q2": 10_000_000_000, "2026-Q3": 11_000_000_000
        }
        periods = sorted(set(cash_periods) | set(profit_periods), reverse=True)
        report = {
            "balance_sheet": [
                {"period": "2026-Q3", "id": "BS_TOTAL_LIABILITIES", "value": 150},
                {"period": "2026-Q3", "id": "BS_EQUITY", "value": 100},
            ],
            "cash_flow": [
                {"period": period, "id": "CF_NET_CASH_FLOWS_FROM_OPERATING_ACTIVITIES", "value": value}
                for period, value in cash_periods.items()
            ],
            "income_statement": [
                {"period": period, "id": "IS_NET_PROFIT_AFTER_TAX", "value": value}
                for period, value in profit_periods.items()
            ],
        }
        Path(folder, "TEST.json").write_text(json.dumps(report), encoding="utf-8")

    def test_cfo_and_profit_ttm_sum_same_four_consecutive_quarters(self):
        with tempfile.TemporaryDirectory() as folder:
            self._write_report(folder)
            result = extract_advanced_metrics_from_bctc("TEST", folder)
            self.assertEqual(result["cfo_ttm"], 40.0)
            self.assertEqual(result["net_profit_ttm"], 38.0)
            self.assertEqual(result["cfo_latest"], 15.0)
            self.assertEqual(result["liabilities_to_equity"], 1.5)
            self.assertEqual(result["debt_to_equity"], 1.5)

    def test_missing_quarter_does_not_create_false_ttm(self):
        with tempfile.TemporaryDirectory() as folder:
            self._write_report(folder, cash_periods={
                "2025-Q4": 10_000_000_000, "2026-Q1": 20_000_000_000, "2026-Q3": 15_000_000_000
            })
            result = extract_advanced_metrics_from_bctc("TEST", folder)
            self.assertIsNone(result["cfo_ttm"])
            self.assertIsNotNone(result["net_profit_ttm"])

    def test_latest_cfo_does_not_fall_back_to_an_older_quarter(self):
        with tempfile.TemporaryDirectory() as folder:
            self._write_report(folder, cash_periods={
                "2025-Q4": 10_000_000_000, "2026-Q1": 20_000_000_000, "2026-Q2": -5_000_000_000
            })
            result = extract_advanced_metrics_from_bctc("TEST", folder)
            self.assertIsNone(result["cfo_latest"])
            self.assertIsNone(result["cfo_ttm"])

    def test_non_finite_values_are_treated_as_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            self._write_report(folder)
            path = Path(folder, "TEST.json")
            report = json.loads(path.read_text(encoding="utf-8"))
            report["cash_flow"][0]["value"] = float("nan")
            path.write_text(json.dumps(report), encoding="utf-8")
            result = extract_advanced_metrics_from_bctc("TEST", folder)
            self.assertIsNone(result["cfo_ttm"])

    def test_missing_report_returns_explicit_missing_values(self):
        with tempfile.TemporaryDirectory() as folder:
            result = extract_advanced_metrics_from_bctc("NOFILE", folder)
            self.assertIsNone(result["cfo_ttm"])
            self.assertIsNone(result["net_profit_ttm"])
            self.assertIsNone(result["liabilities_to_equity"])


if __name__ == "__main__":
    unittest.main()
