"""Regression tests preventing the retired Python renderer from replacing the app UI."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class LegacyRendererSafetyTests(unittest.TestCase):
    def test_legacy_renderer_is_removed(self):
        self.assertFalse((ROOT / "render_ui.py").exists())

    def test_screener_workflow_never_executes_or_stages_the_frontend(self):
        workflow = (ROOT / ".github" / "workflows" / "screener.yml").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("render_ui.py", workflow)
        self.assertNotIn("python render_ui", workflow)
        self.assertNotIn("git add index.html", workflow)
        self.assertIn("python simulator.py", workflow)
        self.assertIn("git add symbol_sim_rates.json quarterly_mean_details.json", workflow)

    def test_no_workflow_references_the_retired_renderer(self):
        workflows = ROOT / ".github" / "workflows"
        references = [
            path.relative_to(ROOT).as_posix()
            for path in workflows.glob("*.yml")
            if "render_ui.py" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(references, [])


if __name__ == "__main__":
    unittest.main()
