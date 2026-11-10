import unittest

from advanced_screener import evaluate_stock, get_sector


class ScreenerCashConversionTests(unittest.TestCase):
    def test_unmapped_symbols_are_not_misclassified_as_defensive_sector(self):
        self.assertEqual(get_sector("UNKNOWN"), "CHUA_PHAN_LOAI")

    def test_duplicate_sector_symbol_is_resolved_to_one_intended_group(self):
        self.assertEqual(get_sector("PHR"), "NGUYEN_VAT_LIEU_CHU_KY")

    def test_unclassified_stock_does_not_receive_defensive_sector_points(self):
        result = evaluate_stock("UNKNOWN", self._stock())
        self.assertEqual(result["sector"], "CHUA_PHAN_LOAI")
        self.assertIn("bỏ qua điểm đặc thù ngành", result["fundamental_notes"])
        self.assertNotIn("LN tăng trưởng tốt", result["fundamental_notes"])

    def _stock(self, **overrides):
        data = {
            "pe": 10,
            "pb": 1.5,
            "roe": 15,
            "roa": 3,
            "dividend_yield": 1,
            "recommendation": "ĐANG TÍCH LŨY NỀN",
            "close": 10000,
            "cfo_latest": 10,
            "cfo_ttm": 100,
            "net_profit_ttm": 100,
            "liabilities_to_equity": 0.8,
            "gross_margin": 20,
            "bctc_history": [{
                "profit_growth_yoy": 12,
                "credit_growth_yoy": 0
            }]
        }
        data.update(overrides)
        return data

    def test_cash_conversion_bonus_uses_ttm_not_latest_quarter(self):
        result = evaluate_stock("FPT", self._stock(cfo_latest=-100, cfo_ttm=90))
        self.assertIn("CFO TTM chuyển đổi tiền mặt tốt", result["fundamental_notes"])
        self.assertEqual(result["cfo_ttm"], 90)

    def test_missing_ttm_cash_flow_is_not_scored_as_zero_or_positive(self):
        result = evaluate_stock("FPT", self._stock(cfo_ttm=None))
        self.assertNotIn("CFO TTM chuyển đổi tiền mặt tốt", result["fundamental_notes"])
        self.assertIn("Chưa đủ 4 quý liên tiếp", result["fundamental_notes"])

    def test_negative_ttm_cash_flow_warns_even_if_latest_quarter_is_positive(self):
        result = evaluate_stock("FPT", self._stock(cfo_latest=50, cfo_ttm=-10))
        self.assertIn("CFO TTM âm", result["fundamental_notes"])


if __name__ == "__main__":
    unittest.main()
