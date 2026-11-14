"""Authenticated read API for the Dautu web client."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import smtplib
import threading
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from functools import lru_cache
from typing import Any

import firebase_admin
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Response
from firebase_admin import auth as firebase_auth, credentials, firestore
from pymongo.database import Database

from app.core.application import create_app
from app.core.config import get_allowed_hosts, get_allowed_origins
from app.database.mongo import ensure_indexes, get_database, ping_database
from app.database.repositories import get_metadata

router = APIRouter()
logger = logging.getLogger(__name__)


def _allowed_origins() -> list[str]:
    """Backward-compatible accessor used by the API compatibility tests."""
    return get_allowed_origins()


def _allowed_hosts() -> list[str]:
    """Backward-compatible accessor for the configured host allow-list."""
    return get_allowed_hosts()


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


_verification_send_state: dict[str, list[float]] = {}
_verification_send_lock = threading.Lock()
VERIFICATION_SEND_LIMIT = 3
VERIFICATION_SEND_WINDOW_SECONDS = 3600


def _check_verification_send_limit(email: str) -> None:
    now = time.monotonic()
    with _verification_send_lock:
        recent = [
            stamp for stamp in _verification_send_state.get(email, [])
            if now - stamp < VERIFICATION_SEND_WINDOW_SECONDS
        ]
        if len(recent) >= VERIFICATION_SEND_LIMIT:
            raise HTTPException(
                status_code=429,
                detail="Anh đã yêu cầu gửi email quá nhiều lần. Vui lòng thử lại sau một giờ.",
                headers={"Retry-After": "3600"},
            )
        recent.append(now)
        _verification_send_state[email] = recent


def _send_gmail_verification(recipient: str, verification_url: str) -> None:
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_password = os.getenv("SMTP_APP_PASSWORD", "").replace(" ", "").strip()
    sender = os.getenv("SMTP_FROM_EMAIL", smtp_user).strip()
    if not smtp_user or not smtp_password or not sender:
        raise RuntimeError("Email sender is not configured on the server")

    message = EmailMessage()
    message["Subject"] = "Xác minh email tài khoản Dautu"
    message["From"] = f"Dautu <{sender}>"
    message["To"] = recipient
    message.set_content(
        "Xin chào,\n\n"
        "Anh/chị vừa yêu cầu xác minh email cho tài khoản Dautu. "
        "Vui lòng mở liên kết dưới đây để xác minh:\n\n"
        f"{verification_url}\n\n"
        "Nếu anh/chị không thực hiện yêu cầu này, hãy bỏ qua email.\n"
    )
    message.add_alternative(
        "<p>Xin chào,</p><p>Anh/chị vừa yêu cầu xác minh email cho tài khoản Dautu.</p>"
        f'<p><a href="{verification_url}">Xác minh email Dautu</a></p>'
        "<p>Nếu anh/chị không thực hiện yêu cầu này, hãy bỏ qua email.</p>",
        subtype="html",
    )
    with smtplib.SMTP(os.getenv("SMTP_HOST", "smtp.gmail.com"), int(os.getenv("SMTP_PORT", "587")), timeout=20) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(smtp_user, smtp_password)
        server.send_message(message)


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


@router.post("/api/auth/send-verification")
def send_verification_email(authorization: str | None = Header(default=None)) -> dict[str, str]:
    """Generate a Firebase verification link and deliver it through Gmail SMTP.

    The caller must already be signed in to Firebase, but the email does not need
    to be verified yet. The server never accepts a recipient address from the
    browser: it uses the email claim from the verified Firebase ID token.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Firebase bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        claims = firebase_auth.verify_id_token(token, app=_firebase_app(), check_revoked=True)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Authentication service unavailable") from exc
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired Firebase token") from exc

    email = claims.get("email")
    if not isinstance(email, str) or not email.strip():
        raise HTTPException(status_code=403, detail="A valid account email is required")
    email = email.strip().lower()
    if claims.get("email_verified") is True:
        raise HTTPException(status_code=409, detail="Email này đã được xác minh.")

    _check_verification_send_limit(email)
    frontend_url = os.getenv("FRONTEND_URL", "https://mimohouse.ddns.net").strip()
    try:
        action_settings = firebase_auth.ActionCodeSettings(
            url=frontend_url,
            handle_code_in_app=False,
        )
        verification_url = firebase_auth.generate_email_verification_link(
            email, action_code_settings=action_settings, app=_firebase_app()
        )
        _send_gmail_verification(email, verification_url)
    except HTTPException:
        raise
    except Exception as exc:
        # Keep SMTP credentials and provider internals out of public responses.
        raise HTTPException(
            status_code=503,
            detail="Máy chủ chưa gửi được email. Vui lòng kiểm tra cấu hình SMTP trên Render.",
        ) from exc
    return {"status": "sent", "message": "Verification email sent"}


