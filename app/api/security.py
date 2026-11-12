"""Server-side authorization for Firebase-authenticated API requests."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException


DEFAULT_ADMIN_EMAILS = {"nguyenanhtuan081196@gmail.com"}


def _admin_emails() -> set[str]:
    configured = os.getenv("FIREBASE_ADMIN_EMAILS", "")
    if not configured.strip():
        return DEFAULT_ADMIN_EMAILS
    return {email.strip().lower() for email in configured.split(",") if email.strip()}


def _expiry_datetime(value: Any) -> datetime | None:
    """Accept Firestore Timestamp/datetime and legacy ISO-8601 strings."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        raw = value.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def authorize_account(
    token: dict[str, Any],
    account: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Require a matching allow-list document, valid role and unexpired access."""
    email = token.get("email")
    if not isinstance(email, str) or not email.strip():
        raise HTTPException(status_code=403, detail="Firebase account has no email")
    email = email.strip().lower()

    if not isinstance(account, dict):
        raise HTTPException(status_code=403, detail="Account is not authorized")

    stored_email = account.get("email")
    if not isinstance(stored_email, str) or stored_email.strip().lower() != email:
        raise HTTPException(status_code=403, detail="Account authorization record mismatch")

    role = account.get("role")
    if role == "admin":
        if email not in _admin_emails():
            raise HTTPException(status_code=403, detail="Administrator access is not allowed")
        return {**token, "role": "admin"}

    if role != "user":
        raise HTTPException(status_code=403, detail="Account role is not authorized")

    expires_at = _expiry_datetime(account.get("expiresAt"))
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    if expires_at is None or expires_at <= current_time.astimezone(timezone.utc):
        raise HTTPException(status_code=403, detail="Account access has expired")

    return {**token, "role": "user", "expires_at": expires_at.isoformat()}
