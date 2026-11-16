"""Tests for the authenticated Gmail API verification endpoint."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import main


class SendVerificationEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.claims = {
            "uid": "unverified-uid",
            "email": "new.user@example.com",
            "email_verified": False,
        }

    @patch("app.api.main._enforce_email_verification_resend_limit")
    @patch("app.email.gmail.send_verification_email")
    @patch("app.api.main.firebase_auth.generate_email_verification_link")
    @patch("app.api.main._verify_firebase_token")
    def test_sends_link_only_to_authenticated_unverified_user(
        self, verify_token, generate_link, send_email, _rate_limit
    ):
        verify_token.return_value = self.claims
        generate_link.return_value = "https://firebase.example/action?oobCode=secret"
        response = self.client.post(
            "/api/auth/send-verification",
            headers={"Authorization": "Bearer valid-token"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "sent")
        verify_token.assert_called_once_with("Bearer valid-token")
        generate_link.assert_called_once()
        self.assertEqual(generate_link.call_args.args[0], "new.user@example.com")
        send_email.assert_called_once_with(
            "new.user@example.com",
            "https://firebase.example/action?oobCode=secret",
        )

    @patch("app.api.main._verify_firebase_token")
    def test_verified_account_does_not_send_another_email(self, verify_token):
        verify_token.return_value = {
            **self.claims,
            "email_verified": True,
        }
        with patch("app.email.gmail.send_verification_email") as send_email:
            response = self.client.post(
                "/api/auth/send-verification",
                headers={"Authorization": "Bearer valid-token"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "already_verified")
        send_email.assert_not_called()

    def test_missing_bearer_token_is_rejected(self):
        response = self.client.post("/api/auth/send-verification")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
