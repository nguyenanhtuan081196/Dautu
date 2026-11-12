"""Unit tests for server-side Firebase account authorization."""
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import HTTPException

from app.api.security import authorize_account


class AuthorizeAccountTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
        self.token = {"uid": "user-1", "email": "user@example.com"}
        self.account = {
            "email": "USER@example.com",
            "role": "user",
            "expiresAt": self.now + timedelta(days=1),
        }

    def assert_denied(self, token=None, account=None, status_code=403):
        with self.assertRaises(HTTPException) as raised:
            authorize_account(
                self.token if token is None else token,
                self.account if account is None else account,
                now=self.now,
            )
        self.assertEqual(raised.exception.status_code, status_code)

    def test_active_user_is_authorized(self):
        result = authorize_account(self.token, self.account, now=self.now)
        self.assertEqual(result["role"], "user")
        self.assertEqual(result["uid"], "user-1")
        self.assertIn("expires_at", result)

    def test_missing_account_is_denied(self):
        self.assert_denied(account=None)

    def test_missing_or_mismatched_email_is_denied(self):
        self.assert_denied(token={"uid": "x"})
        self.assert_denied(account={**self.account, "email": "other@example.com"})

    def test_unknown_role_is_denied(self):
        self.assert_denied(account={**self.account, "role": "owner"})

    def test_missing_malformed_or_expired_expiry_is_denied(self):
        self.assert_denied(account={k: v for k, v in self.account.items() if k != "expiresAt"})
        self.assert_denied(account={**self.account, "expiresAt": "not-a-date"})
        self.assert_denied(account={**self.account, "expiresAt": self.now})

    def test_legacy_iso_expiry_is_supported(self):
        legacy = {**self.account, "expiresAt": (self.now + timedelta(days=1)).isoformat()}
        self.assertEqual(authorize_account(self.token, legacy, now=self.now)["role"], "user")

    def test_admin_requires_server_side_email_allowlist(self):
        admin_token = {"uid": "admin-1", "email": "nguyenanhtuan081196@gmail.com"}
        admin_account = {"email": admin_token["email"], "role": "admin"}
        with patch.dict(os.environ, {"FIREBASE_ADMIN_EMAILS": admin_token["email"]}):
            self.assertEqual(authorize_account(admin_token, admin_account, now=self.now)["role"], "admin")
        self.assert_denied(token=admin_token, account=admin_account)

    def test_admin_role_does_not_bypass_allowlist(self):
        token = {"uid": "attacker", "email": "attacker@example.com"}
        account = {"email": token["email"], "role": "admin"}
        self.assert_denied(token=token, account=account)


if __name__ == "__main__":
    unittest.main()
