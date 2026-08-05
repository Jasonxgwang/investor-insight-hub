# Automatic Report Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic one-minute HTML import workflow that archives reports by year, generates `reports.json`, validates the static site, and keeps GitHub Pages synchronized automatically.

**Architecture:** A Python standard-library generator scans HTML before deployment and produces the existing static JSON contract. A PowerShell wrapper handles the local `Inbox/` workflow, while GitHub Actions rebuilds and validates the same index after pushes; the browser remains a pure static consumer of `reports.json`.

**Tech Stack:** Python 3 standard library, PowerShell 5+, HTML/CSS/JavaScript, Node.js built-in test runner, GitHub Actions, GitHub Pages.

## Global Constraints

- Keep the deployed site pure static with no database, application server, runtime API, external AI service, or paid dependency.
- Use `Reports/<year>/` with an uppercase `R`; all published paths must match GitHub Pages case sensitivity.
- The homepage must continue to load only `reports.json`, never scan or download report bodies at runtime.
- Index output must be UTF-8, deterministic, validated, and atomically replaced only after successful generation.
- Do not write Cookie values, credentials, private API addresses, or source-post body content into `reports.json` or logs.
- Preserve the three existing reports and their curated metadata through `data/report-overrides.json`.
- Keep existing search support for stock code, stock name, influencer, date, tag, industry, title, and summary.
- Add detailed Chinese comments around parsing rules, maintenance entrypoints, and extension interfaces.
- Local import failure leaves the source HTML in `Inbox/` and does not replace the last valid index.

## File Map

- Create `tools/build_reports_index.py`: HTML parsing, entity extraction, index validation, deterministic JSON generation, inbox import, and CLI.
- Create `data/entities.json`: controlled dictionaries for influencers, stocks, industries, tags, and sources.
- Create `data/report-overrides.json`: curated overrides for the three existing reports.
- Create `tests/test_report_import.py`: isolated parser, importer, index, and stability tests.
- Create `import_reports.ps1`: one-command local import, validation, optional commit, and push.
- Create `Inbox/README.md`: drop-folder instructions while excluding daily HTML from Git.
- Create `.github/workflows/update-reports.yml`: serverless pre-deployment index rebuild and verification.
- Modify `.gitignore`: ignore `Inbox/*.html` but keep its instructions.
- Rename `reports/` to `Reports/` and modify `reports.json`: case-correct archive and generated index paths.
- Modify `tests/site.test.mjs`: generated index expectations and uppercase report paths.
- Modify `README.md`: one-minute maintenance flow, parser metadata contract, failure recovery, and extension notes.

---

### Task 1: HTML metadata parser

**Files:**
- Create: `tools/build_reports_index.py`
- Create: `tests/test_report_import.py`

**Interfaces:**
- Produces: `extract_document(path: Path) -> ParsedDocument`
- Produces: `extract_date(document: ParsedDocument, path: Path) -> str`
- Produces: `extract_title(document: ParsedDocument, path: Path, date: str) -> str`
- Produces: `extract_summary(document: ParsedDocument) -> tuple[str, list[str]]`
- Produces: `parse_report(path: Path, root: Path, entities: dict, overrides: dict) -> dict`
- `ParsedDocument` contains `title`, `headings`, `paragraphs`, `lists`, `tables`, `meta`, and normalized visible text.

- [ ] **Step 1: Write failing parser tests**

```python
class ParserTests(unittest.TestCase):
    def test_explicit_metadata_has_highest_priority(self):
        path = self.write_html(
            "20270105_report.html",
            '<meta name="report:date" content="2027-01-06">'
            '<meta name="report:title" content="显式标题">'
            '<meta name="report:summary" content="显式摘要。">'
            '<title>后备标题</title><h1>页面标题</h1>',
        )
        report = module.parse_report(path, self.root, self.entities, {})
        self.assertEqual(report["date"], "2027-01-06")
        self.assertEqual(report["title"], "显式标题")
        self.assertEqual(report["summary"], "显式摘要。")

    def test_filename_date_and_core_conclusion_are_fallbacks(self):
        path = self.write_html(
            "20270105_市场日报.html",
            "<title>2027-01-05 市场日报</title><h2>核心结论</h2>"
            "<p>半导体和有色金属观点出现明显分歧。</p>",
        )
        report = module.parse_report(path, self.root, self.entities, {})
        self.assertEqual(report["date"], "2027-01-05")
        self.assertEqual(report["title"], "市场日报")
        self.assertIn("半导体", report["summary"])

    def test_missing_date_is_blocking(self):
        path = self.write_html("market.html", "<title>市场日报</title>")
        with self.assertRaisesRegex(module.ReportParseError, "无法识别日期"):
            module.parse_report(path, self.root, self.entities, {})
```

