"""One-way, idempotent importer from the legacy JSON files into MongoDB Atlas.

Default mode is a dry run. Pass --apply to write to Atlas. Existing MongoDB
records not present in the JSON files are never deleted.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.database.mongo import ensure_indexes, get_database
from app.database.repositories import (
    replace_symbol_results,
    set_metadata,
    upsert_financial_reports,
    upsert_history,
    upsert_stock,
)

ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def migrate(apply: bool = False) -> dict[str, int]:
    stock_data = read_json(ROOT / "data.json", {})
    screener_data = read_json(ROOT / "screener_results.json", [])
    rates_data = read_json(ROOT / "symbol_sim_rates.json", {})
    details_data = read_json(ROOT / "quarterly_mean_details.json", {})
    last_update_data = read_json(ROOT / "last_update.json", {})

    history_files = sorted((ROOT / "history").glob("*.json")) if (ROOT / "history").exists() else []
    bctc_files = sorted((ROOT / "bctc_data").glob("*.json")) if (ROOT / "bctc_data").exists() else []

    counts = {
        "stocks": len(stock_data),
        "history_symbols": len(history_files),
        "history_bars": 0,
        "financial_report_files": len(bctc_files),
        "financial_report_types": 0,
        "screener_results": len(screener_data),
        "simulations": len(set(rates_data) | set(details_data)),
    }

    if not apply:
        for path in history_files:
            payload = read_json(path, {})
            counts["history_bars"] += sum(len(payload.get(k, []) or []) for k in ("history_d1", "history_w1", "history_mn"))
        for path in bctc_files:
            payload = read_json(path, {})
            counts["financial_report_types"] += sum(k in payload for k in ("balance_sheet", "income_statement", "cash_flow"))
        return counts

    db = get_database()
    ensure_indexes(db)

    for symbol, payload in stock_data.items():
        if isinstance(payload, dict):
            upsert_stock(db, symbol, payload)
            ai_fields = (
                "bctc", "catalyst", "risks", "outlook", "ai_recommendation",
                "ai_price_zone", "macro_view", "ai_updated_at",
            )
            ai_payload = {key: payload[key] for key in ai_fields if key in payload}
            if ai_payload:
                db.ai_analyses.replace_one(
                    {"_id": symbol.upper()},
                    {"_id": symbol.upper(), "symbol": symbol.upper(), **ai_payload},
                    upsert=True,
                )

    for path in history_files:
        symbol = path.stem.upper()
        counts["history_bars"] += upsert_history(db, symbol, read_json(path, {}))

    for path in bctc_files:
        symbol = path.stem.upper()
        counts["financial_report_types"] += upsert_financial_reports(db, symbol, read_json(path, {}))

    counts["screener_results"] = replace_symbol_results(db, "screener_results", screener_data)

    symbols = sorted(set(rates_data) | set(details_data))
    for symbol in symbols:
        payload = {
            **(rates_data.get(symbol) or {}),
            **(details_data.get(symbol) or {}),
            "_id": symbol.upper(),
            "symbol": symbol.upper(),
        }
        db.simulations.replace_one({"_id": symbol.upper()}, payload, upsert=True)

    if last_update_data:
        set_metadata(db, "last_update", last_update_data)
    version_id = "legacy-json-import"
    db.dataset_versions.update_one(
        {"_id": version_id},
        {
            "$set": {
                "version_id": version_id,
                "source": "legacy_json",
                "status": "completed",
                "stocks": counts["stocks"],
                "history_bars": counts["history_bars"],
                "financial_report_types": counts["financial_report_types"],
                "screener_results": counts["screener_results"],
                "simulations": counts["simulations"],
            }
        },
        upsert=True,
    )
    set_metadata(db, "active_dataset_version", version_id)
    set_metadata(db, "migration_source", "legacy_json")
    set_metadata(db, "migration_status", "completed")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write imported data to MongoDB. Without this flag, only count records.")
    args = parser.parse_args()
    counts = migrate(apply=args.apply)
    print(json.dumps({"mode": "apply" if args.apply else "dry-run", "counts": counts}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
