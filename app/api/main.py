"""Authenticated read API for the Dautu web client."""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import firebase_admin
from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
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


def _allowed_hosts() -> list[str]:
    configured = [
        host.strip()
        for host in os.getenv("API_ALLOWED_HOSTS", "").split(",")
        if host.strip()
    ]
    render_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
    if render_hostname:
        configured.append(render_hostname)
    # Local/test defaults only. Render supplies RENDER_EXTERNAL_HOSTNAME;
    # custom domains must be added explicitly through API_ALLOWED_HOSTS.
    return list(dict.fromkeys(configured or ["localhost", "127.0.0.1", "testserver"]))


RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_REQUESTS = 120
_rate_limit_state: dict[str, tuple[float, int]] = {}
_rate_limit_lock = threading.Lock()


def _enforce_user_rate_limit(user_id: str, now: float | None = None) -> None:
    """Apply a per-authenticated-user fixed-window limit in this API process.

    This intentionally does not trust client-supplied forwarding headers. If the
    service is later scaled to multiple instances, move the counter to shared
    storage (for example Render Key Value) before increasing instance count.
    """
    current = time.monotonic() if now is None else now
    with _rate_limit_lock:
        started, count = _rate_limit_state.get(user_id, (current, 0))
        if current - started >= RATE_LIMIT_WINDOW_SECONDS:
            started, count = current, 0
        if count >= RATE_LIMIT_MAX_REQUESTS:
            retry_after = max(1, int(RATE_LIMIT_WINDOW_SECONDS - (current - started)))
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please retry shortly.",
                headers={"Retry-After": str(retry_after)},
            )
        _rate_limit_state[user_id] = (started, count + 1)
        if len(_rate_limit_state) > 5000:
            cutoff = current - RATE_LIMIT_WINDOW_SECONDS
            for key, (window_start, _) in list(_rate_limit_state.items()):
                if window_start < cutoff:
                    _rate_limit_state.pop(key, None)


STOCK_RESPONSE_FIELDS = (
    "symbol", "company_name", "market_cap", "total_shares", "close", "volume",
    "pe", "pb", "eps", "roe", "roa", "dividend_yield", "cfo_latest", "cfo_ttm",
    "debt_to_equity", "liabilities_to_equity", "gross_margin", "net_profit_ttm",
    "recommendation", "price_zone", "updated_at", "outlook", "ai_recommendation",
    "ai_price_zone", "macro_view", "ai_updated_at", "bctc", "bctc_evaluation",
    "catalyst", "risks",
)
SCREENER_RESPONSE_FIELDS = (
    "symbol", "sector", "close_price", "pe", "pb", "roe", "roa",
    "dividend_yield", "profit_growth_yoy", "cfo_latest", "debt_to_equity",
    "gross_margin", "fundamental_score", "technical_score", "valuation_score",
    "total_score", "potential_zone", "technical_status", "technical_notes",
    "fundamental_notes",
)
AI_RESPONSE_FIELDS = (
    "symbol", "bctc", "catalyst", "risks", "outlook", "ai_recommendation",
    "ai_price_zone", "macro_view", "ai_updated_at",
)


def _safe_projection(fields: tuple[str, ...]) -> dict[str, int]:
    return {"_id": 0, **{field: 1 for field in fields}}


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Cache-Control", "no-store")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response


app.add_middleware(TrustedHostMiddleware, allowed_hosts=_allowed_hosts())

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

    # Apply the quota before the Firestore membership lookup so repeated calls
    # from one verified Firebase identity cannot hammer the authorization store.
    _enforce_user_rate_limit(str(claims.get("uid") or claims.get("sub") or email))

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
    """Public platform health probe; disclose no dependency or infrastructure details."""
    try:
        ping_database()
        return {"status": "ok"}
    except Exception:
        raise HTTPException(status_code=503, detail="Service unavailable")


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
    return list(db.stocks.find({}, _safe_projection(STOCK_RESPONSE_FIELDS)).sort("symbol", 1).limit(limit))


@app.get("/api/stocks/{symbol}")
def get_stock(
    symbol: str = Path(..., min_length=1, max_length=20, pattern=r"(?i)^[A-Z0-9][A-Z0-9._-]{0,19}$"),
    _: dict[str, Any] = Depends(require_user),
    db: Database = Depends(db_dependency),
) -> dict[str, Any]:
    doc = db.stocks.find_one({"_id": symbol.upper()}, _safe_projection(STOCK_RESPONSE_FIELDS))
    if not doc:
        raise HTTPException(status_code=404, detail="Stock not found")
    return doc


@app.get("/api/screener")
def get_screener(
    _: dict[str, Any] = Depends(require_user),
    db: Database = Depends(db_dependency),
    limit: int = Query(default=500, ge=1, le=1000),
) -> list[dict[str, Any]]:
    return list(db.screener_results.find({}, _safe_projection(SCREENER_RESPONSE_FIELDS)).sort("total_score", -1).limit(limit))


@app.get("/api/history/{symbol}")
def get_history(
    symbol: str = Path(..., min_length=1, max_length=20, pattern=r"(?i)^[A-Z0-9][A-Z0-9._-]{0,19}$"),
    _: dict[str, Any] = Depends(require_user),
    db: Database = Depends(db_dependency),
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for interval in ("D1", "W1", "MN"):
        result[f"history_{interval.lower()}"] = list(
            db.price_history.find(
                {"symbol": symbol.upper(), "interval": interval},
                {"_id": 0, "symbol": 0, "interval": 0, "updated_at": 0},
            ).sort("time", 1).limit(5000)
        )
    if not any(result.values()):
        raise HTTPException(status_code=404, detail="History not found")
    return result


@app.get("/api/financials/{symbol}")
def get_financials(
    symbol: str = Path(..., min_length=1, max_length=20, pattern=r"(?i)^[A-Z0-9][A-Z0-9._-]{0,19}$"),
    _: dict[str, Any] = Depends(require_user),
    db: Database = Depends(db_dependency),
) -> dict[str, Any]:
    docs = list(
        db.financial_reports.find(
            {"symbol": symbol.upper()},
            {"_id": 0, "symbol": 0, "updated_at": 0},
        ).limit(20)
    )
    if not docs:
        raise HTTPException(status_code=404, detail="Financial reports not found")
    return {doc["report_type"]: doc["data"] for doc in docs}


@app.get("/api/analysis/{symbol}")
def get_analysis(
    symbol: str = Path(..., min_length=1, max_length=20, pattern=r"(?i)^[A-Z0-9][A-Z0-9._-]{0,19}$"),
    _: dict[str, Any] = Depends(require_user),
    db: Database = Depends(db_dependency),
) -> dict[str, Any]:
    doc = db.ai_analyses.find_one({"_id": symbol.upper()}, _safe_projection(AI_RESPONSE_FIELDS))
    if not doc:
        raise HTTPException(status_code=404, detail="AI analysis not found")
    return doc
