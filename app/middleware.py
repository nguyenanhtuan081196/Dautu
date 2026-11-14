"""Shared HTTP middleware setup for the Dautu API."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import get_allowed_hosts, get_allowed_origins


async def security_headers(request, call_next):
    """Apply the existing Dautu response security headers."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Cache-Control", "no-store")
    response.headers.setdefault(
        "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
    )
    return response


def install_middleware(app: FastAPI) -> None:
    """Install host validation, restricted CORS, and response security headers."""
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=get_allowed_hosts())

    origins = get_allowed_origins()
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=False,
            # Authorization triggers a preflight. Cache-Control is also sent by
            # the frontend for no-cache GETs and must be explicitly permitted.
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "Cache-Control"],
        )

    app.middleware("http")(security_headers)
