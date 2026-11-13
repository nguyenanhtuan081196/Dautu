"""Run the Atlas-backed price crawler as an isolated Render Cron Job."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Iterable
from uuid import uuid4


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_symbols(symbols: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(
        str(symbol).strip().upper()
        for symbol in symbols
        if str(symbol).strip()
    ))


def run_price_job(*, symbols: list[str] | None = None, sessions: int = 30) -> dict:
    """Run one price sync and persist a complete audit record in Atlas."""
    import fetch_data_local as crawler
    from app.database.job_io import database

    target_symbols = _normalize_symbols(
        symbols if symbols is not None else crawler.VN100_SYMBOLS
    )
    if not target_symbols:
        raise ValueError("The price pipeline requires at least one stock symbol")
    if sessions < 1:
        raise ValueError("sessions must be at least 1")

    db = database()
    run_id = uuid4().hex
    started_at = _utc_now()
    db.pipeline_runs.insert_one({
        "_id": run_id,
        "run_id": run_id,
        "job_name": "price_sync",
        "status": "running",
        "trigger": "render_cron",
        "started_at": started_at,
        "symbols_total": len(target_symbols),
        "symbols_success": 0,
        "symbols_failed": 0,
        "failed_symbols": [],
        "sessions_requested": sessions,
    })

    error_message = None
    observed_saved_symbols: list[str] = []

    def record_saved_symbol(symbol: str) -> None:
        observed_saved_symbols.append(str(symbol).strip().upper())

    try:
        returned_symbols = crawler.main(
            [
                "--symbols", ",".join(target_symbols),
                "--sessions", str(sessions),
            ],
            on_symbol_saved=record_saved_symbol,
        ) or []
        observed_saved_symbols.extend(_normalize_symbols(returned_symbols))
    except Exception as exc:
        # Keep already confirmed per-symbol Atlas writes even if a later step fails.
        error_message = f"{type(exc).__name__}: {exc}"[:1000]

    saved = sorted(set(_normalize_symbols(observed_saved_symbols)) & set(target_symbols))
    failed = sorted(set(target_symbols) - set(saved))
    completed_at = _utc_now()
    status = "succeeded" if not failed and error_message is None else (
        "partial" if saved else "failed"
    )
    summary = {
        "run_id": run_id,
        "job_name": "price_sync",
        "status": status,
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_seconds": round((completed_at - started_at).total_seconds(), 2),
        "symbols_total": len(target_symbols),
        "symbols_success": len(saved),
        "symbols_failed": len(failed),
        "successful_symbols": saved,
        "failed_symbols": failed,
        "sessions_requested": sessions,
        "error": error_message,
    }
    db.pipeline_runs.update_one(
        {"run_id": run_id},
        {"$set": {key: value for key, value in summary.items() if key != "run_id"}},
    )
    print(json.dumps(summary, ensure_ascii=False, default=str))
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Dautu's scheduled price sync")
    parser.add_argument(
        "--symbols",
        default=None,
        help="Optional comma-separated symbols; defaults to the configured VN100 universe",
    )
    parser.add_argument(
        "--sessions",
        type=int,
        default=int(__import__("os").getenv("PRICE_SESSIONS", "30")),
        help="Number of latest trading sessions to refresh",
    )
    args = parser.parse_args(argv)
    symbols = _normalize_symbols(args.symbols.split(",")) if args.symbols else None
    result = run_price_job(symbols=symbols, sessions=args.sessions)
    return 0 if result["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
