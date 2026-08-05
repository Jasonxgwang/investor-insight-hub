"""自动导入与索引生成的行为测试。"""

from __future__ import annotations

import importlib.util
import json
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


class EntityExtractionTests(unittest.TestCase):
    """验证显式元数据、表格和受控词典能够合并识别实体。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.entities = {
            "influencers": [
                {"name": "飞翔芸", "aliases": ["飞翔芸"]},
                {"name": "伊夫圣洛朗", "aliases": ["伊夫圣洛朗"]},
                {
                    "name": "挖地瓜的超级鹿鼎公",
                    "aliases": ["挖地瓜的超级鹿鼎公", "挖地瓜"],
                },
            ],
            "stocks": [
                {"name": "紫金矿业", "code": "601899", "aliases": ["紫金矿业", "紫金"]},
                {"name": "腾讯控股", "code": "00700", "aliases": ["腾讯控股", "腾讯"]},
            ],
            "industries": [
                {"name": "有色金属", "keywords": ["有色金属", "黄金", "铜", "铝"]}
            ],
            "tags": [
                {"name": "风险提示", "keywords": ["风险提示", "谨慎", "回避"]}
            ],
            "sources": [
                {"name": "雪球", "keywords": ["雪球", "大 V 评论"]},
                {"name": "微博", "keywords": ["微博"]},
            ],
        }

    def tearDown(self):
        self.temp.cleanup()

    def parse(self, name: str, head: str, body: str):
        path = self.root / "Reports" / "2027" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"<!doctype html><html><head>{head}</head><body>{body}</body></html>",
            encoding="utf-8",
        )
        return module.parse_report(path, self.root, self.entities, {})

    def test_metadata_table_and_dictionary_entities_are_merged(self):
        report = self.parse(
            "20270105_entities.html",
            (
                '<meta name="report:stocks" content="紫金矿业|601899">'
                '<meta name="report:influencers" content="飞翔芸">'
                "<title>2027-01-05 实体识别日报</title>"
            ),
            (
                "<h1>实体识别日报</h1><table>"
                "<tr><th>标的</th><th>代码</th><th>作者</th></tr>"
                "<tr><td>腾讯控股</td><td>00700</td><td>伊夫圣洛朗</td></tr>"
                "</table><p>挖地瓜的超级鹿鼎公在微博继续关注有色金属并作出风险提示。</p>"
                "<p>雪球主贴也讨论了相关观点。</p>"
            ),
        )

        self.assertEqual(
            report["stocks"],
            [
                {"name": "紫金矿业", "code": "601899"},
                {"name": "腾讯控股", "code": "00700"},
            ],
        )
        self.assertEqual(
            report["influencers"],
            ["飞翔芸", "伊夫圣洛朗", "挖地瓜的超级鹿鼎公"],
        )
        self.assertEqual(report["industries"], ["有色金属"])
        self.assertEqual(report["tags"], ["风险提示"])
        self.assertEqual(report["sources"], ["雪球", "微博"])

    def test_css_numbers_are_not_stock_codes(self):
        report = self.parse(
            "20270105_css.html",
            "<title>2027-01-05 无标的日报</title><style>.x{color:#667085}</style>",
            "<h1>无标的日报</h1><p>统计数量为 344054 条，但没有具体证券标的。</p>",
        )

        self.assertEqual(report["stocks"], [])


class IndexGenerationTests(unittest.TestCase):
    """验证全量扫描的结果可重复、可覆盖且符合首页契约。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.entities_path = self.root / "data" / "entities.json"
        self.overrides_path = self.root / "data" / "report-overrides.json"
        self.entities_path.parent.mkdir(parents=True, exist_ok=True)
        self.entities_path.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "influencers": [],
                    "stocks": [],
                    "industries": [],
                    "tags": [],
                    "sources": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.overrides_path.write_text(
            json.dumps({"schemaVersion": 1, "reports": {}}, ensure_ascii=False),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp.cleanup()

    def write_report(self, relative_path: str, title: str) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"<!doctype html><html><head><title>{title}</title></head>"
            "<body><h1>日报</h1><p>本期记录市场观点和交易动作。</p></body></html>",
            encoding="utf-8",
        )
        return path

    def test_full_scan_is_sorted_stable_and_valid(self):
        self.write_report("Reports/2027/20270105_b.html", "2027-01-05 B 日报")
        self.write_report("Reports/2027/20270106_a.html", "2027-01-06 A 日报")

        first, first_warnings = module.build_index(
            self.root, self.entities_path, self.overrides_path
        )
        second, second_warnings = module.build_index(
            self.root, self.entities_path, self.overrides_path
        )

        self.assertEqual(first, second)
        self.assertEqual(first_warnings, second_warnings)
        self.assertEqual(
            [item["date"] for item in first["reports"]],
            ["2027-01-06", "2027-01-05"],
        )
        self.assertEqual(first["site"]["updatedAt"], "2027-01-06")
        module.validate_index(first, self.root)

    def test_override_preserves_curated_fields(self):
        path = self.write_report("Reports/2027/20270105_report.html", "2027-01-05 自动标题")
        self.overrides_path.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "reports": {
                        path.relative_to(self.root).as_posix(): {
                            "id": "curated-id",
                            "title": "人工标题",
                            "summary": "人工校准摘要。",
                            "tags": ["仓位变化"],
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        payload, _ = module.build_index(self.root, self.entities_path, self.overrides_path)
        report = payload["reports"][0]

        self.assertEqual(report["id"], "curated-id")
        self.assertEqual(report["title"], "人工标题")
        self.assertEqual(report["summary"], "人工校准摘要。")
        self.assertEqual(report["tags"], ["仓位变化"])


if __name__ == "__main__":
    unittest.main()
