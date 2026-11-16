"""Tests for Gmail API email delivery without contacting Google."""
import base64
import os
import unittest
from email import message_from_bytes
from unittest.mock import MagicMock, patch

from app.email.gmail import GMAIL_SEND_SCOPE, TOKEN_URI, send_verification_email


class GmailApiSenderTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            "GOOGLE_CLIENT_ID": "client-id",
            "GOOGLE_CLIENT_SECRET": "client-secret",
            "GOOGLE_REFRESH_TOKEN": "refresh-token",
            "GMAIL_SENDER_EMAIL": "mimo.homeserver@gmail.com",
            "GMAIL_FROM_NAME": "Dautu",
        }
        self.env_patch = patch.dict(os.environ, self.env, clear=True)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    @patch("app.email.gmail.build")
    @patch("app.email.gmail.Credentials")
    def test_sends_mime_message_through_gmail_api(self, credentials_factory, build):
        execute = MagicMock(return_value={"id": "gmail-message-id"})
        build.return_value.users.return_value.messages.return_value.send.return_value.execute = execute

        result = send_verification_email(
            "new.user@example.com",
            "https://example.com/verify?oobCode=opaque-token",
        )

        self.assertEqual(result, "gmail-message-id")
        credentials_factory.assert_called_once_with(
            token=None,
            refresh_token="refresh-token",
            token_uri=TOKEN_URI,
            client_id="client-id",
            client_secret="client-secret",
            scopes=[GMAIL_SEND_SCOPE],
        )
        build.assert_called_once_with(
            "gmail", "v1", credentials=credentials_factory.return_value,
            cache_discovery=False,
        )
        call = build.return_value.users.return_value.messages.return_value.send
        call.assert_called_once()
        self.assertEqual(call.call_args.kwargs["userId"], "me")
        raw = call.call_args.kwargs["body"]["raw"]
        parsed = message_from_bytes(base64.urlsafe_b64decode(raw))
        self.assertEqual(parsed["To"], "new.user@example.com")
        self.assertIn("Dautu", parsed["From"])
        self.assertIn("Xác minh", parsed["Subject"])
        self.assertIn("oobCode=opaque-token", parsed.get_body(preferencelist=("plain",)).get_content())

    def test_missing_refresh_token_fails_before_network_call(self):
        with patch.dict(os.environ, {"GOOGLE_REFRESH_TOKEN": ""}):
            with self.assertRaisesRegex(RuntimeError, "GOOGLE_REFRESH_TOKEN"):
                send_verification_email("new.user@example.com", "https://example.com/verify")


if __name__ == "__main__":
    unittest.main()
