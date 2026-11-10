import json
import math
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from simulator import get_historical_return_rate_with_details


class HistoricalCagrTests(unittest.TestCase):
    def _write_history(self, folder, prices):
        end = datetime(2025, 12, 31)
        bars = []
        count = len(prices)
        for index, price in enumerate(prices):
            day = end - timedelta(days=round((count - 1 - index) * (5 * 365.25) / (count - 1)))
            bars.append({"time": day.strftime("%Y-%m-%d"), "close": price})
        (Path(folder) / "TEST.json").write_text(
            json.dumps({"history_d1": bars}), encoding="utf-8"
        )

    def test_cagr_is_not_artificially_capped_at_100_percent(self):
        with tempfile.TemporaryDirectory() as folder:
            prices = [10 * (100 ** (i / 30)) for i in range(31)]
            self._write_history(folder, prices)
            result = get_historical_return_rate_with_details("TEST", folder)
            self.assertIsNotNone(result)
            self.assertGreater(result["annual_rate_percent"], 100)

    def test_non_positive_price_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            prices = [0 if i == 0 else 10 + i for i in range(31)]
            self._write_history(folder, prices)
            result = get_historical_return_rate_with_details("TEST", folder)
            self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
