import unittest
from datetime import datetime, timedelta

from simulator import get_historical_return_rate_with_details


class HistoricalCagrTests(unittest.TestCase):
    def _make_history(self, prices):
        end = datetime(2025, 12, 31)
        count = len(prices)
        bars = []
        for index, price in enumerate(prices):
            day = end - timedelta(days=round((count - 1 - index) * (5 * 365.25) / (count - 1)))
            bars.append({"time": day.strftime("%Y-%m-%d"), "close": price})
        return bars

    def test_cagr_is_not_artificially_capped_at_100_percent(self):
        prices = [10 * (100 ** (i / 30)) for i in range(31)]
        result = get_historical_return_rate_with_details("TEST", self._make_history(prices))
        self.assertIsNotNone(result)
        self.assertGreater(result["annual_rate_percent"], 100)

    def test_non_positive_price_is_rejected(self):
        prices = [0 if i == 0 else 10 + i for i in range(31)]
        result = get_historical_return_rate_with_details("TEST", self._make_history(prices))
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
