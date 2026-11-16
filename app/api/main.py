"""Authenticated read API for the Dautu web client."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import requests
import threading
import time
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Literal

import firebase_admin
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request, Response
from pydantic import BaseModel, Field
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
    """Read the legacy Firestore record; its contents are untrusted until provenance is checked."""
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


def _legacy_membership_is_admin_created(email: str, legacy: dict[str, Any] | None) -> bool:
    """Trust only explicit Admin provenance; old unmarked self-created docs fail closed.

    The fixed bootstrap Admin is the sole compatibility exception because its
    identity is independently pinned in server configuration.
    """
    if not legacy:
        return False
    if email == ADMIN_EMAIL and legacy.get("role") == "admin":
        return True
    return (
        str(legacy.get("createdBy", "")).strip().lower() == ADMIN_EMAIL
        and legacy.get("createdSource") == "admin_console"
    )


def _legacy_role_and_expiry(email: str, legacy: dict[str, Any] | None) -> tuple[str, datetime | None]:
    """Translate a trusted legacy record into a safe MongoDB role and expiry."""
    if not _legacy_membership_is_admin_created(email, legacy):
        return "guest", None
    legacy_role = legacy.get("role")
    if legacy_role == "admin" and email == ADMIN_EMAIL:
        return "admin", None
    if legacy_role != "user":
        return "guest", None
    expired_at = legacy.get("expiresAt")
    if not isinstance(expired_at, datetime):
        return "guest", None
    if expired_at.tzinfo is None:
        expired_at = expired_at.replace(tzinfo=timezone.utc)
    return "user", expired_at


def _get_or_create_account(claims: dict[str, Any]) -> dict[str, Any]:
    """Use MongoDB as the registry and re-check old Firestore migrations once.

    Legacy Firestore documents without explicit Admin provenance are never
    allowed to confer paid access. Existing PR-46 migrated records are checked
    too, so previously imported self-created records are downgraded immediately.
    """
    email = claims["email"]
    uid = str(claims.get("uid") or claims.get("sub") or "")
    try:
        db = get_database()
        account = db.users.find_one({"email": email})

        if account is not None:
            existing_uid = account.get("firebase_uid")
            if existing_uid and uid and existing_uid != uid:
                raise HTTPException(status_code=403, detail="Firebase identity does not match this account")
            if not existing_uid and uid:
                db.users.update_one(
                    {"email": email},
                    {"$set": {"firebase_uid": uid, "updated_at": datetime.now(timezone.utc)}},
                )
                account["firebase_uid"] = uid

            if (
                account.get("created_source") == "firestore_migration"
                and account.get("legacy_provenance_checked") is not True
            ):
                legacy, _ = _legacy_membership(email)
                trusted = _legacy_membership_is_admin_created(email, legacy)
                role, expired_at = _legacy_role_and_expiry(email, legacy)
                provenance = "admin_created" if trusted else "untrusted_or_unmarked"
                db.users.update_one(
                    {"email": email},
                    {"$set": {
                        "role": role,
                        "expired_at": expired_at,
                        "legacy_provenance_checked": True,
                        "legacy_provenance": provenance,
                        "updated_at": datetime.now(timezone.utc),
                        "created_source": "firestore_migration_verified" if trusted else "firestore_untrusted_legacy",
                    }},
                )
                account = db.users.find_one({"email": email})
                if account is None:
                    raise RuntimeError("Account disappeared during legacy provenance verification")
            return account

        legacy, created_at = _legacy_membership(email)
        role, expired_at = _legacy_role_and_expiry(email, legacy)
        trusted = _legacy_membership_is_admin_created(email, legacy)
        document = {
            "email": email,
            "firebase_uid": uid,
            "created_at": created_at,
            "expired_at": expired_at,
            "role": role,
            "status": "active",
            "created_source": (
                "firestore_migration_verified" if trusted
                else "firestore_untrusted_legacy" if legacy is not None
                else "firebase_guest"
            ),
            "legacy_provenance_checked": True,
            "legacy_provenance": (
                "admin_created" if trusted
                else "untrusted_or_unmarked" if legacy is not None
                else "no_legacy_record"
            ),
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
        if account.get("firebase_uid") and uid and account["firebase_uid"] != uid:
            raise HTTPException(status_code=403, detail="Firebase identity does not match this account")
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
    if role == "admin":
        # Admin subscriptions do not expire; lock state still applies above.
        expired_at = None
    elif expired_at is not None:
        if not isinstance(expired_at, datetime):
            raise HTTPException(status_code=403, detail="Account expiry is invalid")
        if expired_at.tzinfo is None:
            expired_at = expired_at.replace(tzinfo=timezone.utc)
        if expired_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Account subscription has expired")

    if claims.get("email_verified") is not True:
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


class AdminStatusUpdate(BaseModel):
    status: Literal["active", "locked"]

class AdminRoleUpdate(BaseModel):
    role: Literal["guest", "user", "admin"]
    expired_at: datetime | None = None

class AdminExtendRequest(BaseModel):
    days: int = Field(ge=1, le=3650)

def _serialize_account(account: dict[str, Any]) -> dict[str, Any]:
    """Return only safe account fields for the Admin UI and audit log."""
    fields = (
        "email", "role", "status", "created_at", "expired_at", "updated_at",
        "created_source", "email_verified", "firebase_created_at",
    )
    return {
        key: (
            account.get(key).isoformat()
            if isinstance(account.get(key), datetime)
            else account.get(key)
        )
        for key in fields
    }

def _admin_target(db: Database, email: str) -> dict[str, Any]:
    normalized = email.strip().lower()
    if len(normalized) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
        raise HTTPException(status_code=422, detail="Invalid email address")
    account = db.users.find_one({"email": normalized})
    if account is None:
        raise HTTPException(status_code=404, detail="User not found")
    return account

def _ensure_another_active_admin(db: Database, target: dict[str, Any]) -> None:
    if target.get("role") == "admin" and target.get("status", "active") == "active":
        remaining = db.users.count_documents({"role": "admin", "status": "active", "email": {"$ne": target["email"]}})
        if remaining < 1:
            raise HTTPException(status_code=409, detail="Cannot remove or lock the last active Admin")

def _admin_audit(db: Database, actor: str, target: str, action: str, before: dict[str, Any], after: dict[str, Any]) -> None:
    db.users_admin_audit.insert_one({"actor_email": actor, "target_email": target, "action": action, "before": _serialize_account(before), "after": _serialize_account(after), "created_at": datetime.now(timezone.utc)})

EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS = 60
_email_verification_send_state: dict[str, float] = {}
_email_verification_send_lock = threading.Lock()


def _enforce_email_verification_resend_limit(email: str, now: float | None = None) -> None:
    """Apply a per-account resend cooldown within the single Render API process."""
    current = time.monotonic() if now is None else now
    normalized = email.strip().lower()
    with _email_verification_send_lock:
        previous = _email_verification_send_state.get(normalized)
        if previous is not None:
            elapsed = current - previous
            if elapsed < EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS:
                retry_after = max(1, int(EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS - elapsed))
                raise HTTPException(
                    status_code=429,
                    detail="Please wait before requesting another verification email.",
                    headers={"Retry-After": str(retry_after)},
                )
        _email_verification_send_state[normalized] = current
        if len(_email_verification_send_state) > 5000:
            cutoff = current - 3600
            for key, sent_at in list(_email_verification_send_state.items()):
                if sent_at < cutoff:
                    _email_verification_send_state.pop(key, None)


@router.post("/api/auth/send-verification")
def send_verification_email(authorization: str | None = Header(default=None)) -> dict[str, str]:
    """Send a Firebase verification action link to the authenticated account email."""
    claims = _verify_firebase_token(authorization)
    email = claims["email"]
    if claims.get("email_verified") is True:
        return {"status": "already_verified", "message": "Email address is already verified."}

    _enforce_email_verification_resend_limit(email)
    try:
        frontend_url = os.getenv(
            "FRONTEND_URL", "https://mimohouse.ddns.net"
        ).strip()
        if not frontend_url.startswith("https://"):
            raise RuntimeError("FRONTEND_URL must be an HTTPS URL")
        action_settings = firebase_auth.ActionCodeSettings(url=frontend_url)
        verification_link = firebase_auth.generate_email_verification_link(
            email,
            action_code_settings=action_settings,
            app=_firebase_app(),
        )
        from app.email.gmail import send_verification_email as send_via_gmail_api
        send_via_gmail_api(email, verification_link)
    except Exception as exc:
        logger.error(
            "verification_email_send_failed provider=gmail_api error_type=%s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="Unable to send verification email right now. Please try again later.",
        ) from exc

    logger.info("verification_email_accepted provider=gmail_api")
    return {
        "status": "sent",
        "message": "Gmail API accepted the verification email for delivery.",
    }


@router.get("/api/auth/me")
def current_account(user: dict[str, Any] = Depends(require_guest)) -> dict[str, Any]:
    return {"email": user["email"], "role": user["app_role"], "status": user["account_status"],
            "created_at": user.get("account_created_at").isoformat() if isinstance(user.get("account_created_at"), datetime) else None,
            "expired_at": user.get("account_expired_at").isoformat() if isinstance(user.get("account_expired_at"), datetime) else None}

def _firebase_user_created_at(firebase_user: Any) -> datetime | None:
    metadata = getattr(firebase_user, "user_metadata", None)
    timestamp_ms = getattr(metadata, "creation_timestamp", None)
    if not isinstance(timestamp_ms, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _list_firebase_users(limit: int) -> dict[str, Any]:
    """Read Firebase Auth as the source of truth for email verification state."""
    users: dict[str, Any] = {}
    page_token = None
    try:
        while len(users) < limit:
            kwargs: dict[str, Any] = {
                "max_results": min(1000, max(1, limit - len(users))),
                "app": _firebase_app(),
            }
            if page_token:
                kwargs["page_token"] = page_token
            page = firebase_auth.list_users(**kwargs)
            for firebase_user in page.users:
                email = getattr(firebase_user, "email", None)
                if isinstance(email, str) and email.strip():
                    users[email.strip().lower()] = firebase_user
                    if len(users) >= limit:
                        break
            page_token = getattr(page, "next_page_token", None)
            if not page_token:
                break
    except Exception as exc:
        logger.error("admin_firebase_user_list_failed error_type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=503, detail="Firebase user directory is temporarily unavailable"
        ) from exc
    return users


@router.get("/api/admin/users")
def admin_list_users(_: dict[str, Any] = Depends(require_admin), db: Database = Depends(db_dependency),
                     limit: int = Query(default=500, ge=1, le=1000)) -> list[dict[str, Any]]:
    """List registered Firebase accounts and enrich them with Dautu roles."""
    firebase_users = _list_firebase_users(limit)
    projection = {
        "_id": 0, "email": 1, "role": 1, "status": 1, "created_at": 1,
        "expired_at": 1, "updated_at": 1, "created_source": 1,
    }
    mongo_rows = list(db.users.find({}, projection).limit(limit))
    accounts = {
        row["email"].strip().lower(): dict(row)
        for row in mongo_rows
        if isinstance(row.get("email"), str) and row["email"].strip()
    }

    # Firebase-only accounts are important: newly registered users may not yet
    # have called an authenticated API endpoint, so MongoDB has no row for them.
    for email, firebase_user in firebase_users.items():
        account = accounts.setdefault(email, {
            "email": email,
            "role": "guest",
            "status": "active",
            "created_source": "firebase_guest",
        })
        firebase_created_at = _firebase_user_created_at(firebase_user)
        if not account.get("created_at") and firebase_created_at:
            account["created_at"] = firebase_created_at
        account["email_verified"] = bool(
            getattr(firebase_user, "email_verified", False)
        )
        account["firebase_created_at"] = firebase_created_at

    # A MongoDB-only row can be a stale or legacy record. Do not claim its
    # verification status; make that distinction visible in the Admin UI.
    for email, account in accounts.items():
        account.setdefault("email_verified", None)
        account.setdefault("firebase_created_at", None)

    ordered = sorted(accounts.values(), key=lambda row: row.get("email", ""))
    return [_serialize_account(row) for row in ordered[:limit]]

@router.patch("/api/admin/users/{email}/status")
def admin_update_status(payload: AdminStatusUpdate, email: str = Path(..., min_length=3, max_length=254),
                        actor: dict[str, Any] = Depends(require_admin), db: Database = Depends(db_dependency)) -> dict[str, Any]:
    target = _admin_target(db, email)
    if target["email"] == actor["email"] and payload.status == "locked":
        raise HTTPException(status_code=409, detail="You cannot lock your own Admin account")
    if payload.status == "locked": _ensure_another_active_admin(db, target)
    before = dict(target); now = datetime.now(timezone.utc)
    db.users.update_one({"email": target["email"]}, {"$set": {"status": payload.status, "updated_at": now}})
    after = db.users.find_one({"email": target["email"]})
    _admin_audit(db, actor["email"], target["email"], "status_changed", before, after)
    return _serialize_account(after)

@router.post("/api/admin/users/{email}/extend")
def admin_extend_user(payload: AdminExtendRequest, email: str = Path(..., min_length=3, max_length=254),
                      actor: dict[str, Any] = Depends(require_admin), db: Database = Depends(db_dependency)) -> dict[str, Any]:
    target = _admin_target(db, email)
    if target.get("role") != "user": raise HTTPException(status_code=409, detail="Only User accounts can be extended")
    now = datetime.now(timezone.utc); expiry = target.get("expired_at")
    if isinstance(expiry, datetime) and expiry.tzinfo is None: expiry = expiry.replace(tzinfo=timezone.utc)
    new_expiry = max(now, expiry) + timedelta(days=payload.days) if isinstance(expiry, datetime) else now + timedelta(days=payload.days)
    before = dict(target)
    db.users.update_one({"email": target["email"]}, {"$set": {"expired_at": new_expiry, "status": "active", "updated_at": now}})
    after = db.users.find_one({"email": target["email"]})
    _admin_audit(db, actor["email"], target["email"], "subscription_extended", before, after)
    return _serialize_account(after)

@router.patch("/api/admin/users/{email}/role")
def admin_update_role(payload: AdminRoleUpdate, email: str = Path(..., min_length=3, max_length=254),
                      actor: dict[str, Any] = Depends(require_admin), db: Database = Depends(db_dependency)) -> dict[str, Any]:
    target = _admin_target(db, email)
    if target["email"] == actor["email"] and payload.role != "admin":
        raise HTTPException(status_code=409, detail="You cannot remove your own Admin role")
    if target.get("role") == "admin" and payload.role != "admin": _ensure_another_active_admin(db, target)
    now = datetime.now(timezone.utc)
    if payload.role == "user":
        expiry = payload.expired_at or target.get("expired_at")
        if not isinstance(expiry, datetime): raise HTTPException(status_code=422, detail="A future expired_at is required for User role")
        if expiry.tzinfo is None: expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry <= now: raise HTTPException(status_code=422, detail="User expiry must be in the future")
        expired_at = expiry
    else: expired_at = None
    before = dict(target)
    db.users.update_one({"email": target["email"]}, {"$set": {
        "role": payload.role,
        "expired_at": expired_at,
        "legacy_provenance_checked": True,
        "legacy_provenance": "admin_managed",
        "created_source": "admin_managed",
        "updated_at": now,
    }})
    after = db.users.find_one({"email": target["email"]})
    _admin_audit(db, actor["email"], target["email"], "role_changed", before, after)
    return _serialize_account(after)


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
    """Shallow liveness probe: confirm the API process can serve requests.

    Keep this endpoint independent of databases and other external services so
    platform monitors can distinguish a live process from dependency outages.
    """
    return {"status": "ok"}


@router.api_route("/readyz", methods=["GET", "HEAD"])
def readyz() -> dict[str, str]:
    """Readiness probe: confirm the API can reach its required MongoDB database."""
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


@app.middleware("http")
async def log_http_request(request: Request, call_next):
    """Log mail-related requests and CORS preflight without flooding routine API logs."""
    tracked_paths = {"/api/test-send-mail"}
    if request.method != "OPTIONS" and request.url.path not in tracked_paths:
        return await call_next(request)
    started = time.monotonic()
    logger.info("http_request_started method=%s path=%s", request.method, request.url.path)
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.error(
            "http_request_failed method=%s path=%s error_type=%s",
            request.method, request.url.path, type(exc).__name__,
        )
        raise
    elapsed_ms = round((time.monotonic() - started) * 1000, 2)
    logger.info(
        "http_request_completed method=%s path=%s status=%s duration_ms=%s",
        request.method, request.url.path, response.status_code, elapsed_ms,
    )
    return response