ADMIN_EMAIL = "nguyenanhtuan081196@gmail.com"


def _verify_firebase_token(authorization: str | None) -> dict[str, Any]:
    """Verify Firebase identity; account authorization is handled separately."""
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
        raise HTTPException(status_code=403, detail="A valid account email is required")
    claims["email"] = email.strip().lower()
    return claims


def _legacy_membership(email: str) -> tuple[dict[str, Any] | None, datetime]:
    """Read the legacy Firestore allow-list only when an account is first provisioned."""
    try:
        snapshot = (
            firestore.client(app=_firebase_app())
            .collection("allowed_users")
            .document(email)
            .get()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="Account authorization service unavailable"
        ) from exc
    if not snapshot.exists:
        return None, datetime.now(timezone.utc)
    data = snapshot.to_dict() or {}
    created_at = getattr(snapshot, "create_time", None) or datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return data, created_at


def _get_or_create_account(claims: dict[str, Any]) -> dict[str, Any]:
    """Use MongoDB as the live account registry; migrate legacy Firestore users once."""
    email = claims["email"]
    uid = str(claims.get("uid") or claims.get("sub") or "")
    try:
        db = get_database()
        account = db.users.find_one({"email": email})
        if account is not None:
            return account

        legacy, created_at = _legacy_membership(email)
        if legacy is None:
            role, expired_at = "guest", None
        else:
            legacy_role = legacy.get("role", "user")
            if legacy_role == "admin":
                if email != ADMIN_EMAIL:
                    raise HTTPException(
                        status_code=403, detail="Admin role is not authorized for this account"
                    )
                role = "admin"
            elif legacy_role == "user":
                role = "user"
            else:
                raise HTTPException(status_code=403, detail="Account role is not authorized")
            expired_at = legacy.get("expiresAt")
            if isinstance(expired_at, datetime) and expired_at.tzinfo is None:
                expired_at = expired_at.replace(tzinfo=timezone.utc)

        document = {
            "email": email,
            "firebase_uid": uid,
            "created_at": created_at,
            "expired_at": expired_at,
            "role": role,
            "status": "active",
            "created_source": "firestore_migration" if legacy is not None else "firebase_guest",
            "updated_at": datetime.now(timezone.utc),
        }
        try:
            db.users.update_one(
                {"email": email}, {"$setOnInsert": document}, upsert=True
            )
        except Exception:
            # Concurrent first requests can race on the unique email index.
            pass
        account = db.users.find_one({"email": email})
        if account is None:
            raise RuntimeError("Account provisioning did not create a MongoDB record")
        return account
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="Account authorization service unavailable"
        ) from exc