- [ ] **Step 2: Run the parser tests and confirm the red state**

Run: `python -m unittest tests.test_report_import.ParserTests -v`

Expected: FAIL because `tools/build_reports_index.py` and its public parser interfaces do not exist.

- [ ] **Step 3: Implement the standard-library HTML parser**

Implement `HTMLParser` handling for metadata, headings, paragraphs, lists, and tables. Normalize whitespace without concatenating adjacent semantic blocks. Decode UTF-8 with BOM support and retry GB18030 only when UTF-8 decoding fails.

```python
class ReportParseError(ValueError):
    """表示单份日报缺少生成索引所必需的信息。"""

@dataclass
class ParsedDocument:
    title: str
    meta: dict[str, str]
    headings: list[tuple[int, str]]
    paragraphs: list[str]
    lists: list[str]
    tables: list[list[list[str]]]
    text: str

def parse_report(path: Path, root: Path, entities: dict, overrides: dict) -> dict:
    document = extract_document(path)
    date = extract_date(document, path)
    title = extract_title(document, path, date)
    summary, warnings = extract_summary(document)
    return {
        "id": stable_report_id(date, path, path.read_bytes()),
        "date": date,
        "year": int(date[:4]),
        "title": title,
        "summary": summary,
        "file": path.relative_to(root).as_posix(),
        "industries": [],
        "tags": [],
        "stocks": [],
        "influencers": [],
        "sources": [],
        "featured": False,
        "metrics": {},
        "_warnings": warnings,
    }
```

- [ ] **Step 4: Run parser tests**

Run: `python -m unittest tests.test_report_import.ParserTests -v`

Expected: all `ParserTests` pass.

- [ ] **Step 5: Commit the parser core**

```powershell
git add tools/build_reports_index.py tests/test_report_import.py
git commit -m "feat: parse report html metadata"
```

### Task 2: Entity, tag, industry, and source extraction

**Files:**
- Create: `data/entities.json`
- Modify: `tools/build_reports_index.py`
- Modify: `tests/test_report_import.py`

**Interfaces:**
- Consumes: `ParsedDocument` and base record from Task 1.
- Produces: `load_entities(path: Path) -> dict`
- Produces: `extract_stocks(document: ParsedDocument, entities: dict) -> list[dict[str, str]]`
- Produces: `extract_influencers(document: ParsedDocument, entities: dict) -> list[str]`
- Produces: `score_controlled_terms(text: str, definitions: list[dict], limit: int) -> list[str]`
- Produces: `extract_sources(document: ParsedDocument, entities: dict) -> list[str]`

- [ ] **Step 1: Add failing extraction tests**

```python
class EntityExtractionTests(unittest.TestCase):
    def test_metadata_table_and_dictionary_entities_are_merged(self):
        html = """
        <meta name="report:stocks" content="紫金矿业|601899">
        <meta name="report:influencers" content="飞翔芸">
        <table><tr><th>标的</th><th>代码</th><th>作者</th></tr>
        <tr><td>腾讯控股</td><td>00700</td><td>伊夫圣洛朗</td></tr></table>
        <p>挖地瓜的超级鹿鼎公继续关注有色金属和风险提示。</p>
        """
        report = self.parse("20270105_entities.html", html)
        self.assertIn({"name": "紫金矿业", "code": "601899"}, report["stocks"])
        self.assertIn({"name": "腾讯控股", "code": "00700"}, report["stocks"])
        self.assertEqual(report["influencers"], ["飞翔芸", "伊夫圣洛朗", "挖地瓜的超级鹿鼎公"])
        self.assertIn("有色金属", report["industries"])
        self.assertIn("风险提示", report["tags"])

    def test_css_numbers_are_not_stock_codes(self):
        report = self.parse(
            "20270105_css.html",
            "<style>.x{color:#667085}</style><h1>日报</h1><p>暂无具体标的。</p>",
        )
        self.assertEqual(report["stocks"], [])
```

- [ ] **Step 2: Run entity tests and confirm they fail**

