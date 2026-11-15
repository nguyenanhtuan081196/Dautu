"""Unit tests for Gmail SMTP verification email delivery."""
import unittest
from unittest.mock import MagicMock, patch
from app.api.main import _send_gmail_verification


class GmailVerificationTests(unittest.TestCase):
    @patch.dict("os.environ", {"GMAIL_SMTP_USER":"owner@gmail.com","GMAIL_SMTP_APP_PASSWORD":"abcd efgh ijkl mnop","GMAIL_FROM_NAME":"Dautu"}, clear=True)
    @patch("app.api.main.smtplib.SMTP_SSL")
    def test_sends_firebase_link_through_gmail_smtp(self, smtp_ssl):
        smtp = MagicMock()
        smtp_ssl.return_value.__enter__.return_value = smtp
        _send_gmail_verification("user@example.net", "https://firebase.test/action?oobCode=abc")
        args, kwargs = smtp_ssl.call_args
        self.assertEqual(args[:2], ("smtp.gmail.com", 465))
        self.assertEqual(kwargs["timeout"], 20)
        smtp.login.assert_called_once_with("owner@gmail.com", "abcdefghijklmnop")
        message = smtp.send_message.call_args.args[0]
        self.assertIn("Dautu", message["From"])
        self.assertIn("owner@gmail.com", message["From"])
        self.assertEqual(message["To"], "user@example.net")
        self.assertIn("https://firebase.test/action?oobCode=abc", message.get_body().get_content())

    @patch.dict("os.environ", {}, clear=True)
    def test_requires_gmail_username_and_app_password(self):
        with self.assertRaises(RuntimeError):
            _send_gmail_verification("user@example.net", "https://firebase.test/action")

    @patch.dict("os.environ", {"GMAIL_SMTP_USER":"owner@gmail.com","GMAIL_SMTP_APP_PASSWORD":"abcdefghijklmnop"}, clear=True)
    @patch("app.api.main.smtplib.SMTP_SSL")
    def test_smtp_authentication_failure_is_reported(self, smtp_ssl):
        import smtplib
        smtp = MagicMock()
        smtp.login.side_effect = smtplib.SMTPAuthenticationError(535, b"auth failed")
        smtp_ssl.return_value.__enter__.return_value = smtp
        with self.assertRaises(RuntimeError):
            _send_gmail_verification("user@example.net", "https://firebase.test/action")


if __name__ == "__main__":
    unittest.main()
