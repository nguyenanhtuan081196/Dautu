"""Unit tests for the opt-in SSI realtime collector (no network or Atlas required)."""
import unittest
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

    def test_feature_is_disabled_by_default(self):
        from unittest.mock import patch
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(realtime_enabled())
        with patch.dict("os.environ", {"ENABLE_REALTIME_CRAWLER": "true"}):
            self.assertTrue(realtime_enabled())


if __name__ == "__main__":
    unittest.main()