Run: `python -m unittest tests.test_report_import.EntityExtractionTests -v`

Expected: FAIL because records still contain empty entity arrays.

- [ ] **Step 3: Create the controlled entity dictionary**

Use this stable schema in `data/entities.json`:

```json
{
  "schemaVersion": 1,
  "influencers": [{"name": "飞翔芸", "aliases": ["飞翔芸"]}],
  "stocks": [{"name": "紫金矿业", "code": "601899", "aliases": ["紫金"]}],
  "industries": [{"name": "有色金属", "keywords": ["有色金属", "黄金", "铜", "铝"]}],
  "tags": [{"name": "风险提示", "keywords": ["风险提示", "谨慎", "回避"]}],
  "sources": [{"name": "雪球", "keywords": ["雪球", "大 V 评论"]}]
}
```

Populate it with every stock and influencer already present in `reports.json`, the fixed social accounts represented by the current reports, and the existing controlled industries and tags. Aliases must be explicit and must not contain ambiguous one-character tokens.

- [ ] **Step 4: Implement extraction and controlled scoring**

Only inspect visible text and parsed table cells. Match explicit metadata first, then recognized table headers, then exact dictionary aliases. Sort entities by first document occurrence and use canonical names for deduplication. Score controlled terms by exact phrase count plus heading bonus; cap industries at 6 and tags at 8.

```python
def score_controlled_terms(text: str, headings: str, definitions: list[dict], limit: int) -> list[str]:
    scored = []
    for position, definition in enumerate(definitions):
        score = sum(text.count(keyword) for keyword in definition["keywords"])
        score += 2 * sum(headings.count(keyword) for keyword in definition["keywords"])
        if score:
            scored.append((-score, position, definition["name"]))
    return [name for _, _, name in sorted(scored)[:limit]]
```

- [ ] **Step 5: Run parser and entity tests**

Run: `python -m unittest tests.test_report_import.ParserTests tests.test_report_import.EntityExtractionTests -v`

Expected: all selected tests pass.

- [ ] **Step 6: Commit entity extraction**

```powershell
git add data/entities.json tools/build_reports_index.py tests/test_report_import.py
git commit -m "feat: extract report entities and taxonomy"
```

### Task 3: Deterministic full-index generation and archive migration

**Files:**
- Create: `data/report-overrides.json`
- Modify: `tools/build_reports_index.py`
- Modify: `tests/test_report_import.py`
- Rename: `reports/` to `Reports/`
- Modify: `reports.json`
- Modify: `.gitattributes`

**Interfaces:**
- Consumes: `parse_report(...)` from Tasks 1-2.
- Produces: `build_index(root: Path, entities_path: Path, overrides_path: Path) -> tuple[dict, list[str]]`
- Produces: `validate_index(payload: dict, root: Path) -> None`
- Produces: `write_index_atomic(payload: dict, destination: Path) -> None`
- CLI: `python tools/build_reports_index.py --root . --write`
- CLI: `python tools/build_reports_index.py --root . --check`

- [ ] **Step 1: Add failing deterministic-index tests**

```python
class IndexGenerationTests(unittest.TestCase):
    def test_full_scan_is_sorted_stable_and_valid(self):
        self.write_report("Reports/2027/20270105_b.html", "<title>2027-01-05 B</title>")
        self.write_report("Reports/2027/20270106_a.html", "<title>2027-01-06 A</title>")
        first, _ = module.build_index(self.root, self.entities_path, self.overrides_path)
        second, _ = module.build_index(self.root, self.entities_path, self.overrides_path)
        self.assertEqual(first, second)
        self.assertEqual([item["date"] for item in first["reports"]], ["2027-01-06", "2027-01-05"])
        module.validate_index(first, self.root)

    def test_override_preserves_curated_fields(self):
        payload, _ = module.build_index(self.root, self.entities_path, self.overrides_path)
        report = payload["reports"][0]
        self.assertEqual(report["id"], "curated-id")
        self.assertEqual(report["summary"], "人工校准摘要。")
```

- [ ] **Step 2: Run index tests and confirm they fail**

Run: `python -m unittest tests.test_report_import.IndexGenerationTests -v`

Expected: FAIL because full-scan generation and validation interfaces do not exist.

- [ ] **Step 3: Implement deterministic index generation**

