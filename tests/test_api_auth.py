"""Unit tests for API authentication and subscription authorization."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import HTTPException

from app.api import main


class FakeDocument:
    def __init__(self, data=None):
        self.exists = data is not None
        self._data = data

    def to_dict(self):
        return self._data


class FakeCollection:
    def __init__(self, document):
        self._document = document
        self.requested_email = None

    def document(self, email):
        self.requested_email = email
        return self

    def get(self):
        return self._document


class FakeFirestore:
    def __init__(self, document):
        self.collection_ref = FakeCollection(document)

    def collection(self, name):
        if name != "allowed_users":
            raise AssertionError(f"Unexpected collection: {name}")
        return self.collection_ref


class RequireUserTests(unittest.TestCase):
    def setUp(self):
        self.app = object()
        self.valid_claims = {
            "uid": "uid-123",
            "email": "user@example.com",
            "email_verified": True,
        }
        self.firebase = FakeFirestore(
            FakeDocument({
                "email": "user@example.com",
                "role": "user",
                "expiresAt": datetime.now(timezone.utc) + timedelta(days=2),
            })
        )
        self.app_patch = patch("app.api.main._firebase_app", return_value=self.app)
        self.verify_patch = patch(
            "app.api.main.firebase_auth.verify_id_token",
            return_value=self.valid_claims.copy(),
        )
        self.firestore_patch = patch(
            "app.api.main.firestore.client", return_value=self.firebase
        )
        self.app_patch.start()
        self.verify_patch.start()
        self.firestore_patch.start()
        self.addCleanup(self.app_patch.stop)
        self.addCleanup(self.verify_patch.stop)
        self.addCleanup(self.firestore_patch.stop)

    def test_missing_bearer_token_is_rejected(self):
        with self.assertRaises(HTTPException) as error:
            main.require_user(None)
        self.assertEqual(error.exception.status_code, 401)

    def test_unverified_email_is_rejected(self):
        with patch(
            "app.api.main.firebase_auth.verify_id_token",
            return_value={**self.valid_claims, "email_verified": False},
        ):
            with self.assertRaises(HTTPException) as error:
                main.require_user("Bearer token")
        self.assertEqual(error.exception.status_code, 403)

    def test_missing_membership_is_rejected(self):
        self.firebase = FakeFirestore(FakeDocument())
        with patch(
            "app.api.main.firestore.client", return_value=self.firebase
        ):
            with self.assertRaises(HTTPException) as error:
                main.require_user("Bearer token")
        self.assertEqual(error.exception.status_code, 403)

    def test_expired_subscription_is_rejected(self):
        expired = datetime.now(timezone.utc) - timedelta(seconds=1)
        self.firebase = FakeFirestore(
            FakeDocument({"role": "user", "expiresAt": expired})
        )
        with patch(
            "app.api.main.firestore.client", return_value=self.firebase
        ):
            with self.assertRaises(HTTPException) as error:
                main.require_user("Bearer token")
        self.assertEqual(error.exception.status_code, 403)

    def test_active_user_is_authorized_and_email_is_normalized(self):
        claims = main.require_user("Bearer token")
        self.assertEqual(claims["app_role"], "user")
        self.assertEqual(self.firebase.collection_ref.requested_email, "user@example.com")

    def test_fixed_admin_is_authorized_without_expiry(self):
        admin_email = main.ADMIN_EMAIL
        self.firebase = FakeFirestore(FakeDocument({"role": "admin"}))
        with patch(
            "app.api.main.firebase_auth.verify_id_token",
            return_value={
                "uid": "admin-uid",
                "email": admin_email,
                "email_verified": True,
            },
        ), patch(
            "app.api.main.firestore.client", return_value=self.firebase
        ):
            claims = main.require_user("Bearer token")
        self.assertEqual(claims["app_role"], "admin")

    def test_admin_role_for_another_email_is_rejected(self):
        self.firebase = FakeFirestore(FakeDocument({"role": "admin"}))
        with patch(
            "app.api.main.firebase_auth.verify_id_token",
            return_value={
                "uid": "other-admin",
                "email": "other@example.com",
                "email_verified": True,
            },
        ), patch(
            "app.api.main.firestore.client", return_value=self.firebase
        ):
            with self.assertRaises(HTTPException) as error:
                main.require_user("Bearer token")
        self.assertEqual(error.exception.status_code, 403)

    def test_every_data_api_route_requires_user(self):
        data_routes = [
            route for route in main.app.routes
            if getattr(route, "path", "").startswith("/api/")
        ]
        self.assertGreater(len(data_routes), 0)
        for route in data_routes:
            with self.subTest(path=route.path):
                dependency_names = {
                    getattr(dep.call, "__name__", None)
                    for dep in route.dependant.dependencies
                }
                self.assertIn("require_user", dependency_names)

    def test_symbol_path_parameters_are_constrained(self):
        symbol_routes = [
            route for route in main.app.routes
            if "{symbol}" in getattr(route, "path", "")
        ]
        self.assertEqual(len(symbol_routes), 4)
        for route in symbol_routes:
            with self.subTest(path=route.path):
                parameter = next(
                    p for p in route.dependant.path_params if p.name == "symbol"
                )
                metadata = repr(parameter.field_info.metadata)
                self.assertIn("min_length=1", metadata)
                self.assertIn("max_length=20", metadata)
                self.assertIn("pattern=", metadata)


if __name__ == "__main__":
    unittest.main()