def require_guest(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Base access: valid Firebase identity, active account and non-expired access."""
    claims = _verify_firebase_token(authorization)
    _enforce_user_rate_limit(
        str(claims.get("uid") or claims.get("sub") or claims["email"])
    )
    account = _get_or_create_account(claims)

    status = account.get("status", "active")
    if status != "active":
        raise HTTPException(status_code=403, detail="Account is locked")
    role = account.get("role")
    if role not in {"guest", "user", "admin"}:
        raise HTTPException(status_code=403, detail="Account role is not authorized")

    expired_at = account.get("expired_at")
    if expired_at is not None:
        if not isinstance(expired_at, datetime):
            raise HTTPException(status_code=403, detail="Account expiry is invalid")
        if expired_at.tzinfo is None:
            expired_at = expired_at.replace(tzinfo=timezone.utc)
        if expired_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Account subscription has expired")

    if claims.get("email_verified") is not True and not (
        role == "admin" and claims["email"] == ADMIN_EMAIL
    ):
        raise HTTPException(status_code=403, detail="Email verification is required")

    claims["app_role"] = role
    claims["account_status"] = status
    claims["account_created_at"] = account.get("created_at")
    claims["account_expired_at"] = expired_at
    return claims


def require_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Paid data access: User or Admin; guests are restricted to basic endpoints."""
    user = require_guest(authorization)
    if user.get("app_role") not in {"user", "admin"}:
        raise HTTPException(status_code=403, detail="A User subscription is required")
    if user.get("app_role") == "user" and user.get("account_expired_at") is None:
        raise HTTPException(status_code=403, detail="Account subscription expiry is invalid")
    return user


def require_admin(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Administrative access is reserved for explicit Admin accounts."""
    user = require_guest(authorization)
    if user.get("app_role") != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges are required")
    return user


def db_dependency() -> Database:
    try:
        return get_database()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def metadata_db_dependency() -> Database | None:
    """Metadata is non-critical UI data; DB connection failures use safe defaults."""
    try:
        return get_database()
    except Exception:
        logger.exception("Unable to obtain MongoDB connection for price metadata")
        return None


async def startup() -> None:
    """Initialize Atlas and launch the price scheduler without blocking API requests."""
    global _price_scheduler_task, _realtime_collector_task
    ensure_indexes()
    if os.getenv("PRICE_SCHEDULER_ENABLED", "true").strip().lower() in {"1", "true", "yes"}:
        from app.pipeline.scheduler import price_scheduler_loop
        _price_scheduler_task = asyncio.create_task(
            price_scheduler_loop(), name="dautu-price-scheduler"
        )
    if os.getenv("ENABLE_REALTIME_CRAWLER", "false").strip().lower() in {"1", "true", "yes", "on"}:
        from app.pipeline.realtime_collector import realtime_collector_loop
        _realtime_collector_task = asyncio.create_task(
            realtime_collector_loop(), name="dautu-ssi-realtime-collector"
        )


_price_scheduler_task: asyncio.Task | None = None
_realtime_collector_task: asyncio.Task | None = None


async def shutdown() -> None:
    """Stop the scheduler cleanly before closing the shared Atlas client."""
    global _price_scheduler_task, _realtime_collector_task
    tasks = [task for task in (_price_scheduler_task, _realtime_collector_task) if task is not None]
    _price_scheduler_task = None
    _realtime_collector_task = None
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


@router.api_route("/healthz", methods=["GET", "HEAD"])
def healthz() -> dict[str, str]:
    """Public platform health probe; disclose no dependency or infrastructure details."""
    try:
        ping_database()
        return {"status": "ok"}
    except Exception:
        raise HTTPException(status_code=503, detail="Service unavailable")


@router.get("/api/metadata")
def price_metadata(
    response: Response,
    _: dict[str, Any] = Depends(require_user),
    db: Database | None = Depends(metadata_db_dependency),
) -> dict[str, Any]:
    """Return the latest Atlas price-sync timestamp and outcome without caching."""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    fallback = {
        "last_updated": None,
        "status": "unknown",
        "symbols_total": 0,
        "symbols_success": 0,
        "symbols_failed": 0,
    }
    if db is None:
        return fallback
    try:
        document = db.app_metadata.find_one(
            {"_id": "price_sync"},
            {"_id": 0, "key": 0, "updated_at": 0},
        ) or {}
    except Exception:
        # Metadata is supplementary UI information: Atlas read failures must
        # not break the main frontend or expose database details to clients.
        logger.exception("Unable to read price-sync metadata from MongoDB")
        return fallback

    return {
        "last_updated": document.get("last_updated"),
        "status": document.get("status", "unknown"),
        "symbols_total": document.get("symbols_total", 0),
        "symbols_success": document.get("symbols_success", 0),
        "symbols_failed": document.get("symbols_failed", 0),
    }


@router.get("/api/realtime")
def list_realtime_prices(
    _: dict[str, Any] = Depends(require_user),
    db: Database = Depends(db_dependency),
    limit: int = Query(default=200, ge=1, le=500),
) -> list[dict[str, Any]]:
    """Read the latest SSI ticks from Atlas; this route never calls SSI."""
    return list(
        db.realtime_prices.find({}, {"_id": 0})
        .sort("symbol", 1)
        .limit(limit)
    )


@router.get("/api/realtime/{symbol}")
def get_realtime_price(
    symbol: str = Path(..., min_length=1, max_length=20, pattern=r"(?i)^[A-Z0-9][A-Z0-9._-]{0,19}$"),
    _: dict[str, Any] = Depends(require_user),
    db: Database = Depends(db_dependency),
) -> dict[str, Any]:
    """Read one latest SSI tick from Atlas; never make an upstream request."""
    document = db.realtime_prices.find_one(
        {"_id": symbol.upper()}, {"_id": 0}
    )
    if not document:
        raise HTTPException(status_code=404, detail="Realtime price not found")
    return document


@router.get("/api/status")
def status(
    _: dict[str, Any] = Depends(require_guest),
    db: Database = Depends(db_dependency),
) -> dict[str, Any]:
    return {
        "active_dataset_version": get_metadata(db, "active_dataset_version"),
        "last_update": get_metadata(db, "last_update"),
    }


@router.get("/api/stocks")
def list_stocks(
    _: dict[str, Any] = Depends(require_guest),
    db: Database = Depends(db_dependency),
    limit: int = Query(default=200, ge=1, le=500),
) -> list[dict[str, Any]]:
    return list(db.stocks.find({}, _safe_projection(STOCK_RESPONSE_FIELDS)).sort("symbol", 1).limit(limit))


@router.get("/api/stocks/{symbol}")
def get_stock(
    symbol: str = Path(..., min_length=1, max_length=20, pattern=r"(?i)^[A-Z0-9][A-Z0-9._-]{0,19}$"),
    _: dict[str, Any] = Depends(require_guest),
    db: Database = Depends(db_dependency),
) -> dict[str, Any]:
    doc = db.stocks.find_one({"_id": symbol.upper()}, _safe_projection(STOCK_RESPONSE_FIELDS))
    if not doc:
        raise HTTPException(status_code=404, detail="Stock not found")
    return doc


@router.get("/api/screener")
def get_screener(
    _: dict[str, Any] = Depends(require_user),
    db: Database = Depends(db_dependency),
    limit: int = Query(default=500, ge=1, le=1000),
) -> list[dict[str, Any]]:
    return list(db.screener_results.find({}, _safe_projection(SCREENER_RESPONSE_FIELDS)).sort("total_score", -1).limit(limit))


SIMULATION_RESPONSE_FIELDS = (
    "symbol", "annual_rate_percent", "start_quarter",
    "start_price_mean", "end_quarter", "end_price_mean",
)


@router.get("/api/simulations")
def list_simulations(
    _: dict[str, Any] = Depends(require_user),
    db: Database = Depends(db_dependency),
    limit: int = Query(default=500, ge=1, le=1000),
) -> list[dict[str, Any]]:
    """Return the reviewed historical-return fields used by the investment simulator."""
    return list(
        db.simulations.find({}, _safe_projection(SIMULATION_RESPONSE_FIELDS))
        .sort("symbol", 1)
        .limit(limit)
    )


@router.get("/api/simulations/{symbol}")
def get_simulation(
    symbol: str = Path(..., min_length=1, max_length=20, pattern=r"(?i)^[A-Z0-9][A-Z0-9._-]{0,19}$"),
    _: dict[str, Any] = Depends(require_user),
    db: Database = Depends(db_dependency),
) -> dict[str, Any]:
    doc = db.simulations.find_one(
        {"_id": symbol.upper()}, _safe_projection(SIMULATION_RESPONSE_FIELDS)
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Simulation not found")
    return doc


@router.get("/api/history/{symbol}")
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


@router.get("/api/financials/{symbol}")
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


@router.get("/api/analysis/{symbol}")
def get_analysis(
    symbol: str = Path(..., min_length=1, max_length=20, pattern=r"(?i)^[A-Z0-9][A-Z0-9._-]{0,19}$"),
    _: dict[str, Any] = Depends(require_user),
    db: Database = Depends(db_dependency),
) -> dict[str, Any]:
    doc = db.ai_analyses.find_one({"_id": symbol.upper()}, _safe_projection(AI_RESPONSE_FIELDS))
    if not doc:
        raise HTTPException(status_code=404, detail="AI analysis not found")
    return doc


# Keep the public ASGI import path stable: app.api.main:app
app = create_app(
    router=router,
    startup_handler=startup,
    shutdown_handler=shutdown,
)