Scan exactly `Reports/**/*.html`, reject case-insensitive duplicate relative paths and duplicate IDs, strip internal `_warnings` before serialization, sort records by `date` descending then title and path ascending, and compute `site.updatedAt` from the newest report date.

```python
def write_index_atomic(payload: dict, destination: Path) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(serialized, encoding="utf-8", newline="\n")
    temporary.replace(destination)
```

`--check` must compare generated bytes with the existing index and return exit code 1 with a concise message when stale. `--write` validates before calling `write_index_atomic`.

- [ ] **Step 4: Create curated overrides from the existing index**

Use paths as keys and copy the current curated fields verbatim:

```json
{
  "schemaVersion": 1,
  "reports": {
    "Reports/2026/20260730_165535_大V多空观点与交易动作总结.html": {
      "id": "20260730-dav-market-actions",
      "title": "大 V 多空观点与交易动作总结",
      "summary": "TCL 科技、AI、资源股和价值方向受到关注，期指与科技股出现明确加仓；市场短期方向、AI 估值和交易工具风险仍存在显著分歧。"
    }
  }
}
```

Include all existing fields for all three reports so the generated index remains behaviorally identical after migration.

- [ ] **Step 5: Rename the archive with a two-step Git move**

```powershell
git mv reports Reports-case-transition
git mv Reports-case-transition Reports
```

Update `.gitattributes` from `reports/**/*.html -text` to `Reports/**/*.html -text`.

- [ ] **Step 6: Generate and compare the migrated index**

Run: `python tools/build_reports_index.py --root . --write`

Expected: `reports.json` contains three records with `Reports/2026/...` paths, the same curated IDs and metadata, and `site.updatedAt` equal to `2026-07-30`.

- [ ] **Step 7: Run index tests and validation**

Run: `python -m unittest tests.test_report_import.IndexGenerationTests -v`

Run: `python tools/build_reports_index.py --root . --check`

Expected: both commands exit 0.

- [ ] **Step 8: Commit the generator and archive migration**

```powershell
git add .gitattributes Reports reports.json data/report-overrides.json tools/build_reports_index.py tests/test_report_import.py
git commit -m "feat: generate deterministic report index"
```

### Task 4: Inbox import and one-command PowerShell workflow

**Files:**
- Create: `Inbox/README.md`
- Create: `import_reports.ps1`
- Modify: `.gitignore`
- Modify: `tools/build_reports_index.py`
- Modify: `tests/test_report_import.py`

**Interfaces:**
- Produces: `import_inbox(root: Path) -> ImportResult`
- `ImportResult` contains `imported`, `skipped`, `failed`, and `warnings` lists.
- CLI: `python tools/build_reports_index.py --root . --import-inbox --write`
- PowerShell: `.\import_reports.ps1`
- PowerShell: `.\import_reports.ps1 -Publish`

- [ ] **Step 1: Add failing inbox tests**

```python
class InboxImportTests(unittest.TestCase):
    def test_import_moves_valid_html_to_year_directory(self):
        source = self.write_report("Inbox/20270105_日报.html", "<title>2027-01-05 日报</title>")
        result = module.import_inbox(self.root)
        self.assertFalse(source.exists())
        self.assertTrue((self.root / "Reports/2027/20270105_日报.html").exists())
        self.assertEqual(len(result.imported), 1)

    def test_invalid_or_conflicting_file_remains_in_inbox(self):
        invalid = self.write_report("Inbox/no-date.html", "<title>无日期日报</title>")
        result = module.import_inbox(self.root)
        self.assertTrue(invalid.exists())
        self.assertEqual(len(result.failed), 1)
```

- [ ] **Step 2: Run inbox tests and confirm they fail**

Run: `python -m unittest tests.test_report_import.InboxImportTests -v`

Expected: FAIL because `import_inbox` does not exist.

- [ ] **Step 3: Implement safe inbox import**

Parse each top-level `Inbox/*.html` before moving it. Create `Reports/<year>/` only for valid files. If the destination exists, compare SHA-256: leave identical or conflicting source files in `Inbox/` and report them as skipped or failed; never overwrite an archived HTML file.

After processing all candidates, build the index from valid archived reports. If index validation fails, do not write `reports.json` and return nonzero.

- [ ] **Step 4: Add the drop-folder contract**

Append to `.gitignore`:

```gitignore
Inbox/*.html
!Inbox/README.md
```

