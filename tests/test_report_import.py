"""自动导入与索引生成的行为测试。"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
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

    def test_title_removes_parentheses_left_empty_by_date(self):
        parser = self.require_module()
        path = self.write_html(
            "雪球微博近24h投资观点总结_20260803.html",
            head="<title>雪球+微博近24小时投资观点总结（2026-08-03）</title>",
            body="<h1>投资观点总结</h1><p>本期记录多空观点和交易动作。</p>",
        )

        report = parser.parse_report(path, self.root, self.entities, {})

        self.assertEqual(report["title"], "雪球+微博近24小时投资观点总结")


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


    def test_generated_index_assigns_stable_report_types(self):
        daily = self.write_report(
            "Reports/2027/20270107_daily.html",
            "2027-01-07 普通日报",
        )
        trend = self.write_report(
            "Reports/2027/20270106_trend.html",
            "2027-01-06 原始趋势标题",
        )
        portfolio = self.write_report(
            "Reports/2027/20270105_portfolio.html",
            "2027-01-05 原始组合标题",
        )

        self.overrides_path.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "reports": {
                        trend.relative_to(self.root).as_posix(): {
                            "title": "全站观点趋势专题：2027年1月1日—1月6日",
                        },
                        portfolio.relative_to(self.root).as_posix(): {
                            "title": "人工组合标题",
                            "type": "portfolio",
                        },
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        payload, _ = module.build_index(
            self.root,
            self.entities_path,
            self.overrides_path,
        )

        reports = {
            item["file"]: item
            for item in payload["reports"]
        }

        self.assertEqual(
            reports[daily.relative_to(self.root).as_posix()].get("type"),
            "daily",
        )
        self.assertEqual(
            reports[trend.relative_to(self.root).as_posix()].get("type"),
            "trend",
        )
        self.assertEqual(
            reports[portfolio.relative_to(self.root).as_posix()].get("type"),
            "portfolio",
        )



class InboxImportTests(unittest.TestCase):
    """验证待导入文件只在解析成功且目标无冲突时移动。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        data = self.root / "data"
        data.mkdir(parents=True)
        (data / "entities.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "influencers": [],
                    "stocks": [],
                    "industries": [],
                    "tags": [],
                    "sources": [],
                }
            ),
            encoding="utf-8",
        )
        (data / "report-overrides.json").write_text(
            json.dumps({"schemaVersion": 1, "reports": {}}),
            encoding="utf-8",
        )
        (self.root / "Inbox").mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def write_inbox(self, name: str, html: str) -> Path:
        path = self.root / "Inbox" / name
        path.write_text(html, encoding="utf-8")
        return path

    def test_import_moves_valid_html_to_year_directory(self):
        source = self.write_inbox(
            "20270105_日报.html",
            "<title>2027-01-05 日报</title><h2>核心结论</h2><p>市场维持震荡。</p>",
        )

        result = module.import_inbox(self.root)

        self.assertFalse(source.exists())
        self.assertTrue((self.root / "Reports" / "2027" / source.name).exists())
        self.assertEqual(len(result.imported), 1)
        self.assertEqual(result.failed, [])

    def test_invalid_file_remains_in_inbox(self):
        source = self.write_inbox("no-date.html", "<title>无日期日报</title>")

        result = module.import_inbox(self.root)

        self.assertTrue(source.exists())
        self.assertEqual(len(result.failed), 1)

    def test_existing_destination_is_never_overwritten(self):
        destination = self.root / "Reports" / "2027" / "20270105_日报.html"
        destination.parent.mkdir(parents=True)
        destination.write_text("<title>2027-01-05 已归档版本</title>", encoding="utf-8")
        source = self.write_inbox(
            destination.name,
            "<title>2027-01-05 冲突版本</title><p>不同内容。</p>",
        )

        result = module.import_inbox(self.root)

        self.assertTrue(source.exists())
        self.assertEqual(len(result.failed), 1)
        self.assertIn("冲突", result.failed[0])
        self.assertIn("已归档版本", destination.read_text(encoding="utf-8"))

    def test_same_content_with_different_names_imports_only_one_file(self):
        html = "<title>2027-01-05 日报</title><p>同一份日报内容。</p>"
        duplicate = self.write_inbox("20270105_日报(1).html", html)
        canonical = self.write_inbox("20270105_日报.html", html)

        result = module.import_inbox(self.root)

        self.assertEqual(len(result.imported), 1)
        self.assertTrue((self.root / "Reports/2027" / canonical.name).exists())
        self.assertTrue(duplicate.exists())
        self.assertEqual(len(result.skipped), 1)
        self.assertIn("重复内容", result.skipped[0])

    def test_content_already_archived_is_skipped_even_when_filename_differs(self):
        html = "<title>2027-01-05 日报</title><p>已经归档的日报内容。</p>"
        archived = self.root / "Reports/2027/original.html"
        archived.parent.mkdir(parents=True)
        archived.write_text(html, encoding="utf-8")
        source = self.write_inbox("20270105_另一个文件名.html", html)

        result = module.import_inbox(self.root)

        self.assertEqual(result.imported, [])
        self.assertTrue(source.exists())
        self.assertEqual(len(result.skipped), 1)
        self.assertIn("归档中已存在相同内容", result.skipped[0])


