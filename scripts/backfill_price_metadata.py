"""Idempotently backfill price metadata from the successful 2026-11-13 Atlas run.

This script never starts a crawler or modifies stock/history collections. It only
creates app_metadata/_id=price_sync when that metadata document is absent.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError


SOURCE_RUN_ID = "price_sync:2026-11-13"
METADATA_ID = "price_sync"


def backfill(db: Any) -> dict[str, Any]:
    """Create metadata from the confirmed successful pipeline run, if absent."""
    existing = db.app_metadata.find_one({"_id": METADATA_ID})
    if existing:
        return {
            "status": "already_present",
            "metadata_id": METADATA_ID,
            "last_updated": existing.get("last_updated"),
        }

    run = db.pipeline_runs.find_one(
        {"_id": SOURCE_RUN_ID, "status": "succeeded"}
    )
    if not run:
        raise RuntimeError(
            f"Required successful source run not found: {SOURCE_RUN_ID}"
        )

    completed_at = run.get("completed_at")
    if not isinstance(completed_at, datetime):
        raise RuntimeError("Source run has no valid completed_at timestamp")

    symbols_total = int(run.get("symbols_total", 0))
    symbols_success = int(run.get("symbols_success", 0))
    symbols_failed = int(run.get("symbols_failed", 0))
    if symbols_total <= 0 or symbols_success != symbols_total or symbols_failed != 0:
        raise RuntimeError(
            "Source run is not a complete successful run; refusing metadata backfill"
        )

    metadata = {
        "_id": METADATA_ID,
        "key": METADATA_ID,
        "last_updated": completed_at,
        "status": "succeeded",
        "symbols_total": symbols_total,
        "symbols_success": symbols_success,
        "symbols_failed": symbols_failed,
        "run_id": SOURCE_RUN_ID,
        "updated_at": completed_at,
    }
    try:
        # $setOnInsert makes this safe to run repeatedly and preserves any
        # metadata written by a newer scheduled run.
        db.app_metadata.update_one(
            {"_id": METADATA_ID},
            {"$setOnInsert": metadata},
            upsert=True,
        )
    except DuplicateKeyError:
        # Another process may have inserted the same metadata concurrently.
        pass

    saved = db.app_metadata.find_one({"_id": METADATA_ID})
    if not saved:
        raise RuntimeError("Metadata backfill did not produce a readable document")
    return {
        "status": "created" if saved.get("run_id") == SOURCE_RUN_ID else "already_present",
        "metadata_id": METADATA_ID,
        "last_updated": saved.get("last_updated"),
        "symbols_total": saved.get("symbols_total", 0),
        "symbols_success": saved.get("symbols_success", 0),
        "symbols_failed": saved.get("symbols_failed", 0),
    }


def main() -> int:
    uri = os.getenv("MONGODB_URI", "").strip()
    if not uri:
        raise RuntimeError("Missing required environment variable: MONGODB_URI")
    database_name = os.getenv("MONGODB_DATABASE", "dautu").strip()
    if not database_name:
        raise RuntimeError("MONGODB_DATABASE must not be empty")

    client = MongoClient(uri, appname="DautuMetadataBackfill", serverSelectionTimeoutMS=10000)
    try:
        client.admin.command("ping")
        result = backfill(client[database_name])
        print(json.dumps(result, ensure_ascii=False, default=str))
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
