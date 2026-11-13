"""Authenticated read API for the Dautu web client."""
from __future__ import annotations

import asyncio
import json
import os
import smtplib
import threading
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from functools import lru_cache
from typing import Any

import firebase_admin
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query
from firebase_admin import auth as firebase_auth, credentials, firestore
from pymongo.database import Database

from app.core.application import create_app
from app.core.config import get_allowed_hosts, get_allowed_origins
from app.database.mongo import ensure_indexes, get_database, ping_database
from app.database.repositories import get_metadata

router = APIRouter()


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

    # Apply the quota before the Firestore membership lookup so repeated calls
    # from one Firebase identity cannot hammer the authorization store.
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
        # Bypass verification only for the designated Admin email and an existing
        # Firestore profile explicitly carrying role=admin.
        if email != ADMIN_EMAIL:
            raise HTTPException(status_code=403, detail="Admin role is not authorized for this account")
        claims["app_role"] = "admin"
        return claims

    # Every ordinary User must verify their email before API access.
    if claims.get("email_verified") is not True:
        raise HTTPException(status_code=403, detail="Email verification is required")

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


async def startup() -> None:
    """Initialize Atlas and launch the price scheduler without blocking API requests."""
    global _price_scheduler_task
    ensure_indexes()
    if os.getenv("PRICE_SCHEDULER_ENABLED", "true").strip().lower() in {"1", "true", "yes"}:
        from app.pipeline.scheduler import price_scheduler_loop
        _price_scheduler_task = asyncio.create_task(
            price_scheduler_loop(), name="dautu-price-scheduler"
        )


_price_scheduler_task: asyncio.Task | None = None


async def shutdown() -> None:
    """Stop the scheduler cleanly before closing the shared Atlas client."""
    global _price_scheduler_task
    task = _price_scheduler_task
    _price_scheduler_task = None
    if task is not None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@router.api_route("/healthz", methods=["GET", "HEAD"])
def healthz() -> dict[str, str]:
    """Public platform health probe; disclose no dependency or infrastructure details."""
    try:
        ping_database()
        return {"status": "ok"}
    except Exception:
        raise HTTPException(status_code=503, detail="Service unavailable")


@router.get("/api/status")
def status(
    _: dict[str, Any] = Depends(require_user),
    db: Database = Depends(db_dependency),
) -> dict[str, Any]:
    return {
        "active_dataset_version": get_metadata(db, "active_dataset_version"),
        "last_update": get_metadata(db, "last_update"),
    }


@router.get("/api/stocks")
def list_stocks(
    _: dict[str, Any] = Depends(require_user),
    db: Database = Depends(db_dependency),
    limit: int = Query(default=200, ge=1, le=500),
) -> list[dict[str, Any]]:
    return list(db.stocks.find({}, _safe_projection(STOCK_RESPONSE_FIELDS)).sort("symbol", 1).limit(limit))


@router.get("/api/stocks/{symbol}")
def get_stock(
    symbol: str = Path(..., min_length=1, max_length=20, pattern=r"(?i)^[A-Z0-9][A-Z0-9._-]{0,19}$"),
    _: dict[str, Any] = Depends(require_user),
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