class PowerShellEntrypointTests(unittest.TestCase):
    """防止 Windows PowerShell 5 再次误读中文脚本编码。"""

    def test_entrypoint_uses_utf8_bom(self):
        script = PROJECT_ROOT / "import_reports.ps1"
        self.assertTrue(
            script.read_bytes().startswith(b"\xef\xbb\xbf"),
            "含中文的 PowerShell 5 脚本必须使用 UTF-8 BOM",
        )

    def test_entrypoint_configures_utf8_console_output(self):
        script = (PROJECT_ROOT / "import_reports.ps1").read_text(encoding="utf-8-sig")
        self.assertIn('$env:PYTHONIOENCODING = "utf-8"', script)
        self.assertIn("[Console]::OutputEncoding", script)

    def test_inbox_entrypoint_runs_parent_script_with_publish(self):
        inbox_entrypoint = PROJECT_ROOT / "Inbox" / "import_reports.ps1"
        self.assertTrue(
            inbox_entrypoint.exists(),
            "从 Inbox 打开 PowerShell 时也应存在可运行的一键入口",
        )
        powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
        if powershell is None:
            self.skipTest("当前环境没有可用于入口集成测试的 PowerShell")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inbox = root / "Inbox"
            inbox.mkdir()
            (root / "import_reports.ps1").write_text(
                'param([switch]$Publish)\n'
                'if ($Publish) { Write-Output "ROOT_PUBLISH" } '
                'else { Write-Output "ROOT_LOCAL" }\n',
                encoding="utf-8-sig",
            )
            (inbox / "import_reports.ps1").write_bytes(inbox_entrypoint.read_bytes())

            result = subprocess.run(
                [
                    powershell,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(inbox / "import_reports.ps1"),
                    "-Publish",
                ],
                cwd=inbox,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ROOT_PUBLISH", result.stdout)

    def test_personal_inbox_notes_do_not_dirty_git_worktree(self):
        result = subprocess.run(
            ["git", "check-ignore", "--quiet", "Inbox/说明.txt"],
            cwd=PROJECT_ROOT,
            check=False,
        )

        self.assertEqual(result.returncode, 0)


class EndToEndImportTests(unittest.TestCase):
    """在临时目录验证从 Inbox 到静态索引的完整数据流。"""

    def test_import_build_and_rebuild_are_complete_and_stable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / "data"
            inbox = root / "Inbox"
            data.mkdir()
            inbox.mkdir()
            entities = {
                "schemaVersion": 1,
                "influencers": [{"name": "飞翔芸", "aliases": ["飞翔芸"]}],
                "stocks": [
                    {"name": "紫金矿业", "code": "601899", "aliases": ["紫金矿业"]}
                ],
                "industries": [
                    {"name": "有色金属", "keywords": ["有色金属", "黄金"]}
                ],
                "tags": [{"name": "仓位变化", "keywords": ["仓位变化", "加仓"]}],
                "sources": [{"name": "雪球", "keywords": ["雪球"]}],
            }
            entities_path = data / "entities.json"
            overrides_path = data / "report-overrides.json"
            entities_path.write_text(json.dumps(entities, ensure_ascii=False), encoding="utf-8")
            overrides_path.write_text(
                json.dumps({"schemaVersion": 1, "reports": {}}, ensure_ascii=False),
                encoding="utf-8",
            )
            source = inbox / "20270105_自动导入验收.html"
            source.write_text(
                """<!doctype html><html><head>
                <title>2027-01-05 自动导入验收</title>
                <meta name="report:summary" content="紫金矿业获得关注并出现加仓。">
                <meta name="report:stocks" content="紫金矿业|601899">
                <meta name="report:influencers" content="飞翔芸">
                </head><body><h1>自动导入验收</h1>
                <p>雪球讨论有色金属，记录仓位变化。</p></body></html>""",
                encoding="utf-8",
            )

            import_result = module.import_inbox(root)
            first, _ = module.build_index(root, entities_path, overrides_path)
            first_serialized = module.serialize_index(first)
            second, _ = module.build_index(root, entities_path, overrides_path)

            self.assertEqual(len(import_result.imported), 1)
            self.assertTrue((root / "Reports/2027/20270105_自动导入验收.html").exists())
            self.assertEqual(first_serialized, module.serialize_index(second))
            report = first["reports"][0]
            self.assertEqual(report["date"], "2027-01-05")
            self.assertEqual(report["title"], "自动导入验收")
            self.assertIn("紫金矿业", report["summary"])
            self.assertEqual(report["stocks"], [{"name": "紫金矿业", "code": "601899"}])
            self.assertEqual(report["influencers"], ["飞翔芸"])
            self.assertEqual(report["industries"], ["有色金属"])
            self.assertEqual(report["tags"], ["仓位变化"])
            self.assertEqual(report["sources"], ["雪球"])


class RepositoryHygieneTests(unittest.TestCase):
    """确保每日测试产生的缓存不会阻塞下一次自动发布。"""

    def test_august_30_portfolio_report_is_curated_as_portfolio(self):
        payload, _ = module.build_index(
            PROJECT_ROOT,
            PROJECT_ROOT / "data" / "entities.json",
            PROJECT_ROOT / "data" / "report-overrides.json",
        )
        reports = {item["file"]: item for item in payload["reports"]}
        report = reports[
            "Reports/2026/20260830_关注大V持仓与看好度分析.html"
        ]

        self.assertEqual(report["type"], "portfolio")

    def test_python_cache_is_ignored(self):
        ignore_rules = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("__pycache__/", ignore_rules)
        self.assertIn("*.py[cod]", ignore_rules)


if __name__ == "__main__":
    unittest.main()
