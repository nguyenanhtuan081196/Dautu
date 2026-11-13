"""Tests for the authenticated, uncached price metadata endpoint."""
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import main


class MetadataCollection:
    def __init__(self, document=None):
        self.document = document

    def find_one(self, query, projection=None):
        return self.document


class MetadataFirestore:
    def collection(self, name):
        if name != "allowed_users":
            raise AssertionError(f"Unexpected collection: {name}")
        return self

    def document(self, email):
        if email != "test-user@example.com":
            raise AssertionError(f"Unexpected account: {email}")
        return self

    @property
    def exists(self):
        return True

    def get(self):
        return self

    def to_dict(self):
        return {
            "email": "test-user@example.com",
            "role": "user",
            "expiresAt": datetime.now(timezone.utc) + timedelta(days=1),
        }


class PriceMetadataApiTests(unittest.TestCase):
    def _get(self, document):
        db = SimpleNamespace(app_metadata=MetadataCollection(document))
        claims = {
            "uid": "test-user",
            "email": "test-user@example.com",
            "email_verified": True,
        }
        with (
            patch("app.api.main.ensure_indexes"),
            patch("app.api.main._firebase_app", return_value=object()),
            patch("app.api.main.firebase_auth.verify_id_token", return_value=claims),
            patch("app.api.main.firestore.client", return_value=MetadataFirestore()),
            patch("app.api.main.get_database", return_value=db),
            patch.dict("os.environ", {"PRICE_SCHEDULER_ENABLED": "false"}),
            patch("app.core.application.close_client"),
        ):
            return TestClient(main.app).get(
                "/api/metadata", headers={"Authorization": "Bearer test-token"}
            )

    def test_returns_atlas_timestamp_and_sync_status_without_cache(self):
        timestamp = datetime(2026, 11, 13, 15, 10, tzinfo=timezone.utc)
        response = self._get({
            "last_updated": timestamp,
            "status": "succeeded",
            "symbols_total": 99,
            "symbols_success": 99,
            "symbols_failed": 0,
        })
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        returned_timestamp = datetime.fromisoformat(payload["last_updated"].replace("Z", "+00:00"))
        self.assertEqual(returned_timestamp, timestamp)
        self.assertEqual({key: value for key, value in payload.items() if key != "last_updated"}, {
            "status": "succeeded",
            "symbols_total": 99,
            "symbols_success": 99,
            "symbols_failed": 0,
        })
        self.assertIn("no-cache", response.headers.get("Cache-Control", ""))
        self.assertEqual(response.headers.get("Pragma"), "no-cache")

    def test_empty_metadata_returns_safe_unknown_payload(self):
        response = self._get(None)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "last_updated": None,
            "status": "unknown",
            "symbols_total": 0,
            "symbols_success": 0,
            "symbols_failed": 0,
        })


if __name__ == "__main__":
    unittest.main()
