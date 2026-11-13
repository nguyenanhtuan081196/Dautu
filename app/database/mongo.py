"""MongoDB Atlas connection and index management for Dautu."""
from __future__ import annotations

import os
from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pymongo import ASCENDING, MongoClient
from pymongo.database import Database


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def normalize_mongodb_uri(uri: str) -> str:
    """Validate and normalize a MongoDB URI without overriding explicit options.

    Empty query parameters are removed because copied Atlas connection strings
    can contain trailing ampersands. retryWrites defaults to true only when the
    option is absent or explicitly blank; an explicit false is preserved.
    """
    parts = urlsplit(uri.strip())
    if parts.scheme not in {"mongodb", "mongodb+srv"}:
        raise ValueError("MONGODB_URI must start with mongodb:// or mongodb+srv://")
    if not parts.netloc:
        raise ValueError("MONGODB_URI must include a MongoDB host")

    pairs = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.strip()
    ]
    options = {key.lower(): index for index, (key, _) in enumerate(pairs)}
    retry_index = options.get("retrywrites")
    if retry_index is None:
        pairs.append(("retryWrites", "true"))
    else:
        key, value = pairs[retry_index]
        if not value.strip():
            pairs[retry_index] = (key, "true")

    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(pairs), parts.fragment)
    )


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
