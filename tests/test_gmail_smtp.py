"""Unit tests for Gmail SMTP verification email delivery."""
import unittest
from unittest.mock import MagicMock, patch
from app.api.main import _send_gmail_verification


class GmailVerificationTests(unittest.TestCase):
    @patch.dict("os.environ", {"GMAIL_SMTP_USER":"owner@gmail.com","GMAIL_SMTP_APP_PASSWORD":"abcd efgh ijkl mnop","GMAIL_FROM_NAME":"Dautu"}, clear=True)
    @patch("app.api.main.smtplib.SMTP_SSL")
    def test_sends_firebase_link_through_gmail_smtp(self, smtp_ssl):
        smtp = MagicMock()
        smtp.send_message.return_value = {}
        smtp_ssl.return_value.__enter__.return_value = smtp
        smtp.send_message.return_value = {}
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


    @patch("app.api.main.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("142.250.0.1", 465))])
    @patch("app.api.main.socket.create_connection")
    @patch("app.api.main.ssl.create_default_context")
    def test_connectivity_probe_checks_dns_tcp_tls_without_auth_or_email(self, ssl_context, create_connection, getaddrinfo):
        from app.api.main import _probe_gmail_smtp_connectivity
        tls_socket = MagicMock()
        tls_socket.__enter__.return_value = tls_socket
        tls_socket.version.return_value = "TLSv1.3"
        tls_socket.cipher.return_value = ("TLS_AES_256_GCM_SHA384", "TLSv1.3", 256)
        ssl_context.return_value.wrap_socket.return_value = tls_socket
        create_connection.return_value = MagicMock()
        result = _probe_gmail_smtp_connectivity()
        self.assertTrue(result["dns"]["ok"])
        self.assertTrue(result["tcp"]["ok"])
        self.assertTrue(result["tls"]["ok"])
        self.assertFalse(result["smtp_authenticated"])
        self.assertFalse(result["email_sent"])
        create_connection.assert_called_once()

    @patch("app.api.main.socket.getaddrinfo", side_effect=TimeoutError("DNS timed out"))
    def test_connectivity_probe_reports_dns_failure_without_tcp(self, getaddrinfo):
        from app.api.main import _probe_gmail_smtp_connectivity
        result = _probe_gmail_smtp_connectivity()
        self.assertFalse(result["dns"]["ok"])
        self.assertEqual(result["dns"]["error_type"], "TimeoutError")
        self.assertFalse(result["tcp"]["ok"])
        self.assertFalse(result["tls"]["ok"])

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
