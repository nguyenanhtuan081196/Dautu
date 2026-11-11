"""Small repository layer. Keep MongoDB-specific queries out of jobs and API routes."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo import ReplaceOne
from pymongo.database import Database


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def upsert_stock(db: Database, symbol: str, payload: dict[str, Any]) -> None:
    document = {**payload, "_id": symbol.upper(), "symbol": symbol.upper()}
    db.stocks.replace_one({"_id": symbol.upper()}, document, upsert=True)


def upsert_history(db: Database, symbol: str, history: dict[str, Any]) -> int:
    """Store D1/W1/MN bars as individual documents keyed by symbol+interval+time."""
    symbol = symbol.upper()
    operations = []
    for interval_key in ("history_d1", "history_w1", "history_mn"):
        interval = interval_key.removeprefix("history_").upper()
        for bar in history.get(interval_key, []) or []:
            time_value = str(bar.get("time", ""))[:10]
            if not time_value:
                continue
            document = {
                "_id": f"{symbol}:{interval}:{time_value}",
                "symbol": symbol,
                "interval": interval,
                "time": time_value,
                **bar,
                "updated_at": utc_now(),
            }
            operations.append(
                ReplaceOne(
                    {"_id": document["_id"]},
                    document,
                    upsert=True,
                )
            )
    if operations:
        db.price_history.bulk_write(operations, ordered=False)
    return len(operations)


def upsert_financial_reports(db: Database, symbol: str, reports: dict[str, Any]) -> int:
    symbol = symbol.upper()
    count = 0
    for report_type in ("balance_sheet", "income_statement", "cash_flow"):
        if report_type not in reports:
            continue
        db.financial_reports.replace_one(
            {"_id": f"{symbol}:{report_type}"},
            {
                "_id": f"{symbol}:{report_type}",
                "symbol": symbol,
                "report_type": report_type,
                "data": reports[report_type],
                "source_updated_at": reports.get("updated_at"),
                "updated_at": utc_now(),
            },
            upsert=True,
        )
        count += 1
    return count


def replace_symbol_results(
    db: Database, collection_name: str, records: list[dict[str, Any]], run_id: str | None = None
) -> int:
    collection = db[collection_name]
    operations = []
    for record in records:
        symbol = str(record.get("symbol", "")).upper()
        if not symbol:
            continue
        doc = {**record, "_id": symbol, "symbol": symbol}
        if run_id:
            doc["run_id"] = run_id
        doc["updated_at"] = utc_now()
        operations.append(ReplaceOne({"_id": symbol}, doc, upsert=True))
    if operations:
        collection.bulk_write(operations, ordered=False)
    return len(operations)


def set_metadata(db: Database, key: str, value: Any) -> None:
    db.app_metadata.update_one(
        {"_id": key},
        {"$set": {"key": key, "value": value, "updated_at": utc_now()}},
        upsert=True,
    )


def get_metadata(db: Database, key: str) -> dict[str, Any] | None:
    return db.app_metadata.find_one({"_id": key}, {"_id": 0})
