"""GitHub Actions 自动索引工作流的静态契约测试。"""

from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "update-reports.yml"


class WorkflowConfigTests(unittest.TestCase):
    def test_workflow_rebuilds_tests_and_commits_index(self):
        self.assertTrue(WORKFLOW.exists(), "自动索引工作流尚未创建")
        text = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("Reports/**/*.html", text)
        self.assertIn("contents: write", text)
        self.assertIn("build_reports_index.py --root . --write", text)
        self.assertIn("python -m unittest discover", text)
        self.assertIn("node --test tests/site.test.mjs", text)
        self.assertIn("git diff --quiet -- reports.json", text)
        self.assertIn("git add reports.json", text)

    def test_workflow_does_not_retrigger_on_its_index_commit(self):
        self.assertTrue(WORKFLOW.exists(), "自动索引工作流尚未创建")
        text = WORKFLOW.read_text(encoding="utf-8")

        paths_block = text.split("paths:", 1)[1].split("permissions:", 1)[0]
        self.assertNotIn("reports.json", paths_block)


if __name__ == "__main__":
    unittest.main()
