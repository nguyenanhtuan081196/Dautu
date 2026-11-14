"""Tests for the extracted infrastructure configuration and middleware."""
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import get_allowed_hosts, get_allowed_origins
from app.middleware import install_middleware


class InfrastructureConfigTests(unittest.TestCase):
    def test_origins_are_explicit_and_whitespace_is_removed(self):
        with patch.dict("os.environ", {"CORS_ALLOWED_ORIGINS": " https://a.example, ,https://b.example "}, clear=False):
            self.assertEqual(
                get_allowed_origins(),
                ["https://a.example", "https://b.example"],
            )

    def test_cors_is_disabled_when_no_origins_are_configured(self):
        with patch.dict("os.environ", {"CORS_ALLOWED_ORIGINS": ""}, clear=False):
            self.assertEqual(get_allowed_origins(), [])

    def test_hosts_include_render_hostname_without_duplicates(self):
        env = {
            "API_ALLOWED_HOSTS": "api.example, api.example",
            "RENDER_EXTERNAL_HOSTNAME": "service.onrender.com",
        }
        with patch.dict("os.environ", env, clear=False):
            self.assertEqual(
                get_allowed_hosts(),
                ["api.example", "service.onrender.com"],
            )

    def test_hosts_have_safe_local_defaults(self):
        env = {"API_ALLOWED_HOSTS": "", "RENDER_EXTERNAL_HOSTNAME": ""}
        with patch.dict("os.environ", env, clear=False):
            self.assertEqual(
                get_allowed_hosts(),
                ["localhost", "127.0.0.1", "testserver"],
            )

    def test_cors_preflight_allows_authorization_and_cache_control(self):
        app = FastAPI()
        app.add_api_route("/api/stocks", lambda: {"ok": True}, methods=["GET"])
        with (
            patch("app.middleware.get_allowed_origins", return_value=["https://mimohouse.ddns.net"]),
            patch("app.middleware.get_allowed_hosts", return_value=["testserver"]),
        ):
            install_middleware(app)
            with TestClient(app) as client:
                response = client.options(
                    "/api/stocks",
                    headers={
                        "Origin": "https://mimohouse.ddns.net",
                        "Access-Control-Request-Method": "GET",
                        "Access-Control-Request-Headers": "authorization,cache-control",
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("Access-Control-Allow-Origin"),
            "https://mimohouse.ddns.net",
        )
        allowed_headers = response.headers.get("Access-Control-Allow-Headers", "").lower()
        self.assertIn("authorization", allowed_headers)
        self.assertIn("cache-control", allowed_headers)


if __name__ == "__main__":
    unittest.main()
