"""Idempotent publication of the latest successful scheduled price run."""
from __future__ import annotations

from datetime import datetime
from typing import Any

METADATA_ID = "price_sync"


def ensure_price_metadata(db: Any, scheduled_for: str) -> dict[str, Any]:
    """Create/update the latest metadata only from a complete successful run.

    A same-run document is never rewritten. A newer metadata timestamp wins,
    protecting a concurrently completed newer run from a delayed recovery task.
    """
    run_id = f"price_sync:{scheduled_for}"
    run = db.pipeline_runs.find_one({"_id": run_id, "status": "succeeded"})
    if not run:
        raise RuntimeError(f"Successful price pipeline run not found: {run_id}")

    if run.get("scheduled_for") not in (None, scheduled_for):
        raise RuntimeError("Pipeline run scheduled_for does not match requested date")

    completed_at = run.get("completed_at")
    if not isinstance(completed_at, datetime):
        raise RuntimeError("Successful pipeline run has no valid completed_at timestamp")

    total = int(run.get("symbols_total", 0))
    succeeded = int(run.get("symbols_success", 0))
    failed = int(run.get("symbols_failed", 0))
    if total <= 0 or succeeded != total or failed != 0:
        raise RuntimeError("Pipeline run is not complete; refusing metadata publication")

    metadata = {
        "_id": METADATA_ID,
        "key": METADATA_ID,
        "scheduled_for": scheduled_for,
        "last_updated": completed_at,
        "status": "succeeded",
        "symbols_total": total,
        "symbols_success": succeeded,
        "symbols_failed": failed,
        "run_id": run_id,
        "updated_at": completed_at,
    }

    existing = db.app_metadata.find_one({"_id": METADATA_ID})
    if existing:
        if existing.get("run_id") == run_id:
            return {
                "status": "already_present",
                "metadata_id": METADATA_ID,
                "last_updated": existing.get("last_updated"),
            }

        existing_timestamp = existing.get("last_updated")
        # Unknown legacy timestamp formats are preserved conservatively.
        if not isinstance(existing_timestamp, datetime) or existing_timestamp >= completed_at:
            return {
                "status": "preserved_existing",
                "metadata_id": METADATA_ID,
                "last_updated": existing_timestamp,
            }

        # Compare-and-set: if another process changed the document after our
        # read, this update cannot overwrite that newer write.
        db.app_metadata.update_one(
            {"_id": METADATA_ID, "last_updated": existing_timestamp},
            {"$set": {key: value for key, value in metadata.items() if key != "_id"}},
        )
        saved = db.app_metadata.find_one({"_id": METADATA_ID}) or {}
        if saved.get("run_id") == run_id:
            return {
                "status": "updated",
                "metadata_id": METADATA_ID,
                "last_updated": saved.get("last_updated"),
            }
        return {
            "status": "preserved_existing",
            "metadata_id": METADATA_ID,
            "last_updated": saved.get("last_updated"),
        }

    # $setOnInsert is atomic and never replaces a document inserted concurrently.
    db.app_metadata.update_one(
        {"_id": METADATA_ID},
        {"$setOnInsert": metadata},
        upsert=True,
    )
    saved = db.app_metadata.find_one({"_id": METADATA_ID}) or {}
    if not saved:
        raise RuntimeError("Price metadata write did not produce a readable document")
    return {
        "status": "created" if saved.get("run_id") == run_id else "preserved_existing",
        "metadata_id": METADATA_ID,
        "last_updated": saved.get("last_updated"),
    }
