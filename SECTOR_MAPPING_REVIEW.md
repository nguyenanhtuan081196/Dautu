# Sector mapping review

The screener's sector mapping was compared against the 99 unique tickers in crawl_bctc.py.

- 86 tickers have one mapped sector.
- 13 tickers remain unclassified: VJC, LIG, TCD, TLG, VDP, VPG, VTO, IMP, SBA, TID, NTC, VOS, HAG.
- PHR appeared in both real estate and cyclical materials. The duplicate real-estate assignment was removed; PHR now maps once to cyclical materials.

## Why unclassified is safer

Previously, every ticker missing from SECTOR_MAPPING silently fell into SAN_XUAT_TIEU_DUNG_PHONG_THU. That incorrectly applied defensive-manufacturing thresholds to unrelated businesses and displayed a misleading industry label.

Unmapped tickers now use CHUA_PHAN_LOAI:
- They are visible in the UI's sector filter under "Chưa phân loại".
- They do not receive the 35-point sector-specific score component.
- Shared metrics and technical/valuation scoring continue to work.
- No sector has been guessed from the ticker symbol alone.

## Manual review needed

Confirm the correct sector and scoring framework for each of the 13 symbols before adding them to SECTOR_MAPPING. In particular, aviation, construction, pharmaceuticals, shipping, agriculture, industrial parks, and trading businesses should not automatically share the same thresholds.
