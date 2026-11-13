"""Regression tests for the Dautu API compatibility boundary.

These tests intentionally exercise the existing Dautu application without
replacing its MongoDB, Firebase membership, SMTP, or business logic adapters.
"""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import main


class ApiCompatibilityTests(unittest.TestCase):
    def test_public_and_protected_route_contract_is_stable(self):
        routes = {
            (method, route.path)
            for route in main.app.routes
            for method in (getattr(route, "methods", None) or set())
        }
        expected = {
            ("POST", "/api/auth/send-verification"),
            ("GET", "/healthz"),
            ("GET", "/api/status"),
            ("GET", "/api/stocks"),
            ("GET", "/api/stocks/{symbol}"),
            ("GET", "/api/screener"),
            ("GET", "/api/simulations"),
            ("GET", "/api/simulations/{symbol}"),
            ("GET", "/api/history/{symbol}"),
            ("GET", "/api/financials/{symbol}"),
            ("GET", "/api/analysis/{symbol}"),
        }
        self.assertTrue(expected.issubset(routes))

    def test_healthz_returns_ok_when_database_is_available(self):
        with patch("app.api.main.ping_database", return_value=True):
            response = TestClient(main.app).get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_healthz_returns_503_when_database_is_unavailable(self):
        with patch("app.api.main.ping_database", side_effect=TimeoutError("offline")):
            response = TestClient(main.app).get("/healthz")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "Service unavailable"})

    def test_startup_still_creates_dautu_specific_indexes(self):
        with patch("app.api.main.ensure_indexes") as ensure_indexes:
            main.startup()
        ensure_indexes.assert_called_once_with()

    def test_security_headers_remain_present_on_health_response(self):
        with patch("app.api.main.ping_database", return_value=True):
            response = TestClient(main.app).get("/healthz")
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.headers.get("Referrer-Policy"), "no-referrer")
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")
        self.assertEqual(
            response.headers.get("Permissions-Policy"),
            "camera=(), microphone=(), geolocation=()",
        )

    def test_cors_remains_restricted_to_existing_methods_and_headers(self):
        cors = [
            middleware.options
            for middleware in main.app.user_middleware
            if middleware.cls.__name__ == "CORSMiddleware"
        ]
        if not cors:
            # CORS is intentionally disabled unless exact origins are configured.
            self.assertEqual(main._allowed_origins(), [])
            return
        self.assertEqual(cors[0]["allow_methods"], ["GET", "POST", "OPTIONS"])
        self.assertEqual(cors[0]["allow_headers"], ["Authorization", "Content-Type"])
        self.assertFalse(cors[0]["allow_credentials"])

    def test_docs_remain_disabled_in_production_api(self):
        self.assertIsNone(main.app.docs_url)
        self.assertIsNone(main.app.redoc_url)
        self.assertIsNone(main.app.openapi_url)


if __name__ == "__main__":
    unittest.main()
