"""Read-only MongoDB Atlas diagnostics for the Dautu operational database."""
from __future__ import annotations

import json

from app.database.mongo import get_client, get_database

COLLECTIONS = (
    "stocks",
    "price_history",
    "financial_reports",
    "screener_results",
    "ai_analyses",
    "simulations",
    "pipeline_runs",
    "dataset_versions",
    "app_metadata",
)


def collect_status() -> dict:
    client = get_client()
    client.admin.command("ping")
    db = get_database()
    existing = set(db.list_collection_names())
    counts = {
        name: db[name].estimated_document_count() if name in existing else 0
        for name in COLLECTIONS
    }
    return {
        "status": "ok",
        "database": db.name,
        "collections": counts,
        "total_documents": sum(counts.values()),
    }


if __name__ == "__main__":
    print(json.dumps(collect_status(), ensure_ascii=False, indent=2))
