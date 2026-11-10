import json
import os
import unittest
from unittest.mock import patch

from render_ui import get_firebase_config


class FirebaseConfigTests(unittest.TestCase):
    def test_missing_config_fails_build(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "FIREBASE_CONFIG"):
                get_firebase_config()

    def test_invalid_json_fails_build(self):
        with patch.dict(os.environ, {"FIREBASE_CONFIG": "not-json"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "JSON"):
                get_firebase_config()

    def test_required_fields_are_enforced(self):
        config = {"apiKey": "public-key", "projectId": "project"}
        with patch.dict(os.environ, {"FIREBASE_CONFIG": json.dumps(config)}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "authDomain"):
                get_firebase_config()

    def test_valid_config_is_returned(self):
        config = {
            "apiKey": "public-key",
            "authDomain": "example.firebaseapp.com",
            "projectId": "example",
            "appId": "app-id",
        }
        with patch.dict(os.environ, {"FIREBASE_CONFIG": json.dumps(config)}, clear=True):
            self.assertEqual(get_firebase_config(), config)


if __name__ == "__main__":
    unittest.main()
