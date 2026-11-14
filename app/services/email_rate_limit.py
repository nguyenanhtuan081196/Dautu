"""MongoDB-backed atomic rate limits for verification email delivery."""
from __future__ import annotations

import hashlib
import math
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError


class MongoEmailRateLimiter:
    """Enforce shared account/IP quotas using atomic MongoDB increments.

    Account policy: 1 attempt per minute and 3 attempts per hour.
    IP policy: 10 attempts per minute and 30 attempts per hour, allowing
    multiple legitimate users behind the same household/mobile NAT address.

    Counters use fixed UTC windows. A counter represents an attempt, not only a
    successful SMTP delivery, so failed provider calls cannot be retried to
    bypass the quota. Only SHA-256 subject digests are persisted.
    """

    ACCOUNT_LIMITS = ((60, 1), (3600, 3))
    IP_LIMITS = ((60, 10), (3600, 30))
    RETENTION_SECONDS = 3600

    def __init__(self, database: Any):
        self.collection = database.email_rate_limits

    @staticmethod
    def _subject_digest(value: str) -> str:
        normalized = value.strip().lower()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _increment(
        self,
        *,
        scope: str,
        subject: str,
        window_seconds: int,
        now: datetime,
    ) -> tuple[int, int]:
        timestamp = now.timestamp()
        window_start = int(timestamp // window_seconds) * window_seconds
        window_end = window_start + window_seconds
        digest = self._subject_digest(subject)
        document_id = f"{scope}:{window_seconds}:{window_start}:{digest}"
        expires_at = datetime.fromtimestamp(
            window_end + self.RETENTION_SECONDS, tz=timezone.utc
        )
        update = {
            "$inc": {"count": 1},
            "$setOnInsert": {
                "scope": scope,
                "window_seconds": window_seconds,
                "window_start": datetime.fromtimestamp(window_start, tz=timezone.utc),
                "expires_at": expires_at,
                "count": 0,
            },
        }
        query = {"_id": document_id}

        try:
            document = self.collection.find_one_and_update(
                query,
                update,
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            # Two first requests may race to upsert the same deterministic _id.
            # Retry as an update against the document created by the winner.
            document = self.collection.find_one_and_update(
                query,
                {"$inc": {"count": 1}},
                upsert=False,
                return_document=ReturnDocument.AFTER,
            )
        if document is None:
            raise RuntimeError("MongoDB did not return the updated rate-limit counter")

        count = int(document["count"])
        retry_after = max(1, math.ceil(window_end - timestamp))
        return count, retry_after

    def check(
        self,
        *,
        email: str,
        ip_address: str,
        now: datetime | None = None,
    ) -> None:
        """Atomically count one send attempt for the account and source IP."""
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        current = current.astimezone(timezone.utc)

        exceeded_retry_after: list[int] = []
        policies = (
            ("account", email, self.ACCOUNT_LIMITS),
            ("ip", ip_address or "unknown", self.IP_LIMITS),
        )
        for scope, subject, limits in policies:
            for window_seconds, maximum in limits:
                count, retry_after = self._increment(
                    scope=scope,
                    subject=subject,
                    window_seconds=window_seconds,
                    now=current,
                )
                if count > maximum:
                    exceeded_retry_after.append(retry_after)

        if exceeded_retry_after:
            raise HTTPException(
                status_code=429,
                detail="Bạn đã yêu cầu gửi email quá nhiều lần. Vui lòng thử lại sau.",
                headers={"Retry-After": str(max(exceeded_retry_after))},
            )
