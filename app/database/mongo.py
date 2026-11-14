"""MongoDB Atlas connection and index management for Dautu."""
from __future__ import annotations

import os
from functools import lru_cache

from pymongo import ASCENDING, MongoClient
from pymongo.database import Database
from server_platform.database.mongo import (
    normalize_mongodb_uri as _platform_normalize_mongodb_uri,
)


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def normalize_mongodb_uri(uri: str) -> str:
    """Use the shared platform URI validator while preserving Dautu's API."""
    return _platform_normalize_mongodb_uri(uri)


# Backward-compatible private name used by existing migration tooling/tests.
_normalize_mongodb_uri = normalize_mongodb_uri


@lru_cache(maxsize=1)
def get_client() -> MongoClient:
    uri = normalize_mongodb_uri(_required_env("MONGODB_URI"))
    return MongoClient(
        uri,
        appname="Dautu",
        serverSelectionTimeoutMS=int(
            os.getenv("MONGODB_SERVER_SELECTION_TIMEOUT_MS", "10000")
        ),
        connectTimeoutMS=int(os.getenv("MONGODB_CONNECT_TIMEOUT_MS", "10000")),
    )


def close_client() -> None:
    """Close the cached MongoDB client without creating a new connection."""
    if not get_client.cache_info().currsize:
        return
    client = get_client()
    try:
        client.close()
    finally:
        # Always discard a potentially closed/broken client from the cache.
        get_client.cache_clear()


def get_database() -> Database:
    database_name = os.getenv("MONGODB_DATABASE", "dautu").strip()
    if not database_name:
        raise RuntimeError("MONGODB_DATABASE must not be empty")
    return get_client()[database_name]


def ping_database() -> bool:
    get_client().admin.command("ping")
    return True


def ensure_indexes(db: Database | None = None) -> None:
    """Create idempotent Dautu-specific indexes."""
    if db is None:
        db = get_database()
    db.stocks.create_index([("symbol", ASCENDING)], unique=True)
    db.price_history.create_index(
        [("symbol", ASCENDING), ("interval", ASCENDING), ("time", ASCENDING)],
        unique=True,
    )
    db.price_history.create_index([("symbol", ASCENDING), ("interval", ASCENDING)])
    db.financial_reports.create_index(
        [("symbol", ASCENDING), ("report_type", ASCENDING)], unique=True
    )
    db.screener_results.create_index([("symbol", ASCENDING)], unique=True)
    db.ai_analyses.create_index([("symbol", ASCENDING)], unique=True)
    db.simulations.create_index([("symbol", ASCENDING)], unique=True)
    db.pipeline_runs.create_index([("run_id", ASCENDING)], unique=True)
    db.dataset_versions.create_index([("version_id", ASCENDING)], unique=True)
    db.app_metadata.create_index([("key", ASCENDING)], unique=True)
    db.realtime_prices.create_index([("symbol", ASCENDING)], unique=True)
    db.realtime_prices.create_index([("updated_at", ASCENDING)])
    db.users.create_index([("email", ASCENDING)], unique=True)
    db.users.create_index([("role", ASCENDING), ("status", ASCENDING)])
