"""Environment configuration for the Dautu API infrastructure.

This module centralizes infrastructure settings only. Firebase membership,
business authorization, MongoDB repositories, and SMTP delivery remain owned
by the Dautu application.
"""
from __future__ import annotations

import os


def _csv_env(name: str, default: str = "") -> list[str]:
    return [part.strip() for part in os.getenv(name, default).split(",") if part.strip()]


def get_allowed_origins() -> list[str]:
    """Return explicitly configured browser origins; empty means CORS is off."""
    return _csv_env("CORS_ALLOWED_ORIGINS")


def get_allowed_hosts() -> list[str]:
    """Resolve host allow-list while preserving Render's injected hostname."""
    configured = _csv_env("API_ALLOWED_HOSTS")
    render_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
    if render_hostname:
        configured.append(render_hostname)
    # Local/test defaults only. Custom domains must be explicitly allow-listed.
    return list(dict.fromkeys(configured or ["localhost", "127.0.0.1", "testserver"]))