`Inbox/README.md` must state that the folder is local staging only and that imported HTML is archived under `Reports/<year>/`.

- [ ] **Step 5: Implement the PowerShell entrypoint**

The script must use strict mode, locate `python` or `py -3`, run the importer, run Python unit tests, locate Node.js from `PATH` or the Codex bundled runtime path, and run `node --test tests/site.test.mjs`.

For `-Publish`, verify that pre-existing Git changes are limited to `Inbox/*.html`; stage only `Reports`, `reports.json`, and the moved inbox files, create a concise commit, and run `git push`. Stop before staging when unrelated changes exist.

```powershell
param([switch]$Publish)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

& $python @pythonArgs "tools/build_reports_index.py" --root . --import-inbox --write
if ($LASTEXITCODE -ne 0) { throw "日报导入失败，原 HTML 已保留在 Inbox。" }
& $python @pythonArgs -m unittest tests.test_report_import -v
& $node --test tests/site.test.mjs
```

- [ ] **Step 6: Run inbox and full Python tests**

Run: `python -m unittest tests.test_report_import -v`

Expected: all Python tests pass, including invalid-file preservation.

- [ ] **Step 7: Run a PowerShell dry import with an empty Inbox**

Run: `powershell -ExecutionPolicy Bypass -File .\import_reports.ps1`

Expected: reports 0 new HTML files, confirms the index is current, and both Python and Node test suites pass.

- [ ] **Step 8: Commit the local workflow**

```powershell
git add .gitignore Inbox/README.md import_reports.ps1 tools/build_reports_index.py tests/test_report_import.py
git commit -m "feat: add one-command report import"
```

### Task 5: GitHub Actions index synchronization

**Files:**
- Create: `.github/workflows/update-reports.yml`
- Create: `tests/test_workflow_config.py`

**Interfaces:**
- Consumes: `python tools/build_reports_index.py --root . --write` and both test suites.
- Produces: a workflow with `contents: write`, path-scoped push triggers, deterministic regeneration, validation, and bot commit.

- [ ] **Step 1: Add failing workflow structure tests**

```python
class WorkflowConfigTests(unittest.TestCase):
    def test_workflow_rebuilds_tests_and_commits_index(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("Reports/**/*.html", text)
        self.assertIn("contents: write", text)
        self.assertIn("build_reports_index.py --root . --write", text)
        self.assertIn("python -m unittest", text)
        self.assertIn("node --test tests/site.test.mjs", text)
        self.assertIn("git diff --quiet -- reports.json", text)
```

- [ ] **Step 2: Run workflow test and confirm it fails**

Run: `python -m unittest tests.test_workflow_config -v`

Expected: FAIL because the workflow does not exist.

- [ ] **Step 3: Create the synchronization workflow**

Use `actions/checkout@v4`, `actions/setup-python@v5`, and `actions/setup-node@v4`. Trigger on pushes to `master` that touch `Reports/**/*.html`, parser code, dictionaries, overrides, or the workflow. Set `contents: write` at job level.

After generation and tests, use this guarded commit step:

```yaml
- name: 提交更新后的日报索引
  shell: bash
  run: |
    if git diff --quiet -- reports.json; then
      echo "reports.json 已是最新状态。"
      exit 0
    fi
    git config user.name "github-actions[bot]"
    git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
    git add reports.json
    git commit -m "chore: update report index"
    git push
```

- [ ] **Step 4: Run workflow and parser tests**

Run: `python -m unittest tests.test_workflow_config tests.test_report_import -v`

Expected: all tests pass.

- [ ] **Step 5: Commit the GitHub automation**

```powershell
git add .github/workflows/update-reports.yml tests/test_workflow_config.py
git commit -m "ci: synchronize report index"
```

### Task 6: Frontend compatibility, statistics, search, and maintenance documentation

**Files:**
- Modify: `tests/site.test.mjs`
- Modify: `README.md`
- Verify: `index.html`
- Verify: `script.js`
- Verify: `style.css`
- Verify: `reports.json`

**Interfaces:**
- Consumes: generated schema version 1 index.
- Preserves: `normalizeReport`, `calculateStats`, `filterReports`, `readFilters`, `createSearchParams`, and `loadReports` exports.
- Preserves URL filters: `q`, `year`, `industry`, `tag`, `stock`, and `influencer`.

- [ ] **Step 1: Update frontend contract tests before changing fixtures**

