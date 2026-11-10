from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class StaticEntryPointTests(unittest.TestCase):
    def test_legacy_login_redirects_to_canonical_app(self):
        legacy_login = (ROOT / "login.html").read_text(encoding="utf-8")
        self.assertIn("window.location.replace('./index.html'", legacy_login)
        self.assertIn('url=./index.html', legacy_login)
        self.assertNotIn("firebase.initializeApp", legacy_login)
        self.assertNotIn("hoc-tieng-trung-64b8d", legacy_login)

    def test_admin_account_actions_follow_firestore_rules(self):
        app = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("function renderAdminUsers()", app)
        self.assertIn("function extendUser(email)", app)
        self.assertIn("function suspendUser(email)", app)
        self.assertIn("firebase.firestore.Timestamp.fromDate(currentExpire)", app)
        self.assertIn("firebase.firestore.Timestamp.fromDate(new Date(0))", app)
        self.assertIn("currentUser.emailVerified", app)
        self.assertNotIn("docRef.delete()", app)
        self.assertNotIn("function deleteUser(email)", app)


if __name__ == "__main__":
    unittest.main()
