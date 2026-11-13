"""Tests for the standardized FastAPI application lifecycle."""
import unittest
from unittest.mock import patch

from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.core.application import create_app


class ApplicationFactoryTests(unittest.TestCase):
    def test_factory_registers_router_and_runs_lifecycle_hooks(self):
        router = APIRouter()

        @router.get("/factory-check")
        def factory_check():
            return {"ok": True}

        started = []
        with (
            patch("app.core.application.configure_logging") as configure_logging,
            patch("app.core.application.close_client") as close_client,
        ):
            application = create_app(
                router=router,
                startup_handler=lambda: started.append(True),
                title="Factory Test API",
            )
            with TestClient(application) as client:
                response = client.get("/factory-check")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})
        self.assertEqual(started, [True])
        configure_logging.assert_called_once_with()
        close_client.assert_called_once_with()
        self.assertIsNone(application.docs_url)
        self.assertIsNone(application.redoc_url)
        self.assertIsNone(application.openapi_url)

    def test_factory_closes_database_even_when_startup_fails(self):
        router = APIRouter()
        with patch("app.core.application.close_client") as close_client:
            application = create_app(
                router=router,
                startup_handler=lambda: (_ for _ in ()).throw(RuntimeError("startup failed")),
            )
            with self.assertRaisesRegex(RuntimeError, "startup failed"):
                with TestClient(application):
                    pass
        close_client.assert_called_once_with()

    def test_factory_installs_security_headers(self):
        router = APIRouter()

        @router.get("/headers")
        def headers():
            return {"ok": True}

        application = create_app(router=router)
        with patch("app.core.application.close_client"):
            with TestClient(application) as client:
                response = client.get("/headers")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")


if __name__ == "__main__":
    unittest.main()
