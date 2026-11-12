"""Authenticated read API for the Dautu web client."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import firebase_admin
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from firebase_admin import auth as firebase_auth, credentials, firestore
from pymongo.database import Database

from app.database.mongo import ensure_indexes, get_database, ping_database
from app.database.repositories import get_metadata

app = FastAPI(
    title="Dautu API",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


def _allowed_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOWED_ORIGINS", "")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


origins = _allowed_origins()
if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )


@lru_cache(maxsize=1)
def _firebase_app():
    raw = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON is not configured")
    try:
        service_account = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON must be valid JSON") from exc
    try:
        return firebase_admin.get_app()
    except ValueError:
        return firebase_admin.initialize_app(credentials.Certificate(service_account))


ADMIN_EMAIL = "nguyenanhtuan081196@gmail.com"


def require_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Authenticate a Firebase user and enforce the server-side membership record.

    Firestore rules protect browser access, but the Admin SDK bypasses those rules;
    therefore every API request must independently enforce verification, role and
    subscription expiry here.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Firebase bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing Firebase bearer token")

    try:
        claims = firebase_auth.verify_id_token(
            token, app=_firebase_app(), check_revoked=True
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Authentication service unavailable") from exc
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired Firebase token") from exc

    email = claims.get("email")
    if not isinstance(email, str) or not email.strip():
        raise HTTPException(status_code=403, detail="A verified email address is required")
    email = email.strip().lower()
    if claims.get("email_verified") is not True:
        raise HTTPException(status_code=403, detail="Email verification is required")

    try:
        account = (
            firestore.client(app=_firebase_app())
            .collection("allowed_users")
            .document(email)
            .get()
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Account authorization service unavailable") from exc

    if not account.exists:
        raise HTTPException(status_code=403, detail="Account is not authorized")
    account_data = account.to_dict() or {}
    role = account_data.get("role")

    if role == "admin":
        if email != ADMIN_EMAIL:
            raise HTTPException(status_code=403, detail="Admin role is not authorized for this account")
        claims["app_role"] = "admin"
        return claims

    if role != "user":
        raise HTTPException(status_code=403, detail="Account role is not authorized")

    expires_at = account_data.get("expiresAt")
    if not isinstance(expires_at, datetime):
        raise HTTPException(status_code=403, detail="Account subscription expiry is invalid")
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=403, detail="Account subscription has expired")

    claims["app_role"] = "user"
    return claims


def db_dependency() -> Database:
    try:
        return get_database()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.on_event("startup")
def startup() -> None:
    ensure_indexes()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    try:
        ping_database()
        return {"status": "ok", "database": "connected"}
    except Exception:
        raise HTTPException(status_code=503, detail="Database unavailable")


@app.get("/api/status")
def status(
    _: dict[str, Any] = Depends(require_user),
    db: Database = Depends(db_dependency),
) -> dict[str, Any]:
    return {
        "active_dataset_version": get_metadata(db, "active_dataset_version"),
        "last_update": get_metadata(db, "last_update"),
    }


@app.get("/api/stocks")
def list_stocks(
    _: dict[str, Any] = Depends(require_user),
    db: Database = Depends(db_dependency),
    limit: int = Query(default=200, ge=1, le=500),
) -> list[dict[str, Any]]:
    return list(db.stocks.find({}, {"_id": 0}).sort("symbol", 1).limit(limit))


@app.get("/api/stocks/{symbol}")
def get_stock(
    symbol: str,
    _: dict[str, Any] = Depends(require_user),
    db: Database = Depends(db_dependency),
) -> dict[str, Any]:
    doc = db.stocks.find_one({"_id": symbol.upper()}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Stock not found")
    return doc


@app.get("/api/screener")
def get_screener(
    _: dict[str, Any] = Depends(require_user),
    db: Database = Depends(db_dependency),
    limit: int = Query(default=500, ge=1, le=1000),
) -> list[dict[str, Any]]:
    return list(db.screener_results.find({}, {"_id": 0}).sort("total_score", -1).limit(limit))


@app.get("/api/history/{symbol}")
def get_history(
    symbol: str,
    _: dict[str, Any] = Depends(require_user),
    db: Database = Depends(db_dependency),
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for interval in ("D1", "W1", "MN"):
        result[f"history_{interval.lower()}"] = list(
            db.price_history.find(
                {"symbol": symbol.upper(), "interval": interval},
                {"_id": 0, "symbol": 0, "interval": 0, "updated_at": 0},
            ).sort("time", 1)
        )
    if not any(result.values()):
        raise HTTPException(status_code=404, detail="History not found")
    return result


@app.get("/api/financials/{symbol}")
def get_financials(
    symbol: str,
    _: dict[str, Any] = Depends(require_user),
    db: Database = Depends(db_dependency),
) -> dict[str, Any]:
    docs = list(
        db.financial_reports.find(
            {"symbol": symbol.upper()},
            {"_id": 0, "symbol": 0, "updated_at": 0},
        )
    )
    if not docs:
        raise HTTPException(status_code=404, detail="Financial reports not found")
    return {doc["report_type"]: doc["data"] for doc in docs}


@app.get("/api/analysis/{symbol}")
def get_analysis(
    symbol: str,
    _: dict[str, Any] = Depends(require_user),
    db: Database = Depends(db_dependency),
) -> dict[str, Any]:
    doc = db.ai_analyses.find_one({"_id": symbol.upper()}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="AI analysis not found")
    return doc
