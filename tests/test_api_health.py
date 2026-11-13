"""Operational health endpoint tests for the deployed Dautu API."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.main import app


class HealthEndpointTests(unittest.TestCase):
    def test_healthz_returns_ok_when_mongodb_ping_succeeds(self):
        with (
            patch("app.api.main.ensure_indexes"),
            patch("app.api.main.ping_database", return_value=True) as ping_database,
            patch("app.core.application.close_client"),
        ):
            with TestClient(app) as client:
                response = client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        ping_database.assert_called_once_with()

    def test_healthz_hides_mongodb_failure_details(self):
        with (
            patch("app.api.main.ensure_indexes"),
            patch("app.api.main.ping_database", side_effect=RuntimeError("private database detail")),
            patch("app.core.application.close_client"),
        ):
            with TestClient(app) as client:
                response = client.get("/healthz")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "Service unavailable"})


if __name__ == "__main__":
    unittest.main()
