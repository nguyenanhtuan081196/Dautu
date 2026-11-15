"""Unit tests for Resend verification email delivery."""
import unittest
from unittest.mock import Mock, patch

from app.api.main import _send_resend_verification


class ResendVerificationTests(unittest.TestCase):
    @patch.dict("os.environ", {"RESEND_API_KEY": "re_test_key", "RESEND_FROM_EMAIL": "Dautu <no-reply@example.com>"})
    @patch("app.api.main.requests.post")
    def test_sends_firebase_link_through_resend_api(self, post):
        post.return_value = Mock(ok=True, status_code=200, headers={"x-resend-id": "email_123"})
        _send_resend_verification("user@example.net", "https://firebase.test/action?oobCode=abc")
        post.assert_called_once()
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://api.resend.com/emails")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer re_test_key")
        self.assertEqual(kwargs["json"]["from"], "Dautu <no-reply@example.com>")
        self.assertEqual(kwargs["json"]["to"], ["user@example.net"])
        self.assertIn("https://firebase.test/action?oobCode=abc", kwargs["json"]["text"])
        self.assertEqual(kwargs["timeout"], 20)

    @patch.dict("os.environ", {}, clear=True)
    def test_requires_resend_key_and_sender(self):
        with self.assertRaises(RuntimeError):
            _send_resend_verification("user@example.net", "https://firebase.test/action")

    @patch.dict("os.environ", {"RESEND_API_KEY": "re_test_key", "RESEND_FROM_EMAIL": "Dautu <no-reply@example.com>"})
    @patch("app.api.main.requests.post")
    def test_provider_rejection_is_reported(self, post):
        import requests
        response = Mock(ok=False, status_code=403, headers={})
        response.raise_for_status.side_effect = requests.HTTPError("403 Forbidden")
        post.return_value = response
        with self.assertRaises(RuntimeError):
            _send_resend_verification("user@example.net", "https://firebase.test/action")


if __name__ == "__main__":
    unittest.main()
