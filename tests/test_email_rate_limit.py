"""Tests for MongoDB-backed Gmail verification rate limits."""
from __future__ import annotations

import threading
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

from app.services.email_rate_limit import MongoEmailRateLimiter


class FakeRateLimitCollection:
    def __init__(self):
        self.documents = {}
        self.lock = threading.Lock()
        self.indexes = []

    def create_index(self, *args, **kwargs):
        self.indexes.append((args, kwargs))

    def find_one_and_update(self, query, update, upsert=False, return_document=None):
        key = query["_id"]
        with self.lock:
            document = self.documents.get(key)
            if document is None:
                if not upsert:
                    return None
                document = dict(update.get("$setOnInsert", {}))
                document["_id"] = key
                self.documents[key] = document
            document["count"] = document.get("count", 0) + update["$inc"]["count"]
            return dict(document)


class FakeDatabase:
    def __init__(self):
        self.email_rate_limits = FakeRateLimitCollection()


class MongoEmailRateLimiterTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDatabase()
        self.limiter = MongoEmailRateLimiter(self.db)
        self.start = datetime(2026, 11, 14, 12, 0, 5, tzinfo=timezone.utc)

    def test_second_attempt_in_same_minute_returns_429(self):
        self.limiter.check(
            email="person@example.com", ip_address="203.0.113.10", now=self.start
        )
        with self.assertRaises(HTTPException) as error:
            self.limiter.check(
                email="person@example.com", ip_address="203.0.113.10", now=self.start
            )
        self.assertEqual(error.exception.status_code, 429)
        self.assertIn("Retry-After", error.exception.headers)

    def test_fourth_attempt_within_one_hour_returns_429(self):
        for minute in (0, 1, 2):
            self.limiter.check(
                email="person@example.com",
                ip_address=f"203.0.113.{10 + minute}",
                now=self.start.replace(minute=self.start.minute + minute),
            )
        with self.assertRaises(HTTPException) as error:
            self.limiter.check(
                email="person@example.com",
                ip_address="203.0.113.20",
                now=self.start.replace(minute=self.start.minute + 3),
            )
        self.assertEqual(error.exception.status_code, 429)

    def test_ten_concurrent_attempts_allow_exactly_one_for_account_minute_limit(self):
        barrier = threading.Barrier(10)
        outcomes = []
        outcome_lock = threading.Lock()

        def attempt():
            barrier.wait()
            try:
                self.limiter.check(
                    email="parallel@example.com",
                    ip_address="203.0.113.30",
                    now=self.start,
                )
                result = "allowed"
            except HTTPException as error:
                result = error.status_code
            with outcome_lock:
                outcomes.append(result)

        threads = [threading.Thread(target=attempt) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(outcomes.count("allowed"), 1)
        self.assertEqual(outcomes.count(429), 9)

    def test_counter_survives_limiter_recreation_like_server_restart(self):
        self.limiter.check(
            email="restart@example.com", ip_address="203.0.113.40", now=self.start
        )
        # A new limiter instance represents a fresh application process. It
        # sees the same MongoDB collection and therefore retains the quota.
        restarted_limiter = MongoEmailRateLimiter(self.db)
        with self.assertRaises(HTTPException) as error:
            restarted_limiter.check(
                email="restart@example.com",
                ip_address="203.0.113.40",
                now=self.start,
            )
        self.assertEqual(error.exception.status_code, 429)

    def test_only_hashed_identifiers_are_stored(self):
        self.limiter.check(
            email="private@example.com", ip_address="203.0.113.50", now=self.start
        )
        serialized = repr(self.db.email_rate_limits.documents)
        self.assertNotIn("private@example.com", serialized)
        self.assertNotIn("203.0.113.50", serialized)


class SendVerificationEndpointRateLimitTests(unittest.TestCase):
    def test_endpoint_returns_429_before_second_email_is_sent(self):
        from app.api import main

        database = FakeDatabase()
        request = Request({
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/auth/send-verification",
            "raw_path": b"/api/auth/send-verification",
            "query_string": b"",
            "headers": [],
            "client": ("198.51.100.42", 12345),
            "server": ("testserver", 80),
        })
        claims = {
            "uid": "firebase-uid",
            "email": "verify@example.com",
            "email_verified": False,
        }
        with (
            patch("app.api.main.get_database", return_value=database),
            patch("app.api.main._firebase_app", return_value=object()),
            patch("app.api.main.firebase_auth.verify_id_token", return_value=claims),
            patch("app.api.main.firebase_auth.generate_email_verification_link", return_value="https://example.test/verify"),
            patch("app.api.main._send_gmail_verification") as send_email,
        ):
            main.send_verification_email(request, "Bearer valid-token")
            with self.assertRaises(HTTPException) as error:
                main.send_verification_email(request, "Bearer valid-token")

        self.assertEqual(error.exception.status_code, 429)
        send_email.assert_called_once()


if __name__ == "__main__":
    unittest.main()
