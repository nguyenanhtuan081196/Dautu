"""Compatibility tests for the current vnstock v6 price API."""
import os
import unittest
from unittest.mock import Mock, patch

import pandas as pd

import fetch_data_local as crawler


class VnstockV6PriceTests(unittest.TestCase):
    def test_price_history_uses_v6_market_ohlcv_contract(self):
        frame = pd.DataFrame([{"time": "2026-11-12", "close": 100}])
        market = Mock()
        market.equity.return_value.ohlcv.return_value = frame

        with patch.object(crawler, "Market", return_value=market) as market_factory:
            with patch.dict(os.environ, {"VNSTOCK_MARKET_SOURCE": "fhsc"}, clear=False):
                result = crawler.fetch_history_with_fallback("FPT", "2026-10-01", "2026-11-13")

        self.assertIs(result, frame)
        market_factory.assert_called_once_with("fhsc")
        market.equity.assert_called_once_with("FPT")
        market.equity.return_value.ohlcv.assert_called_once_with(
            start="2026-10-01",
            end="2026-11-13",
            interval="1D",
        )

    def test_price_history_uses_configured_fallback_source(self):
        frame = pd.DataFrame([{"time": "2026-11-12", "close": 100}])
        primary_market = Mock()
        primary_market.equity.return_value.ohlcv.side_effect = RuntimeError("primary unavailable")
        fallback_market = Mock()
        fallback_market.equity.return_value.ohlcv.return_value = frame
        markets = {"fhsc": primary_market, "ssi": fallback_market}

        def market_factory(source):
            return markets[source]

        with patch.object(crawler, "Market", side_effect=market_factory) as factory:
            with patch.object(crawler.time, "sleep"):
                with patch.dict(
                    os.environ,
                    {
                        "VNSTOCK_MARKET_SOURCE": "fhsc",
                        "VNSTOCK_MARKET_FALLBACK_SOURCE": "ssi",
                    },
                    clear=False,
                ):
                    result = crawler.fetch_history_with_fallback(
                        "FPT", "2026-10-01", "2026-11-13"
                    )

        self.assertIs(result, frame)
        self.assertEqual(
            [call.args[0] for call in factory.call_args_list],
            ["fhsc", "fhsc", "ssi"],
        )


if __name__ == "__main__":
    unittest.main()
