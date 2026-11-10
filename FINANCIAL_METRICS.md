# Financial metric definitions

All monetary amounts below are expressed in VND billions in the generated data files unless otherwise noted.

| Field | Definition | Missing-data behavior |
|---|---|---|
| cfo_latest | Net cash from operating activities for the latest available quarter | null when no CFO record exists for that exact quarter |
| cfo_ttm | Sum of CFO for the latest four consecutive quarter labels | null if any of the four quarter labels is missing or invalid |
| net_profit_ttm | Sum of net profit after tax for the same latest four consecutive quarter labels | null if any of the four quarter labels is missing or invalid |
| liabilities_to_equity | Total liabilities divided by shareholders' equity at the latest balance-sheet period | null when either value is missing or equity is not positive |
| debt_to_equity | Legacy compatibility alias for liabilities_to_equity; it is not interest-bearing debt divided by equity | same as liabilities_to_equity |
| gross_margin | Gross profit divided by net revenue for the latest income-statement quarter | null when required values are missing; zero for banking/securities statements where this traditional margin is not applicable |

## Screener cash-conversion rule

For non-bank and non-securities companies, the screener compares CFO TTM with net-profit TTM:

- +5 points when both values exist, net-profit TTM is positive, and CFO TTM is at least 80% of net-profit TTM.
- -5 points when both values exist, net-profit TTM is positive, and CFO TTM is negative.
- No cash-conversion points when either TTM value is missing or net-profit TTM is non-positive. A note explains when four consecutive quarters are unavailable.

This avoids comparing one quarter of cash flow with four quarters of accounting profit.

## Period and provider assumptions

The extractor interprets period labels such as 2026-Q1 as discrete quarterly observations and requires four consecutive quarters. The current VNStock quarter payload samples inspected for FPT, HPG, ACB, and VCB contain distinct Q1, Q2, and Q3 observations; nevertheless, provider changes and year-end restatements must be monitored. Do not combine cumulative year-to-date values with standalone quarterly values.

## Interpretation warning

Total liabilities/equity is a broad balance-sheet leverage proxy. It includes operating liabilities and other non-interest-bearing obligations. It must not be presented as interest-bearing debt/equity. For banks and securities firms, this ratio has a different economic meaning and is not used in the current non-financial-company scoring rule.
