"""Unit tests for the opt-in SSI realtime collector (no network or Atlas required)."""
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from datetime import datetime, timezone

from app.pipeline.realtime_collector import (
    chunks, is_after_close, is_market_window, normalize_trade, realtime_enabled,
)


class RealtimeCollectorTests(unittest.TestCase):
    def test_market_hours_include_morning_and_afternoon_sessions(self):
        self.assertTrue(is_market_window(datetime.fromisoformat("2026-11-16T09:00:00+07:00")))
        self.assertTrue(is_market_window(datetime.fromisoformat("2026-11-16T14:59:00+07:00")))
        self.assertFalse(is_market_window(datetime.fromisoformat("2026-11-16T11:45:00+07:00")))
        self.assertFalse(is_market_window(datetime.fromisoformat("2026-11-16T12:59:00+07:00")))
        self.assertFalse(is_market_window(datetime.fromisoformat("2026-11-15T10:00:00+07:00")))

    def test_after_close_is_weekday_only(self):
        self.assertTrue(is_after_close(datetime.fromisoformat("2026-11-16T15:00:00+07:00")))
        self.assertFalse(is_after_close(datetime.fromisoformat("2026-11-15T15:30:00+07:00")))

    def test_symbols_are_subscribed_in_bounded_groups(self):
        groups = list(chunks([f"S{i}" for i in range(61)], 25))
        self.assertEqual([len(group) for group in groups], [25, 25, 11])

    def test_normalize_trade_supports_ssi_field_names(self):
        received = datetime(2026, 11, 16, 3, 0, tzinfo=timezone.utc)
        item = normalize_trade({
            "s": "ssi", "p": "45500", "q": "1000", "a": "45350",
            "o": "45000", "h": "45800", "l": "44900", "v": "1250000",
            "si": "B", "t": "2026/11/16 10:00:00",
        }, received)
        self.assertEqual(item["symbol"], "SSI")
        self.assertEqual(item["price"], 45500.0)
        self.assertEqual(item["total_volume"], 1250000.0)
        self.assertEqual(item["trading_date"], "2026-11-16")

    def test_invalid_or_empty_trade_is_ignored(self):
        self.assertIsNone(normalize_trade({"s": "SSI", "p": "N/A"}))
        self.assertIsNone(normalize_trade({"p": "45000"}))

    def test_finalizer_upserts_one_d1_candle_per_latest_symbol(self):
        class Prices:
            def find(self, query):
                self.query = query
                return [{
                    "_id": "SSI", "symbol": "SSI", "trading_date": "2026-11-16",
                    "price": 45500, "open": 45000, "high": 45800, "low": 44900,
                    "total_volume": 1250000,
                }]
        class History:
            def __init__(self):
                self.saved = []
            def replace_one(self, query, document, upsert=False):
                self.saved.append((query, document, upsert))
        prices, history = Prices(), History()
        fake_db = SimpleNamespace(realtime_prices=prices, price_history=history)
        with patch("app.pipeline.realtime_collector.get_database", return_value=fake_db):
            from app.pipeline.realtime_collector import _finalize_daily_candles
            count = _finalize_daily_candles(datetime(2026, 11, 16).date())
        self.assertEqual(count, 1)
        query, candle, upsert = history.saved[0]
        self.assertEqual(query["_id"], "SSI:D1:2026-11-16")
        self.assertEqual(candle["close"], 45500)
        self.assertEqual(candle["volume"], 1250000)
        self.assertTrue(upsert)

    def test_feature_is_disabled_by_default(self):
        from unittest.mock import patch
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(realtime_enabled())
        with patch.dict("os.environ", {"ENABLE_REALTIME_CRAWLER": "true"}):
            self.assertTrue(realtime_enabled())


if __name__ == "__main__":
    unittest.main()
