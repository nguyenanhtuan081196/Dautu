"""Regression tests enforcing Atlas-only runtime data processing."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


class RuntimeWorkflowSafetyTests(unittest.TestCase):
    def test_legacy_python_renderer_is_removed(self):
        self.assertFalse((ROOT / "render_ui.py").exists())

    def test_github_actions_no_longer_runs_operational_data_jobs(self):
        retired = (
            "screener.yml",
            "quant_screener.yml",
            "ai_analysis.yml",
        )
        for name in retired:
            with self.subTest(workflow=name):
                self.assertFalse((WORKFLOWS / name).exists())

    def test_remaining_workflows_do_not_commit_runtime_datasets(self):
        forbidden = (
            "git add data.json",
            "git add screener_results.json",
            "git add symbol_sim_rates.json",
            "git add quarterly_mean_details.json",
            "git add index.html",
            "python render_ui.py",
        )
        for path in WORKFLOWS.glob("*.yml"):
            content = path.read_text(encoding="utf-8")
            for phrase in forbidden:
                with self.subTest(workflow=path.name, phrase=phrase):
                    self.assertNotIn(phrase, content)

    def test_no_workflow_references_the_retired_renderer(self):
        references = [
            path.relative_to(ROOT).as_posix()
            for path in WORKFLOWS.glob("*.yml")
            if "render_ui.py" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(references, [])


if __name__ == "__main__":
    unittest.main()
