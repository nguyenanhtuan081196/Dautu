"""Unit tests for API-side Firebase allowlist and expiry enforcement."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import HTTPException

from app.api import main


class FakeDocument:
    def __init__(self, data=None):
        self.exists = data is not None
        self._data = data or {}

    def to_dict(self):
        return self._data


class FakeCollection:
    def __init__(self, document):
        self.document = document

    def document(self, email):
        self.email = email
        return self

    def get(self):
        return self.document_value


class FakeFirestoreClient:
    def __init__(self, document):
        self.document_value = document

    def collection(self, name):
        self.collection_name = name
        return self

    def document(self, email):
        self.email = email
        return self

    def get(self):
        return self.document_value


class RequireUserTests(unittest.TestCase):
    def setUp(self):
        self.firebase_app = object()
        self.claims = {"uid": "uid-123", "email": "USER@example.com"}
        self.token_patch = patch.object(
            main.firebase_auth, "verify_id_token", return_value=self.claims
        )
        self.app_patch = patch.object(main, "_firebase_app", return_value=self.firebase_app)
        self.token_patch.start()
        self.app_patch.start()
        self.addCleanup(self.token_patch.stop)
        self.addCleanup(self.app_patch.stop)

    def call_with_document(self, document):
        client = FakeFirestoreClient(document)
        with patch.object(main.firestore, "client", return_value=client):
            return main.require_user("Bearer valid-token")

    def test_active_allowlisted_user_is_accepted(self):
        doc = FakeDocument({
            "email": "user@example.com",
            "role": "user",
            "expiresAt": datetime.now(timezone.utc) + timedelta(days=1),
        })
        result = self.call_with_document(doc)
        self.assertEqual(result["access_role"], "user")
        self.assertEqual(result["access_email"], "user@example.com")

    def test_missing_allowlist_record_is_denied(self):
        with self.assertRaises(HTTPException) as caught:
            self.call_with_document(FakeDocument())
        self.assertEqual(caught.exception.status_code, 403)

    def test_expired_user_is_denied(self):
        doc = FakeDocument({
            "email": "user@example.com",
            "role": "user",
            "expiresAt": datetime.now(timezone.utc) - timedelta(seconds=1),
        })
        with self.assertRaises(HTTPException) as caught:
            self.call_with_document(doc)
        self.assertEqual(caught.exception.status_code, 403)

    def test_admin_does_not_require_expiry_timestamp(self):
        doc = FakeDocument({"email": "user@example.com", "role": "admin"})
        result = self.call_with_document(doc)
        self.assertEqual(result["access_role"], "admin")

    def test_email_mismatch_is_denied(self):
        doc = FakeDocument({
            "email": "other@example.com",
            "role": "user",
            "expiresAt": datetime.now(timezone.utc) + timedelta(days=1),
        })
        with self.assertRaises(HTTPException) as caught:
            self.call_with_document(doc)
        self.assertEqual(caught.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
