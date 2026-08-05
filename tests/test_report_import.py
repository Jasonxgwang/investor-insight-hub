"""自动导入与索引生成的行为测试。"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = PROJECT_ROOT / "tools" / "build_reports_index.py"


def load_report_module():
    """从脚本路径加载模块，便于直接测试命令行脚本中的公共函数。"""

    if not MODULE_PATH.exists():
        return None
    spec = importlib.util.spec_from_file_location("build_reports_index", MODULE_PATH)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


module = load_report_module()


class ParserTests(unittest.TestCase):
    """验证日期、标题和摘要的分层解析规则。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.entities = {}

    def tearDown(self):
        self.temp.cleanup()

    def write_html(self, name: str, head: str = "", body: str = "") -> Path:
        path = self.root / "Reports" / "2027" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"<!doctype html><html><head><meta charset='utf-8'>{head}</head>"
            f"<body>{body}</body></html>",
            encoding="utf-8",
        )
        return path

    def require_module(self):
        self.assertIsNotNone(module, "自动导入解析器尚未实现")
        return module

    def test_explicit_metadata_has_highest_priority(self):
        parser = self.require_module()
        path = self.write_html(
            "20270105_report.html",
            head=(
                '<meta name="report:date" content="2027-01-06">'
                '<meta name="report:title" content="显式标题">'
                '<meta name="report:summary" content="显式摘要。">'
                "<title>2027-01-05 后备标题</title>"
            ),
            body="<h1>页面标题</h1><p>正文摘要不应覆盖显式元数据。</p>",
        )

        report = parser.parse_report(path, self.root, self.entities, {})

        self.assertEqual(report["date"], "2027-01-06")
        self.assertEqual(report["title"], "显式标题")
        self.assertEqual(report["summary"], "显式摘要。")

    def test_filename_date_and_core_conclusion_are_fallbacks(self):
        parser = self.require_module()
        path = self.write_html(
            "20270105_市场日报.html",
            head="<title>2027-01-05 市场日报</title>",
            body=(
                "<h1>市场日报</h1><p>统计口径：近 24 小时。</p>"
                "<h2>核心结论</h2><p>半导体和有色金属观点出现明显分歧。</p>"
            ),
        )

        report = parser.parse_report(path, self.root, self.entities, {})

        self.assertEqual(report["date"], "2027-01-05")
        self.assertEqual(report["title"], "市场日报")
        self.assertEqual(report["summary"], "半导体和有色金属观点出现明显分歧。")

    def test_missing_date_is_blocking(self):
        parser = self.require_module()
        path = self.write_html(
            "market.html",
            head="<title>市场日报</title>",
            body="<h1>市场日报</h1><p>没有可用于归档的日期。</p>",
        )

        with self.assertRaisesRegex(parser.ReportParseError, "无法识别日期"):
            parser.parse_report(path, self.root, self.entities, {})


if __name__ == "__main__":
    unittest.main()
