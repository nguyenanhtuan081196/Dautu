from google.auth.exceptions import RefreshError

from app.email.gmail import safe_oauth_error_code


def test_safe_oauth_error_code_reads_whitelisted_response_code():
    error = RefreshError(
        "OAuth refresh failed",
        {"error": "invalid_grant", "error_description": "sensitive response text"},
    )

    assert safe_oauth_error_code(error) == "invalid_grant"


def test_safe_oauth_error_code_does_not_return_untrusted_response_text():
    error = RefreshError(
        "OAuth refresh failed",
        {"error": "unexpected_value", "error_description": "do not log this"},
    )

    assert safe_oauth_error_code(error) == "unknown"


def test_safe_oauth_error_code_ignores_non_refresh_errors():
    error = RuntimeError("invalid_grant")

    assert safe_oauth_error_code(error) is None
