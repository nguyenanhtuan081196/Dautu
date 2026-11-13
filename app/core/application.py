"""Reusable FastAPI application factory for Dautu infrastructure."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Callable

from fastapi import APIRouter, FastAPI

from app.core.logging import configure_logging
from app.database.mongo import close_client
from app.middleware import install_middleware

logger = logging.getLogger(__name__)


def create_app(
    *,
    router: APIRouter,
    startup_handler: Callable[[], None] | None = None,
    title: str = "Dautu API",
    version: str = "1.0.0",
) -> FastAPI:
    """Build the API consistently while leaving domain routes in their own router."""

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        configure_logging()
        logger.info("Starting %s", title)
        try:
            if startup_handler is not None:
                startup_handler()
            yield
        finally:
            # The client is lazy; close_client is a no-op if MongoDB was never used.
            close_client()
            logger.info("Stopped %s", title)

    application = FastAPI(
        title=title,
        version=version,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    install_middleware(application)
    # Keep concrete APIRoute objects visible on app.routes for existing
    # authorization/compatibility inspection and test tooling.
    application.router.routes.extend(router.routes)
    return application
