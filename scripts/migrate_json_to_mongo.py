"""Import legacy JSON snapshots into MongoDB Atlas.

Dry-run is the default. Writes require --apply. By default, an apply is
refused unless all target collections are empty; --allow-existing is an
explicit opt-in to idempotent upserts into a populated database.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
# When invoked as "python scripts/migrate_json_to_mongo.py", Python places
# scripts/ (not the repository root) at sys.path[0]. Add the project root so
# the app package can be imported consistently in GitHub Actions and locally.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database.mongo import ensure_indexes, get_database
from app.database.repositories import (
    replace_symbol_results,
    set_metadata,
    upsert_financial_reports,
    upsert_history,
    upsert_stock,
)
TARGET_COLLECTIONS = (
    "stocks", "price_history", "financial_reports", "screener_results",
    "ai_analyses", "simulations", "dataset_versions", "app_metadata",
)
AI_FIELDS = (
    "bctc", "catalyst", "risks", "outlook", "ai_recommendation",
    "ai_price_zone", "macro_view", "ai_updated_at",
)


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read valid JSON from {path.relative_to(ROOT)}: {exc}") from exc


def load_sources(root: Path) -> dict[str, Any]:
    stock_data = read_json(root / "data.json", {})
    screener_data = read_json(root / "screener_results.json", [])
    rates_data = read_json(root / "symbol_sim_rates.json", {})
    details_data = read_json(root / "quarterly_mean_details.json", {})
    last_update_data = read_json(root / "last_update.json", {})
    for name, value, expected in (
        ("data.json", stock_data, dict),
        ("screener_results.json", screener_data, list),
        ("symbol_sim_rates.json", rates_data, dict),
        ("quarterly_mean_details.json", details_data, dict),
    ):
        if not isinstance(value, expected):
            raise ValueError(f"{name} must contain a JSON {expected.__name__}")
    history_dir, bctc_dir = root / "history", root / "bctc_data"
    history_files = sorted(history_dir.glob("*.json")) if history_dir.exists() else []
    bctc_files = sorted(bctc_dir.glob("*.json")) if bctc_dir.exists() else []
    return {
        "stocks": stock_data,
        "screener": screener_data,
        "rates": rates_data,
        "details": details_data,
        "last_update": last_update_data,
        "history_files": history_files,
        "bctc_files": bctc_files,
    }


def inspect_sources(root: Path) -> dict[str, int]:
    sources = load_sources(root)
    history_bars = 0
    report_types = 0
    for path in sources["history_files"]:
        payload = read_json(path, {})
        if not isinstance(payload, dict):
            raise ValueError(f"{path.relative_to(root)} must contain a JSON object")
        for key in ("history_d1", "history_w1", "history_mn"):
            rows = payload.get(key, []) or []
            if not isinstance(rows, list):
                raise ValueError(f"{path.relative_to(root)}: {key} must be a list")
            history_bars += len(rows)
    for path in sources["bctc_files"]:
        payload = read_json(path, {})
        if not isinstance(payload, dict):
            raise ValueError(f"{path.relative_to(root)} must contain a JSON object")
        report_types += sum(key in payload for key in ("balance_sheet", "income_statement", "cash_flow"))
    return {
        "stocks": len(sources["stocks"]),
        "history_symbols": len(sources["history_files"]),
        "history_bars": history_bars,
        "financial_report_files": len(sources["bctc_files"]),
        "financial_report_types": report_types,
        "screener_results": len(sources["screener"]),
        "simulations": len(set(sources["rates"]) | set(sources["details"])),
    }


def migrate(apply: bool = False, allow_existing: bool = False, root: Path = ROOT) -> dict[str, int]:
    counts = inspect_sources(root)
    if not apply:
        return counts

    db = get_database()
    existing = {
        name: db[name].estimated_document_count()
        for name in TARGET_COLLECTIONS
    }
    populated = {name: count for name, count in existing.items() if count}
    if populated and not allow_existing:
        raise RuntimeError(
            "Import stopped: target collections are not empty: "
            + json.dumps(populated, ensure_ascii=False)
            + ". Review the data, then rerun with --allow-existing only if overwriting matching IDs is intended."
        )

    sources = load_sources(root)
    ensure_indexes(db)

    for symbol, payload in sources["stocks"].items():
        if not isinstance(payload, dict):
            raise ValueError(f"data.json entry {symbol} must be an object")
        upsert_stock(db, symbol, payload)
        ai_payload = {key: payload[key] for key in AI_FIELDS if key in payload}
        if ai_payload:
            db.ai_analyses.replace_one(
                {"_id": symbol.upper()},
                {"_id": symbol.upper(), "symbol": symbol.upper(), **ai_payload},
                upsert=True,
            )

    imported_history = 0
    for path in sources["history_files"]:
        imported_history += upsert_history(db, path.stem.upper(), read_json(path, {}))
    imported_reports = 0
    for path in sources["bctc_files"]:
        imported_reports += upsert_financial_reports(db, path.stem.upper(), read_json(path, {}))

    imported_screener = replace_symbol_results(db, "screener_results", sources["screener"])
    symbols = sorted(set(sources["rates"]) | set(sources["details"]))
    for symbol in symbols:
        payload = {
            **(sources["rates"].get(symbol) or {}),
            **(sources["details"].get(symbol) or {}),
            "_id": symbol.upper(),
            "symbol": symbol.upper(),
        }
        db.simulations.replace_one({"_id": symbol.upper()}, payload, upsert=True)

    if sources["last_update"]:
        set_metadata(db, "last_update", sources["last_update"])
    version_id = "legacy-json-import"
    db.dataset_versions.update_one(
        {"_id": version_id},
        {"$set": {
            "version_id": version_id, "source": "legacy_json", "status": "completed",
            "stocks": counts["stocks"], "history_bars": imported_history,
            "financial_report_types": imported_reports, "screener_results": imported_screener,
            "simulations": counts["simulations"],
        }},
        upsert=True,
    )
    set_metadata(db, "active_dataset_version", version_id)
    set_metadata(db, "migration_source", "legacy_json")
    set_metadata(db, "migration_status", "completed")
    counts["history_bars"] = imported_history
    counts["financial_report_types"] = imported_reports
    counts["screener_results"] = imported_screener
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write data to Atlas; otherwise perform a local dry-run.")
    parser.add_argument("--allow-existing", action="store_true", help="Allow upserts when target collections already contain documents.")
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository/data snapshot root.")
    args = parser.parse_args()
    counts = migrate(apply=args.apply, allow_existing=args.allow_existing, root=args.root.resolve())
    print(json.dumps({"mode": "apply" if args.apply else "dry-run", "database": "configured via environment" if args.apply else None, "counts": counts}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
