from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class StaticEntryPointTests(unittest.TestCase):
    def test_legacy_login_redirects_to_canonical_app(self):
        source=(ROOT/"login.html").read_text(encoding="utf-8")
        self.assertIn("window.location.replace('./index.html'",source)

    def test_admin_entrypoint_uses_backend_only_and_firebase_auth(self):
        admin=(ROOT/"admin.html").read_text(encoding="utf-8")
        self.assertIn("/api/admin/users",admin)
        self.assertIn("/api/auth/me",admin)
        self.assertIn("Authorization",admin)
        self.assertNotIn("firebase.firestore",admin)
        self.assertNotIn("allowed_users",admin)
        self.assertNotIn("MONGODB_URI",admin)

    def test_main_frontend_does_not_provision_memberships_in_firestore(self):
        app=(ROOT/"index.html").read_text(encoding="utf-8")
        self.assertIn("apiFetch('/api/auth/me')",app)
        self.assertIn("window.location.href = './admin.html'",app)
        self.assertNotIn("allowed_users",app)
        self.assertNotIn("firebase.firestore",app)
        self.assertNotIn("expireDate.setDate(expireDate.getDate() + 7)",app)

    def test_pages_workflow_publishes_allowlisted_frontend_assets(self):
        workflow=(ROOT/".github"/"workflows"/"pages.yml").read_text(encoding="utf-8")
        self.assertIn("cp index.html login.html admin.html lightweight-charts.js CNAME site/",workflow)
        self.assertIn('"admin.html"',workflow)
        self.assertNotIn("cp data.json",workflow)
        self.assertNotIn("cp screener_results.json",workflow)
        self.assertNotIn("cp -r history",workflow)
        self.assertNotIn("cp -r bctc_data",workflow)

    def test_private_data_remains_backend_api_only(self):
        app=(ROOT/"index.html").read_text(encoding="utf-8")
        self.assertIn("async function apiFetch(path)",app)
        self.assertIn("Authorization",app)
        self.assertIn("apiFetch('/api/screener?limit=500')",app)
        self.assertIn("apiFetch('/api/stocks?limit=500')",app)
        self.assertNotIn("fetch('data.json",app)

if __name__=="__main__":
    unittest.main()
