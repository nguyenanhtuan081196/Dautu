"""Tests for the authenticated, uncached price metadata endpoint."""
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import main


class MetadataCollection:
    def __init__(self, document=None):
        self.document = document

    def find_one(self, query, projection=None):
        return self.document


class PriceMetadataApiTests(unittest.TestCase):
    def setUp(self):
        self.original_overrides = main.app.dependency_overrides.copy()
        main.app.dependency_overrides[main.require_user] = lambda: {"uid": "test-user"}

    def tearDown(self):
        main.app.dependency_overrides.clear()
        main.app.dependency_overrides.update(self.original_overrides)

    def _get(self, document):
        db = SimpleNamespace(app_metadata=MetadataCollection(document))
        main.app.dependency_overrides[main.db_dependency] = lambda: db
        with (
            patch("app.api.main.ensure_indexes"),
            patch.dict("os.environ", {"PRICE_SCHEDULER_ENABLED": "false"}),
            patch("app.core.application.close_client"),
        ):
            return TestClient(main.app).get("/api/metadata")

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
