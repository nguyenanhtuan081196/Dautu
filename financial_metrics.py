"""Source-aware fundamental metric extraction from quarterly statements."""
import json
import math
import os


def extract_advanced_metrics_from_bctc(symbol, bctc_dir="bctc_data"):
    """Extract comparable latest-quarter and TTM fundamentals from raw quarterly statements.

    Cash-flow and income-statement figures are compared only when four consecutive
    quarterly observations are available. Missing values remain None, never a fake zero.
    """
    empty = {
        "cfo_latest": None,
        "cfo_ttm": None,
        "debt_to_equity": None,
        "liabilities_to_equity": None,
        "gross_margin": None,
        "net_profit_ttm": None,
    }
    filepath = os.path.join(bctc_dir, f"{symbol}.json")
    if not os.path.exists(filepath):
        return empty.copy()

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, TypeError):
        return empty.copy()

    balance_sheet = data.get("balance_sheet") or []
    cash_flow = data.get("cash_flow") or []
    income_statement = data.get("income_statement") or []

    def finite_value(value):
        try:
            number = float(value)
            return number if math.isfinite(number) else None
        except (TypeError, ValueError):
            return None

    def period_number(period):
        try:
            year, quarter = str(period).split("-Q", 1)
            year, quarter = int(year), int(quarter)
            if quarter not in (1, 2, 3, 4):
                return None
            return year * 4 + quarter - 1
        except (TypeError, ValueError):
            return None

    def quarterly_values(rows, ids):
        # Use one recognized line item per period and reject duplicate periods.
        values = {}
        duplicates = set()
        for row in rows:
            if row.get("id") not in ids:
                continue
            period = row.get("period")
            ordinal = period_number(period)
            value = finite_value(row.get("value"))
            if ordinal is None or value is None:
                continue
            if ordinal in duplicates:
                continue
            if ordinal in values:
                # Duplicate observations for one quarter are ambiguous (e.g. a restatement
                # or mixed provider series). Do not silently choose whichever row appears first.
                values.pop(ordinal, None)
                duplicates.add(ordinal)
                continue
            values[ordinal] = (str(period), value)
        return values

    bs_periods = [period_number(row.get("period")) for row in balance_sheet]
    is_periods = [period_number(row.get("period")) for row in income_statement]
    available_periods = [p for p in bs_periods + is_periods if p is not None]
    if not available_periods:
        return empty.copy()
    latest_ordinal = max(available_periods)
    latest_period = next(
        (row.get("period") for row in balance_sheet if period_number(row.get("period")) == latest_ordinal),
        None,
    ) or next(
        (row.get("period") for row in income_statement if period_number(row.get("period")) == latest_ordinal),
        None,
    )

    cfo_ids = {
        "CF_NET_CASH_FLOWS_FROM_OPERATING_ACTIVITIES",
        "CF_OPERATE_CASH_FLOW",
        "CFO",
        "CF_NET_CASH",
    }
    cfo_by_period = quarterly_values(cash_flow, cfo_ids)
    cfo_latest_value = cfo_by_period.get(latest_ordinal)
    cfo_latest = cfo_latest_value[1] if cfo_latest_value else None

    pat_ids = {
        "IS_NET_PROFIT_AFTER_TAX",
        "NET_PROFIT_AFTER_TAX",
        "IS_PROFIT_AFTER_TAX",
    }
    pat_by_period = quarterly_values(income_statement, pat_ids)

    def contiguous_ttm(period_map):
        required = [latest_ordinal - offset for offset in (3, 2, 1, 0)]
        if any(period not in period_map for period in required):
            return None
        return sum(period_map[period][1] for period in required)

    cfo_ttm_value = contiguous_ttm(cfo_by_period)
    net_profit_ttm_value = contiguous_ttm(pat_by_period)

    bs_values = {}
    for row in balance_sheet:
        if period_number(row.get("period")) != latest_ordinal:
            continue
        value = finite_value(row.get("value"))
        if value is not None:
            bs_values[row.get("id")] = value

    total_liabilities = bs_values.get("BS_TOTAL_LIABILITIES", bs_values.get("TOTAL_LIABILITIES"))
    equity = bs_values.get("BS_EQUITY", bs_values.get("EQUITY"))
    liabilities_to_equity = (
        round(total_liabilities / equity, 2)
        if total_liabilities is not None and equity is not None and equity > 0
        else None
    )

    income_values = {}
    for row in income_statement:
        if period_number(row.get("period")) == latest_ordinal:
            value = finite_value(row.get("value"))
            if value is not None:
                income_values[row.get("id")] = value

    gross_profit = next(
        (income_values[key] for key in ("IS_GROSS_PROFIT", "GROSS_PROFIT") if key in income_values),
        None,
    )
    revenue = next(
        (income_values[key] for key in ("IS_NET_REVENUE", "REVENUE", "NET_REVENUE", "IS_TOTAL_REVENUE") if key in income_values),
        None,
    )
    is_bank_or_sec = "IS_NET_INTEREST_INCOME" in income_values
    gross_margin = (
        0.0 if is_bank_or_sec
        else round(gross_profit / revenue * 100, 1)
        if gross_profit is not None and revenue is not None and revenue > 0
        else None
    )

    return {
        "cfo_latest": round(cfo_latest / 1e9, 2) if cfo_latest is not None else None,
        "cfo_ttm": round(cfo_ttm_value / 1e9, 2) if cfo_ttm_value is not None else None,
        "debt_to_equity": liabilities_to_equity,  # Legacy key; this is total liabilities/equity.
        "liabilities_to_equity": liabilities_to_equity,
        "gross_margin": gross_margin,
        "net_profit_ttm": round(net_profit_ttm_value / 1e9, 2) if net_profit_ttm_value is not None else None,
    }
