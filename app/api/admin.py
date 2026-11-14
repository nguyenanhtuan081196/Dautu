"""Admin-only user management API.

Firebase remains the identity provider. MongoDB stores the application account
state used by API authorization; Firestore membership records are synchronized
for compatibility with the existing browser application and security rules.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from firebase_admin import firestore
from pydantic import BaseModel, ConfigDict, Field
from pymongo.database import Database

from app.api.main import ADMIN_EMAIL, _firebase_app, db_dependency, require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["active", "locked"] | None = None
    role: Literal["user", "admin"] | None = None
    expired_at: datetime | None = None


def _sync_firestore_users(db: Database) -> None:
    """Import current allow-list records so pre-existing users appear in Admin."""
    collection = firestore.client(app=_firebase_app()).collection("allowed_users")
    for document in collection.stream():
        data = document.to_dict() or {}
        email = str(data.get("email") or document.id).strip().lower()
        if not email:
            continue
        expires_at = data.get("expiresAt")
        if isinstance(expires_at, datetime) and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        created_at = getattr(document, "create_time", None) or datetime.now(timezone.utc)
        db.users.update_one(
            {"email": email},
            {
                "$setOnInsert": {
                    "email": email,
                    "firebase_uid": None,
                    "created_at": created_at,
                    "status": "active",
                    "role": data.get("role", "user"),
                },
                "$set": {
                    "role": data.get("role", "user"),
                    "expired_at": expires_at,
                    "updated_at": datetime.now(timezone.utc),
                },
            },
            upsert=True,
        )


@router.get("/users")
def list_users(
    _: dict[str, Any] = Depends(require_admin),
    db: Database = Depends(db_dependency),
    limit: int = Query(default=500, ge=1, le=1000),
) -> dict[str, Any]:
    """Return the MongoDB account registry after a safe Firestore compatibility sync."""
    _sync_firestore_users(db)
    now = datetime.now(timezone.utc)
    users = []
    for item in db.users.find({}, {"_id": 0}).sort("email", 1).limit(limit):
        expires_at = item.get("expired_at")
        if isinstance(expires_at, datetime) and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        status = item.get("status", "active")
        if item.get("role", "user") != "admin" and (expires_at is None or expires_at <= now):
            status = "expired" if status == "active" else status
        users.append({
            "email": item.get("email"),
            "joined_at": item.get("created_at"),
            "expired_at": expires_at,
            "role": item.get("role", "user"),
            "status": status,
        })
    return {"users": users, "count": len(users)}


@router.patch("/users/{email}")
def update_user(
    payload: UserUpdate,
    email: str = Path(..., min_length=3, max_length=254),
    admin: dict[str, Any] = Depends(require_admin),
    db: Database = Depends(db_dependency),
) -> dict[str, Any]:
    """Change one user's role, lock state or subscription expiry."""
    normalized_email = email.strip().lower()
    if "@" not in normalized_email:
        raise HTTPException(status_code=422, detail="Invalid email address")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="No account changes supplied")

    target = db.users.find_one({"email": normalized_email})
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    if normalized_email == str(admin.get("email", "")).lower():
        if changes.get("status") == "locked" or changes.get("role") == "user":
            raise HTTPException(status_code=409, detail="You cannot lock or demote your own Admin account")

    if changes.get("role") == "user" and target.get("role") == "admin":
        admin_count = db.users.count_documents({"role": "admin", "status": {"$ne": "locked"}})
        if admin_count <= 1:
            raise HTTPException(status_code=409, detail="The last active Admin cannot be demoted")

    if "expired_at" in changes:
        expiry = changes["expired_at"]
        if expiry is None:
            raise HTTPException(status_code=422, detail="expired_at must be a timestamp")
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        changes["expired_at"] = expiry

    changes["updated_at"] = datetime.now(timezone.utc)
    db.users.update_one({"email": normalized_email}, {"$set": changes})

    # Keep the legacy Firestore-backed browser membership in sync. MongoDB
    # remains the account-state registry; Firestore still protects direct reads.
    firestore_changes: dict[str, Any] = {}
    if "role" in changes:
        firestore_changes["role"] = changes["role"]
    if "expired_at" in changes:
        firestore_changes["expiresAt"] = changes["expired_at"]
    if firestore_changes:
        try:
            firestore.client(app=_firebase_app()).collection("allowed_users").document(
                normalized_email
            ).update(firestore_changes)
        except Exception as exc:
            # Do not hide a partial write: the caller needs to know to reconcile.
            raise HTTPException(
                status_code=503,
                detail="MongoDB was updated but Firestore synchronization failed; retry or reconcile this account",
            ) from exc

    updated = db.users.find_one({"email": normalized_email}, {"_id": 0})
    return {
        "email": updated.get("email"),
        "role": updated.get("role"),
        "status": updated.get("status", "active"),
        "expired_at": updated.get("expired_at"),
    }