Change fixture and archive expectations from lowercase `reports/` to uppercase `Reports/`. Add an assertion that every generated report path starts with `Reports/<year>/` and that calculated statistics equal the generated unique entity counts.

```javascript
assert.match(report.file, new RegExp(`^Reports/${report.year}/.+\\.html$`));
assert.deepEqual(calculateStats(normalized), {
  reportCount: normalized.length,
  latestDate: payload.site.updatedAt,
  stockCount: new Set(normalized.flatMap((item) => item.stocks.map((stock) => stock.code || stock.name))).size,
  influencerCount: new Set(normalized.flatMap((item) => item.influencers)).size,
});
```

- [ ] **Step 2: Run Node tests and inspect any compatibility failures**

Run: `node --test tests/site.test.mjs`

Expected: generated index, statistics, search, and archive-access tests pass after path updates. If an existing frontend function fails, make the smallest compatible change in `script.js` without changing its public exports.

- [ ] **Step 3: Rewrite maintenance documentation in valid UTF-8**

Document exactly these daily flows:

```powershell
# Local import and preview preparation
.\import_reports.ps1

# Local import, validation, commit, and push
.\import_reports.ps1 -Publish
```

Also document direct GitHub upload to `Reports/<year>/`, automatic Action behavior, optional `<meta name="report:*">` fields, warning recovery, controlled dictionary maintenance, and extension boundaries for stock pages, influencer pages, rankings, and timelines.

- [ ] **Step 4: Run all local tests and index check**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`

Run: `node --test tests/site.test.mjs`

Run: `python tools/build_reports_index.py --root . --check`

Expected: every command exits 0; Node reports 0 failed tests; generator reports that `reports.json` is current.

- [ ] **Step 5: Commit compatibility and documentation**

```powershell
git add README.md tests/site.test.mjs script.js reports.json
git commit -m "docs: document automatic report maintenance"
```

### Task 7: End-to-end import, browser verification, and publication

**Files:**
- Verify all files changed by Tasks 1-6.
- Do not commit generated temporary fixtures or test output.

**Interfaces:**
- Verifies local workflow, static runtime, repository automation, and public deployment as one complete path.

- [ ] **Step 1: Run a disposable end-to-end import outside the repository**

Create a temporary project fixture containing `Inbox/20270105_自动导入验收.html`, the parser, dictionaries, and an empty archive. Run the importer and assert that the file moves to `Reports/2027/`, the index contains the parsed title, date, summary, tags, stocks, and influencers, and a second run produces identical JSON bytes.

Run: `python -m unittest tests.test_report_import.EndToEndImportTests -v`

Expected: PASS without modifying the real archive.

- [ ] **Step 2: Run the complete verification suite from a clean working tree candidate**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`

Run: `node --test tests/site.test.mjs`

Run: `python tools/build_reports_index.py --root . --check`

Run: `git diff --check`

Expected: all commands exit 0.

- [ ] **Step 3: Start the local static server and verify desktop and mobile behavior**

Run: `python -m http.server 8765 --bind 127.0.0.1`

Verify at `1440x1000` and `390x844`:

- Four statistics cards show 3 reports, `2026-07-30`, the generated unique stock count, and the generated unique influencer count.
- Searches for `000100`, `TCL科技`, `伊夫圣洛朗`, `2026-07-29`, and `仓位变化` return the expected reports.
- Every report button opens its `Reports/2026/...` URL with HTTP 200.
- No horizontal overflow or console error occurs.

- [ ] **Step 4: Review the final diff and commit any verification-only corrections**

Run: `git status --short`

Run: `git diff --stat master...HEAD`

If a verification correction was necessary, stage only its files and commit with `fix: complete automatic import verification`. Otherwise create no empty commit.

- [ ] **Step 5: Merge and push the implementation**

Fast-forward the reviewed implementation branch into `master`, then run:

```powershell
git push origin master
```

- [ ] **Step 6: Verify GitHub automation and the public site**

Check the latest `update-reports` workflow run, GitHub Pages build status, and these public URLs:

```text
https://jasonxgwang.github.io/investor-insight-hub/
https://jasonxgwang.github.io/investor-insight-hub/reports.json
https://jasonxgwang.github.io/investor-insight-hub/Reports/2026/20260730_165535_大V多空观点与交易动作总结.html
```

Expected: workflow success, Pages build success, HTTP 200 for all URLs, and three reports in the public index.
