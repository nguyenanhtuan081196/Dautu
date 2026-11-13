"""Run the existing price crawler as an isolated Render Cron Job.

The cron service has its own compute instance, so this workload never shares
CPU or an asyncio event loop with the public FastAPI process. The wrapper adds
MongoDB run auditing and jitter to the crawler's existing provider backoffs.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import datetime, timezone
from uuid import uuid4
from typing import Callable, Iterable


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _jittered_sleep(
    seconds: float,
    *,
    sleep_fn: Callable[[float], None] = time.sleep,
    random_fn: Callable[[float, float], float] = random.uniform,
) -> None:
    """Apply +/-20% jitter to an existing provider backoff interval."""
    delay = max(0.0, float(seconds))
    if delay == 0:
        return
    sleep_fn(random_fn(delay * 0.8, delay * 1.2))


def _normalize_symbols(symbols: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(
        str(symbol).strip().upper()
        for symbol in symbols
        if str(symbol).strip()
    ))


def run_price_job(*, symbols: list[str] | None = None, sessions: int = 30) -> dict:
    """Run one crawler invocation and persist a per-symbol audit record."""
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

    saved_symbols: list[str] = []
    original_save_stock = crawler.save_stock
    original_sleep = crawler.time.sleep
    original_argv = sys.argv[:]
    error_message = None

    def track_saved_stock(target_db, symbol, payload):
        original_save_stock(target_db, symbol, payload)
        saved_symbols.append(str(symbol).upper())

    def polite_sleep(seconds):
        _jittered_sleep(seconds, sleep_fn=original_sleep)

    crawler.save_stock = track_saved_stock
    crawler.time.sleep = polite_sleep
    sys.argv = [
        "fetch_data_local.py",
        "--symbols", ",".join(target_symbols),
        "--sessions", str(sessions),
    ]

    try:
        crawler.main()
    except Exception as exc:  # Preserve the failure in MongoDB before exiting non-zero.
        error_message = f"{type(exc).__name__}: {exc}"[:1000]
    finally:
        crawler.save_stock = original_save_stock
        crawler.time.sleep = original_sleep
        sys.argv = original_argv

    saved = sorted(set(saved_symbols))
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

    if status != "succeeded":
        return summary
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
