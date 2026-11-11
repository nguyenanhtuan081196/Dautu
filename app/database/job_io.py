"""Mongo-backed input/output helpers shared by scheduled Dautu jobs."""
from __future__ import annotations

from typing import Any

from app.database.mongo import ensure_indexes, get_database
from app.database.repositories import (
    get_metadata,
    replace_symbol_results,
    set_metadata,
    upsert_financial_reports,
    upsert_history,
    upsert_stock,
)


def database():
    db = get_database()
    ensure_indexes(db)
    return db


def load_stocks(db=None) -> dict[str, dict[str, Any]]:
    db = db or database()
    return {doc["symbol"]: {k: v for k, v in doc.items() if k != "_id"}
            for doc in db.stocks.find({})}


def save_stock(db, symbol: str, payload: dict[str, Any]) -> None:
    upsert_stock(db, symbol, payload)


def load_history(db, symbol: str, interval: str = "D1") -> list[dict[str, Any]]:
    return list(db.price_history.find(
        {"symbol": symbol.upper(), "interval": interval.upper()}, {"_id": 0}
    ).sort("time", 1))


def load_all_daily_history(db) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for row in db.price_history.find({"interval": "D1"}, {"_id": 0}).sort(
        [("symbol", 1), ("time", 1)]
    ):
        result.setdefault(row["symbol"], []).append(row)
    return result


def load_financial_reports(db, symbol: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for doc in db.financial_reports.find({"symbol": symbol.upper()}):
        result[doc["report_type"]] = doc.get("data", [])
    return result


def load_screener(db) -> list[dict[str, Any]]:
    return list(db.screener_results.find({}, {"_id": 0}))


def save_screener(db, records: list[dict[str, Any]]) -> int:
    return replace_symbol_results(db, "screener_results", records)


def save_ai_analysis(db, symbol: str, payload: dict[str, Any]) -> None:
    db.ai_analyses.update_one(
        {"_id": symbol.upper()},
        {"$set": {"symbol": symbol.upper(), **payload}},
        upsert=True,
    )
    # Keep legacy AI fields on the stock document for existing consumers/API.
    db.stocks.update_one(
        {"_id": symbol.upper()},
        {"$set": payload, "$setOnInsert": {"symbol": symbol.upper()}},
        upsert=True,
    )


def save_simulation(db, symbol: str, payload: dict[str, Any]) -> None:
    db.simulations.replace_one(
        {"_id": symbol.upper()},
        {"_id": symbol.upper(), "symbol": symbol.upper(), **payload},
        upsert=True,
    )


def save_last_update(db, value: Any) -> None:
    set_metadata(db, "last_update", value)


def read_last_update(db):
    return get_metadata(db, "last_update")
