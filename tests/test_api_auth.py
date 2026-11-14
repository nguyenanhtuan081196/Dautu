"""Unit tests for API authentication and subscription authorization."""
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
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


class FakeMongoUsers:
    def __init__(self):
        self.records = {}

    def find_one(self, query):
        return self.records.get(query["email"])

    def update_one(self, query, update, upsert=False):
        email = query["email"]
        if email not in self.records and upsert:
            self.records[email] = dict(update.get("$setOnInsert", {}))
        elif email in self.records and "$set" in update:
            self.records[email].update(update["$set"])


class RequireUserTests(unittest.TestCase):
    def setUp(self):
        main._rate_limit_state.clear()
        self.app = object()
        self.mongo = SimpleNamespace(users=FakeMongoUsers())
        self.mongo_patch = patch("app.api.main.get_database", return_value=self.mongo)
        self.mongo_patch.start()
        self.addCleanup(self.mongo_patch.stop)
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
                "created_by": main.ADMIN_EMAIL,
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
            FakeDocument({
                "role": "user",
                "expiresAt": expired,
                "created_by": main.ADMIN_EMAIL,
            })
        )
        with patch(
            "app.api.main.firestore.client", return_value=self.firebase
        ):
            with self.assertRaises(HTTPException) as error:
                main.require_user("Bearer token")
        self.assertEqual(error.exception.status_code, 401)

    def test_unregistered_firebase_account_is_provisioned_as_guest(self):
        self.firebase = FakeFirestore(FakeDocument())
        with patch("app.api.main.firestore.client", return_value=self.firebase):
            claims = main.require_guest("Bearer token")
        self.assertEqual(claims["app_role"], "guest")
        self.assertEqual(self.mongo.users.records["user@example.com"]["role"], "guest")
        with self.assertRaises(HTTPException) as error:
            main.require_user("Bearer token")
        self.assertEqual(error.exception.status_code, 403)

    def test_mongo_role_is_authoritative_after_legacy_migration(self):
        self.mongo.users.records["user@example.com"] = {
            "email": "user@example.com",
            "role": "guest",
            "status": "active",
            "expired_at": None,
        }
        claims = main.require_guest("Bearer token")
        self.assertEqual(claims["app_role"], "guest")
        with self.assertRaises(HTTPException) as error:
            main.require_user("Bearer token")
        self.assertEqual(error.exception.status_code, 403)

    def test_previously_migrated_unproven_user_is_downgraded_immediately(self):
        self.mongo.users.records["user@example.com"] = {
            "email": "user@example.com",
            "role": "user",
            "status": "active",
            "expired_at": datetime.now(timezone.utc) + timedelta(days=2),
            "created_source": "firestore_migration",
        }
        self.firebase = FakeFirestore(FakeDocument({
            "email": "user@example.com",
            "role": "user",
            "expiresAt": datetime.now(timezone.utc) + timedelta(days=2),
        }))
        with patch("app.api.main.firestore.client", return_value=self.firebase):
            claims = main.require_guest("Bearer token")
        account = self.mongo.users.records["user@example.com"]
        self.assertEqual(claims["app_role"], "guest")
        self.assertEqual(account["role"], "guest")
        self.assertEqual(account["created_source"], "firestore_untrusted_guest")
        self.assertIsNone(account["expired_at"])

    def test_admin_dependency_rejects_user_role(self):
        with self.assertRaises(HTTPException) as error:
            main.require_admin("Bearer token")
        self.assertEqual(error.exception.status_code, 403)

    def test_legacy_user_without_admin_provenance_is_downgraded_to_guest(self):
        self.firebase = FakeFirestore(FakeDocument({
            "email": "user@example.com",
            "role": "user",
            "expiresAt": datetime.now(timezone.utc) + timedelta(days=2),
        }))
        with patch("app.api.main.firestore.client", return_value=self.firebase):
            claims = main.require_guest("Bearer token")
        account = self.mongo.users.records["user@example.com"]
        self.assertEqual(claims["app_role"], "guest")
        self.assertEqual(account["role"], "guest")
        self.assertEqual(account["created_source"], "firestore_untrusted_guest")
        self.assertIsNone(account["expired_at"])

    def test_legacy_user_with_admin_provenance_is_migrated_as_user(self):
        claims = main.require_user("Bearer token")
        self.assertEqual(claims["app_role"], "user")
        self.assertEqual(
            self.mongo.users.records["user@example.com"]["created_source"],
            "firestore_admin_migration",
        )

    def test_existing_mongo_user_with_unverified_firebase_email_is_rejected(self):
        self.mongo.users.records["user@example.com"] = {
            "email": "user@example.com",
            "role": "user",
            "status": "active",
            "expired_at": datetime.now(timezone.utc) + timedelta(days=2),
        }
        with patch(
            "app.api.main.firebase_auth.verify_id_token",
            return_value={**self.valid_claims, "email_verified": False},
        ):
            with self.assertRaises(HTTPException) as error:
                main.require_user("Bearer token")
        self.assertEqual(error.exception.status_code, 403)
        self.assertEqual(error.exception.detail, "Email verification is required")

    def test_locked_mongo_account_is_rejected(self):
        self.mongo.users.records["user@example.com"] = {
            "email": "user@example.com",
            "role": "user",
            "status": "locked",
            "expired_at": datetime.now(timezone.utc) + timedelta(days=2),
        }
        with self.assertRaises(HTTPException) as error:
            main.require_guest("Bearer token")
        self.assertEqual(error.exception.status_code, 403)

    def test_mongo_account_registry_failure_fails_closed(self):
        with patch("app.api.main.get_database", side_effect=ConnectionError("Atlas down")):
            with self.assertRaises(HTTPException) as error:
                main.require_guest("Bearer token")
        self.assertEqual(error.exception.status_code, 503)

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

    def test_data_api_routes_require_the_correct_role_dependency(self):
        basic_paths = {
            "/api/status",
            "/api/stocks",
            "/api/stocks/{symbol}",
        }
        data_routes = [
            route for route in main.app.routes
            if getattr(route, "path", "").startswith("/api/")
            and getattr(route, "path", "") != "/api/auth/send-verification"
        ]
        self.assertGreater(len(data_routes), 0)
        for route in data_routes:
            with self.subTest(path=route.path):
                dependency_names = {
                    getattr(dep.call, "__name__", None)
                    for dep in route.dependant.dependencies
                }
                if route.path in basic_paths or route.path == "/api/auth/me":
                    expected = "require_guest"
                elif route.path.startswith("/api/admin/"):
                    expected = "require_admin"
                else:
                    expected = "require_user"
                self.assertIn(expected, dependency_names)


    def test_simulation_routes_are_authenticated(self):
        routes = [
            route for route in main.app.routes
            if getattr(route, "path", "").startswith("/api/simulations")
        ]
        self.assertEqual(
            {route.path for route in routes},
            {"/api/simulations", "/api/simulations/{symbol}"},
        )
        for route in routes:
            dependency_names = {
                getattr(dep.call, "__name__", None)
                for dep in route.dependant.dependencies
            }
            self.assertIn("require_user", dependency_names)

    def test_simulation_projection_is_allowlisted(self):
        self.assertIn("annual_rate_percent", main.SIMULATION_RESPONSE_FIELDS)
        self.assertIn("start_price_mean", main.SIMULATION_RESPONSE_FIELDS)
        self.assertNotIn("provider_payload", main.SIMULATION_RESPONSE_FIELDS)
        self.assertNotIn("run_id", main.SIMULATION_RESPONSE_FIELDS)

    def test_symbol_path_parameters_are_constrained(self):
        symbol_routes = [
            route for route in main.app.routes
            if "{symbol}" in getattr(route, "path", "")
        ]
        self.assertEqual(len(symbol_routes), 6)
        for route in symbol_routes:
            with self.subTest(path=route.path):
                parameter = next(
                    p for p in route.dependant.path_params if p.name == "symbol"
                )
                metadata = repr(parameter.field_info.metadata)
                self.assertIn("min_length=1", metadata)
                self.assertIn("max_length=20", metadata)
                self.assertIn("pattern=", metadata)

    def test_authenticated_user_rate_limit_returns_retry_after(self):
        with patch.object(main, "RATE_LIMIT_MAX_REQUESTS", 2):
            main._enforce_user_rate_limit("uid-rate-test", now=100.0)
            main._enforce_user_rate_limit("uid-rate-test", now=101.0)
            with self.assertRaises(HTTPException) as error:
                main._enforce_user_rate_limit("uid-rate-test", now=102.0)
            self.assertEqual(error.exception.status_code, 429)
            self.assertIn("Retry-After", error.exception.headers)
            main._enforce_user_rate_limit("uid-rate-test", now=161.0)

    def test_allowed_hosts_uses_render_hostname_and_explicit_custom_hosts(self):
        with patch.dict(
            "os.environ",
            {
                "API_ALLOWED_HOSTS": "api.example.com, www.example.com",
                "RENDER_EXTERNAL_HOSTNAME": "dautu-api.onrender.com",
            },
            clear=True,
        ):
            self.assertEqual(
                main._allowed_hosts(),
                ["api.example.com", "www.example.com", "dautu-api.onrender.com"],
            )

    def test_response_field_allowlists_exclude_unreviewed_document_fields(self):
        self.assertIn("company_name", main.STOCK_RESPONSE_FIELDS)
        self.assertIn("ai_recommendation", main.STOCK_RESPONSE_FIELDS)
        self.assertNotIn("raw_payload", main.STOCK_RESPONSE_FIELDS)
        self.assertNotIn("run_id", main.SCREENER_RESPONSE_FIELDS)
        self.assertNotIn("provider_response", main.AI_RESPONSE_FIELDS)


if __name__ == "__main__":
    unittest.main()
