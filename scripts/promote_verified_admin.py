"""Promote one verified Firebase account to Dautu Admin.

Safe by default: without --apply this script only validates prerequisites.
It never changes Firebase's email_verified flag; the account must already be
verified by following Firebase's own email verification flow.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

import firebase_admin
from firebase_admin import auth, credentials

from app.api.main import ADMIN_EMAIL
from app.database.mongo import get_database

TARGET_EMAIL = "tuanguyen081196@gmail.com"


def _firebase_app():
    raw = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON is not configured")
    try:
        service_account = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON is invalid JSON") from exc
    try:
        return firebase_admin.get_app()
    except ValueError:
        return firebase_admin.initialize_app(credentials.Certificate(service_account))


def promote_verified_admin(*, apply: bool = False) -> dict[str, object]:
    email = TARGET_EMAIL
    user = auth.get_user_by_email(email, app=_firebase_app())
    if user.email_verified is not True:
        raise RuntimeError(
            f"{email} is not verified in Firebase. Complete Firebase email verification first; "
            "this script will not set email_verified."
        )

    db = get_database()
    before = db.users.find_one({"email": email})
    if before and before.get("firebase_uid") and before["firebase_uid"] != user.uid:
        raise RuntimeError("MongoDB Firebase UID does not match the Firebase account")

    now = datetime.now(timezone.utc)
    status = before.get("status", "active") if before else "active"
    update = {
        "email": email,
        "firebase_uid": user.uid,
        "role": "admin",
        "status": status,
        "expired_at": None,
        "legacy_provenance_checked": True,
        "legacy_provenance": "admin_managed",
        "created_source": "admin_managed",
        "updated_at": now,
    }
    if not apply:
        return {
            "mode": "dry_run",
            "email": email,
            "firebase_email_verified": True,
            "firebase_uid_matches": not before or not before.get("firebase_uid") or before["firebase_uid"] == user.uid,
            "current_role": before.get("role") if before else None,
            "current_status": status,
            "would_set_role": "admin",
            "email_verified_will_be_changed": False,
        }

    db.users.update_one(
        {"email": email},
        {
            "$set": {key: value for key, value in update.items() if key != "email"},
            "$setOnInsert": {"email": email, "created_at": now},
        },
        upsert=True,
    )
    after = db.users.find_one({"email": email})
    db.users_admin_audit.insert_one({
        "actor_email": ADMIN_EMAIL,
        "target_email": email,
        "action": "admin_promoted_by_verified_admin_script",
        "before": {
            "role": before.get("role") if before else None,
            "status": before.get("status") if before else None,
        },
        "after": {"role": "admin", "status": status},
        "created_at": now,
    })
    return {
        "mode": "applied",
        "email": email,
        "role": after.get("role") if after else None,
        "status": after.get("status") if after else None,
        "firebase_email_verified": True,
        "email_verified_was_not_changed": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the Admin role to MongoDB. Omit for a read-only dry run.",
    )
    args = parser.parse_args()
    result = promote_verified_admin(apply=args.apply)
    for key, value in result.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
