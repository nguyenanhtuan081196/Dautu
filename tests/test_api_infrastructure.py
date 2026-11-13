"""Tests for the extracted infrastructure configuration and middleware."""
import unittest
from unittest.mock import patch

from app.core.config import get_allowed_hosts, get_allowed_origins


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


if __name__ == "__main__":
    unittest.main()
