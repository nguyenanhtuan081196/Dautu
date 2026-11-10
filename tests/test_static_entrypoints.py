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


if __name__ == "__main__":
    unittest.main()
