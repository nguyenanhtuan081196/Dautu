"""Run the Atlas-backed price crawler in bounded batches on Render Free."""
from __future__ import annotations

import argparse
import gc
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Iterable
from uuid import uuid4

DEFAULT_BATCH_SIZE = 5
RUN_LEASE_MINUTES = 90


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    """Normalize PyMongo's default naive UTC datetimes for safe comparisons."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_symbols(symbols: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(
        str(symbol).strip().upper()
        for symbol in symbols
        if str(symbol).strip()
    ))


def _chunks(values: list[str], size: int):
    for offset in range(0, len(values), size):
        yield values[offset:offset + size]


def _claim_run(collection, run_id: str, scheduled_for: str | None, total: int, sessions: int) -> bool:
    """Claim/reclaim a durable run; an unexpired running lease blocks duplicates."""
    from pymongo import ReturnDocument
    from pymongo.errors import DuplicateKeyError

    now = _utc_now()
    existing = collection.find_one({"_id": run_id})
    if existing and existing.get("status") == "succeeded":
        return False
    if existing:
        # Atomic compare-and-set: only one process can reclaim a partial/failed
        # run or an expired lease. A live lease blocks a second scheduler.
        claimed = collection.find_one_and_update(
            {
                "_id": run_id,
                "$or": [
                    {"status": {"$ne": "running"}},
                    {"lease_until": {"$lte": now}},
                    {"lease_until": {"$exists": False}},
                ],
            },
            {"$set": {
                "status": "running",
                "started_at": now,
                "lease_until": now + timedelta(minutes=RUN_LEASE_MINUTES),
                "recovered_after_restart": True,
                "error": None,
            }},
            return_document=ReturnDocument.AFTER,
        )
        return claimed is not None

    document = {
        "_id": run_id,
        "run_id": run_id,
        "job_name": "price_sync",
        "status": "running",
        "trigger": "render_free_scheduler" if scheduled_for else "manual",
        "scheduled_for": scheduled_for,
        "started_at": now,
        "lease_until": now + timedelta(minutes=RUN_LEASE_MINUTES),
        "symbols_total": total,
        "symbols_success": 0,
        "symbols_failed": total,
        "successful_symbols": [],
        "failed_symbols": [],
        "sessions_requested": sessions,
        "batch_size": DEFAULT_BATCH_SIZE,
    }
    try:
        collection.insert_one(document)
        return True
    except DuplicateKeyError:
        return False


def run_price_job(
    *,
    symbols: list[str] | None = None,
    sessions: int = 30,
    batch_size: int | None = None,
    scheduled_for: str | None = None,
) -> dict:
    """Refresh symbols in small batches; each batch writes directly to Atlas."""
    import fetch_data_local as crawler
    from app.database.job_io import database

    target_symbols = _normalize_symbols(
        symbols if symbols is not None else crawler.VN100_SYMBOLS
    )
    if not target_symbols:
        raise ValueError("The price pipeline requires at least one stock symbol")
    if sessions < 1:
        raise ValueError("sessions must be at least 1")

    configured_batch = batch_size or int(os.getenv("PRICE_BATCH_SIZE", str(DEFAULT_BATCH_SIZE)))
    bounded_batch = min(10, max(1, configured_batch))
    db = database()
    run_id = f"price_sync:{scheduled_for}" if scheduled_for else uuid4().hex
    if not _claim_run(db.pipeline_runs, run_id, scheduled_for, len(target_symbols), sessions):
        return {
            "run_id": run_id,
            "status": "skipped",
            "reason": "already_succeeded_or_an_unexpired_run_is_active",
            "symbols_success": 0,
            "symbols_failed": len(target_symbols),
        }

    saved_symbols: list[str] = []
    batch_errors: list[str] = []

    def record_saved_symbol(symbol: str) -> None:
        saved_symbols.append(str(symbol).strip().upper())

    try:
        for batch_number, batch in enumerate(_chunks(target_symbols, bounded_batch), start=1):
            logger_prefix = f"[batch {batch_number}]"
            print(f"{logger_prefix} Processing {len(batch)} symbols; memory is released after this batch.")
            try:
                returned = crawler.main(
                    ["--symbols", ",".join(batch), "--sessions", str(sessions)],
                    on_symbol_saved=record_saved_symbol,
                ) or []
                saved_symbols.extend(_normalize_symbols(returned))
            except Exception as exc:
                batch_error = f"{type(exc).__name__}: {exc}"[:500]
                batch_errors.append(batch_error)
                print(f"{logger_prefix} Batch failed: {batch_error}")
            finally:
                gc.collect()
            # Continue with later batches after an isolated batch failure.

        saved = sorted(set(saved_symbols) & set(target_symbols))
        failed = sorted(set(target_symbols) - set(saved))
        completed_at = _utc_now()
        error_message = "; ".join(batch_errors)[:1000] or None
        status = "succeeded" if not failed and error_message is None else (
            "partial" if saved else "failed"
        )
        summary = {
            "status": status,
            "completed_at": completed_at,
            "lease_until": completed_at,
            "duration_seconds": round((completed_at - _as_utc((db.pipeline_runs.find_one({"_id": run_id}) or {}).get("started_at", completed_at))).total_seconds(), 2),
            "symbols_total": len(target_symbols),
            "symbols_success": len(saved),
            "symbols_failed": len(failed),
            "successful_symbols": saved,
            "failed_symbols": failed,
            "sessions_requested": sessions,
            "batch_size": bounded_batch,
            "error": error_message,
        }
        db.pipeline_runs.update_one({"_id": run_id}, {"$set": summary})
        result = {"run_id": run_id, **summary}
        print(json.dumps(result, ensure_ascii=False, default=str))
        return result
    except Exception as exc:
        completed_at = _utc_now()
        db.pipeline_runs.update_one(
            {"_id": run_id},
            {"$set": {
                "status": "failed",
                "completed_at": completed_at,
                "lease_until": completed_at,
                "error": f"{type(exc).__name__}: {exc}"[:1000],
            }},
        )
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Dautu's Atlas-backed price sync")
    parser.add_argument("--symbols", default=None, help="Optional comma-separated symbols")
    parser.add_argument(
        "--sessions",
        type=int,
        default=int(os.getenv("PRICE_SESSIONS", "30")),
        help="Number of latest trading sessions to refresh",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.getenv("PRICE_BATCH_SIZE", str(DEFAULT_BATCH_SIZE))),
        help="Symbols per memory-bounded batch (1-10)",
    )
    args = parser.parse_args(argv)
    symbols = _normalize_symbols(args.symbols.split(",")) if args.symbols else None
    result = run_price_job(
        symbols=symbols,
        sessions=args.sessions,
        batch_size=args.batch_size,
    )
    return 0 if result["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
