"""Gmail API transport for Firebase email-verification links."""
from __future__ import annotations

import base64
import html
import os
from email.message import EmailMessage
from email.utils import formataddr

from google.auth.transport.requests import Request
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
TOKEN_URI = "https://oauth2.googleapis.com/token"


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def send_verification_email(recipient: str, verification_link: str) -> str:
    """Send a Firebase-generated verification link using Gmail API over HTTPS.

    Credentials are created without an access token. google-auth refreshes the
    short-lived access token from the stored refresh token when the API request
    is executed; no SMTP connection or App Password is used.
    """
    client_id = _required_env("GOOGLE_CLIENT_ID")
    client_secret = _required_env("GOOGLE_CLIENT_SECRET")
    refresh_token = _required_env("GOOGLE_REFRESH_TOKEN")
    sender = _required_env("GMAIL_SENDER_EMAIL")
    from_name = os.getenv("GMAIL_FROM_NAME", "Dautu").strip() or "Dautu"

    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=TOKEN_URI,
        client_id=client_id,
        client_secret=client_secret,
        scopes=[GMAIL_SEND_SCOPE],
    )

    # Refresh explicitly for every send; never depend on a stale in-memory token.
    credentials.refresh(Request())

    safe_link = html.escape(verification_link, quote=True)
    message = EmailMessage()
    message["Subject"] = "Xác minh địa chỉ email cho Dautu"
    message["From"] = formataddr((from_name, sender))
    message["To"] = recipient
    message.set_content(
        "Chào bạn,\n\n"
        "Vui lòng mở liên kết sau để xác minh địa chỉ email và kích hoạt tài khoản Dautu:\n"
        f"{verification_link}\n\n"
        "Nếu bạn không thực hiện đăng ký, hãy bỏ qua email này.\n"
        "Đội ngũ Dautu"
    )
    message.add_alternative(
        "<!doctype html><html><body>"
        "<p>Chào bạn,</p>"
        "<p>Vui lòng nhấn nút bên dưới để xác minh địa chỉ email "
        "và kích hoạt tài khoản Dautu.</p>"
        f'<p><a href="{safe_link}" style="display:inline-block;padding:12px 20px;'
        'background:#059669;color:#fff;text-decoration:none;border-radius:8px">'
        "Xác minh email</a></p>"
        "<p>Nếu bạn không thực hiện đăng ký, hãy bỏ qua email này.</p>"
        "<p>Đội ngũ Dautu</p>"
        "</body></html>",
        subtype="html",
    )

    encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    gmail = build("gmail", "v1", credentials=credentials, cache_discovery=False)
    result = (
        gmail.users()
        .messages()
        .send(userId="me", body={"raw": encoded_message})
        .execute()
    )
    return str(result.get("id", ""))
