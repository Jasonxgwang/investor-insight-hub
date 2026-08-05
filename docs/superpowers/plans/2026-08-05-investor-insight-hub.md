# Investor Insight Hub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a maintainable, responsive static archive that loads `reports.json`, searches and filters investment reports, and opens three supplied HTML daily reports.

**Architecture:** `index.html` provides semantic page regions and stable DOM hooks; `style.css` owns the responsive visual system; `script.js` is an ES module that separates pure data functions from DOM rendering and browser initialization. `reports.json` is the canonical index, while original report HTML files remain unchanged under `reports/<year>/`.

**Tech Stack:** HTML5, CSS3, vanilla JavaScript ES modules, Node.js built-in test runner, local HTTP server, browser visual inspection.

## Global Constraints

- The deployed site must remain pure static HTML, CSS, JavaScript, JSON, and report assets.
- Do not introduce a package manager, runtime dependency, framework, database, server application, font service, or third-party CDN.
- All deployed URLs must be relative and compatible with a GitHub Pages project or repository root.
- Homepage search uses only structured fields in `reports.json`; it must not fetch report bodies.
- Preserve the three supplied report HTML files byte-for-byte and retain their filenames.
- Use detailed Chinese comments at maintenance boundaries, while avoiding comments that merely restate individual assignments.
- The first version directly exposes year and industry controls and accepts URL parameters `q`, `year`, `industry`, `tag`, `stock`, and `influencer`.

---

## File Map

- `index.html`: semantic shell, accessible controls, statistics, navigation, report list, loading/error/empty templates.
- `style.css`: design tokens, desktop layout, report rows, filters, states, and responsive breakpoints.
- `script.js`: schema normalization, statistics, filtering, URL state, DOM rendering, and initialization.
- `reports.json`: versioned report metadata and all searchable fields.
- `reports/2026/*.html`: unchanged source reports.
- `tests/site.test.mjs`: pure data-function tests using `node:test` and `node:assert/strict`.
- `README.md`: maintenance workflow and GitHub Pages deployment instructions.

---

### Task 1: Data Functions and Automated Tests

**Files:**
- Create: `script.js`
- Create: `tests/site.test.mjs`

**Interfaces:**
- Produces: `normalizeReport(report) -> NormalizedReport | null`
- Produces: `calculateStats(reports) -> { reportCount, latestDate, stockCount, influencerCount }`
- Produces: `filterReports(reports, filters) -> NormalizedReport[]`
- Produces: `readFilters(search) -> { q, year, industry, tag, stock, influencer }`
- Produces: `createSearchParams(filters) -> URLSearchParams`

- [ ] **Step 1: Write failing tests for normalization and statistics**

Create `tests/site.test.mjs` with fixtures that include duplicate stocks and influencers:

```js
import test from "node:test";
import assert from "node:assert/strict";
import {
  calculateStats,
  createSearchParams,
  filterReports,
  normalizeReport,
  readFilters,
} from "../script.js";

const reports = [
  normalizeReport({
    id: "20260730-market-summary",
    date: "2026-07-30",
    title: "大V多空观点与交易动作总结",
    summary: "科技与资源方向出现分歧。",
    file: "reports/2026/report-a.html",
    industries: ["科技", "有色金属"],
    tags: ["多空观点", "仓位变化"],
    stocks: [
      { name: "TCL 科技", code: "000100" },
      { name: "紫金矿业", code: "601899" },
    ],
    influencers: ["飞翔的阿炳", "斯托伯的天空"],
    sources: ["雪球", "微博"],
  }),
  normalizeReport({
    id: "20260729-xueqiu-summary",
    date: "2026-07-29",
    title: "雪球大V观点总结",
    summary: "记录腾讯控股与宁德时代。",
    file: "reports/2026/report-b.html",
    industries: ["科技", "新能源"],
    tags: ["交易动作"],
    stocks: [
      { name: "腾讯控股", code: "00700" },
      { name: "紫金矿业", code: "601899" },
    ],
    influencers: ["飞翔的阿炳", "伊夫圣洛朗"],
    sources: ["雪球"],
  }),
].filter(Boolean);

test("normalizeReport derives year and safe defaults", () => {
  const report = normalizeReport({ id: "one", date: "2026-07-30", title: "标题" });
  assert.equal(report.year, 2026);
  assert.deepEqual(report.tags, []);
  assert.deepEqual(report.metrics, {});
});

test("normalizeReport rejects records without required identity fields", () => {
  assert.equal(normalizeReport({ date: "2026-07-30", title: "标题" }), null);
  assert.equal(normalizeReport({ id: "one", title: "标题" }), null);
});

test("calculateStats counts unique stocks and influencers", () => {
  assert.deepEqual(calculateStats(reports), {
    reportCount: 2,
    latestDate: "2026-07-30",
    stockCount: 3,
    influencerCount: 3,
  });
});
```

- [ ] **Step 2: Run tests and confirm the missing-module failure**

Run: `node --test tests/site.test.mjs`

Expected: FAIL because `script.js` and its exports do not exist.

- [ ] **Step 3: Implement normalization and statistics**

Create `script.js` as an ES module. Add Chinese comments above the schema-normalization boundary and unique-count rules. Use these exact behaviors:

```js
const EMPTY_FILTERS = Object.freeze({
  q: "",
  year: "",
  industry: "",
  tag: "",
  stock: "",
  influencer: "",
});

const toStringArray = (value) =>
  Array.isArray(value)
    ? value.map((item) => String(item).trim()).filter(Boolean)
    : [];

export function normalizeReport(report) {
  if (!report || !report.id || !report.date || !report.title) return null;

  const stocks = Array.isArray(report.stocks)
    ? report.stocks
        .map((stock) => ({
          name: String(stock?.name || "").trim(),
          code: String(stock?.code || "").trim(),
        }))
        .filter((stock) => stock.name || stock.code)
    : [];

  return {
    id: String(report.id),
    date: String(report.date),
    year: Number(report.year) || Number(String(report.date).slice(0, 4)),
    title: String(report.title),
    summary: String(report.summary || ""),
    file: String(report.file || ""),
    industries: toStringArray(report.industries),
    tags: toStringArray(report.tags),
    stocks,
    influencers: toStringArray(report.influencers),
    sources: toStringArray(report.sources),
    featured: Boolean(report.featured),
    metrics: report.metrics && typeof report.metrics === "object" ? report.metrics : {},
  };
}

export function calculateStats(reports) {
  const stocks = new Set();
  const influencers = new Set();
  let latestDate = "";

  for (const report of reports) {
    if (report.date > latestDate) latestDate = report.date;
    for (const stock of report.stocks) stocks.add(stock.code || stock.name);
    for (const influencer of report.influencers) influencers.add(influencer);
  }

  return {
    reportCount: reports.length,
    latestDate,
    stockCount: stocks.size,
    influencerCount: influencers.size,
  };
}
```

- [ ] **Step 4: Add failing tests for keyword, combined filters, and URL state**

Append these tests:

```js
test("keyword search covers stock code, influencer, tag, and date", () => {
  assert.deepEqual(filterReports(reports, { q: "000100" }).map((item) => item.id), [
    "20260730-market-summary",
  ]);
  assert.equal(filterReports(reports, { q: "伊夫圣洛朗" }).length, 1);
  assert.equal(filterReports(reports, { q: "仓位变化" }).length, 1);
  assert.equal(filterReports(reports, { q: "2026-07-29" }).length, 1);
});

test("year, industry, and keyword filters use intersection logic", () => {
  const result = filterReports(reports, {
    q: "紫金",
    year: "2026",
    industry: "科技",
  });
  assert.equal(result.length, 2);
  assert.ok(result[0].date > result[1].date);
});

test("reserved URL filters round-trip without empty parameters", () => {
  const filters = readFilters("?q=TCL&year=2026&stock=000100&tag=");
  assert.equal(filters.q, "TCL");
  assert.equal(filters.stock, "000100");
  assert.equal(createSearchParams(filters).toString(), "q=TCL&year=2026&stock=000100");
});
```

- [ ] **Step 5: Implement search and URL functions**

Build one normalized, lowercase search string per report from all approved fields. Match every active structured filter and sort descending by `date`, then by `id`. `createSearchParams` must emit only non-empty values in `EMPTY_FILTERS` key order.

- [ ] **Step 6: Run the data tests**

Run: `node --test tests/site.test.mjs`

Expected: all tests PASS.

- [ ] **Step 7: Commit the data layer**

```powershell
git add script.js tests/site.test.mjs
git -c user.name="Codex" -c user.email="codex@local.invalid" commit -m "feat: add report search data layer"
```

---

### Task 2: Accessible Homepage and Responsive Styling

**Files:**
- Create: `index.html`
- Create: `style.css`
- Modify: `script.js`

**Interfaces:**
- Consumes: data functions from Task 1.
- Produces: `loadReports(url = "./reports.json") -> Promise<NormalizedReport[]>`
- Produces: browser initialization guarded by `typeof document !== "undefined"`.

- [ ] **Step 1: Create semantic HTML with stable hooks**

Create `index.html` with:

- `<header>` containing the bilingual product name and a compact archive descriptor.
- Four statistic elements with IDs `stat-reports`, `stat-updated`, `stat-stocks`, and `stat-influencers`.
- A labeled search input `#search-input`, clear button `#clear-search`, and mobile filter toggle `#filter-toggle`.
- `<aside id="filters-panel">` with `#year-filters` and `#industry-filters`.
- `<main>` with `#result-count`, `#active-filters`, and `#report-list`.
- `<template>` elements for report rows, error state, empty library, and no results.
- `<script type="module" src="./script.js"></script>`.

All icon-only buttons must include an accessible name and tooltip. The report row template must keep date, source, title, summary, chips, and action in separate stable regions so dynamic text cannot resize toolbar controls.

- [ ] **Step 2: Add the complete responsive design system**

Create `style.css` with exact design tokens at `:root`:

```css
:root {
  --color-bg: #f6f8fb;
  --color-surface: #ffffff;
  --color-text: #172033;
  --color-muted: #637083;
  --color-line: #dfe5ec;
  --color-primary: #1769aa;
  --color-primary-strong: #0e4f86;
  --color-accent: #147d72;
  --color-soft-blue: #edf5fb;
  --color-soft-green: #eaf6f3;
  --radius: 8px;
  --shadow: 0 8px 24px rgba(23, 32, 51, 0.07);
  --content-width: 1440px;
}
```

Use a `240px minmax(0, 1fr)` desktop content grid, `44px` minimum control height, visible `:focus-visible` outlines, and line clamps only for summaries. At widths below `820px`, switch to one column and reveal the filter toggle. At widths below `560px`, stack report metadata and action without shrinking the action button below its readable width. Add `prefers-reduced-motion` handling.

- [ ] **Step 3: Implement DOM rendering and state handling**

Extend `script.js` with Chinese comments around:

- JSON schema validation and normalization;
- derived year/industry navigation counts;
- URL-to-state and state-to-URL synchronization;
- safe rendering with `textContent` and element creation;
- loading, error, empty-library, and no-results state transitions;
- responsive filter-panel open/close behavior.

Use `fetch("./reports.json", { cache: "no-cache" })`, check `response.ok`, validate `payload.reports` as an array, and throw a user-facing error on failure. Search input updates should use a short `150ms` debounce. Browser initialization must run only when `document` exists so Node tests continue to import the module.

- [ ] **Step 4: Add static structure tests**

Append Node tests that read `index.html` and `style.css` using `node:fs/promises`. Assert that the module script, required IDs, `lang="zh-CN"`, viewport meta, two responsive breakpoints, and `:focus-visible` exist.

- [ ] **Step 5: Run automated tests**

Run: `node --test tests/site.test.mjs`

Expected: all data and static structure tests PASS.

- [ ] **Step 6: Commit the homepage**

```powershell
git add index.html style.css script.js tests/site.test.mjs
git -c user.name="Codex" -c user.email="codex@local.invalid" commit -m "feat: build responsive report archive homepage"
```

---

### Task 3: Initial Report Index and Original HTML Files

**Files:**
- Create: `reports.json`
- Copy unchanged: `reports/2026/20260727_233314_投资观点与交易动作汇总.html`
- Copy unchanged: `reports/2026/20260729_雪球JS评论_大V多空与仓位变化总结.html`
- Copy unchanged: `reports/2026/20260730_165535_大V多空观点与交易动作总结.html`

**Interfaces:**
- Consumes: the schema accepted by `normalizeReport`.
- Produces: three valid records whose `file` values resolve to the copied HTML files.

- [ ] **Step 1: Copy the source reports without modification**

Create `reports/2026/`, copy the three user-provided files, and compare SHA-256 hashes between source and destination. The source paths are:

```text
F:\WeChat Files\xwechat_files\wxid_gk2j4ryc37ag22_fbc3\msg\file\2026-08\20260727_233314_投资观点与交易动作汇总.html
F:\WeChat Files\xwechat_files\wxid_gk2j4ryc37ag22_fbc3\msg\file\2026-08\20260729_雪球JS评论_大V多空与仓位变化总结.html
F:\WeChat Files\xwechat_files\wxid_gk2j4ryc37ag22_fbc3\msg\file\2026-08\20260730_165535_大V多空观点与交易动作总结.html
```

- [ ] **Step 2: Create the versioned report index**

Create UTF-8 `reports.json` with `schemaVersion: 1`, site name, and three records. Use the report `<title>` and visible core conclusions to write concise summaries. Populate searchable arrays with explicitly named industries, stocks, influencers, tags, and sources from each report; do not infer stock codes unless the code is present or can be unambiguously mapped from the report's named security.

- [ ] **Step 3: Add index integrity tests**

Append tests that parse `reports.json`, normalize every record, assert exactly three valid records and unique IDs, and verify each referenced file exists. Assert the three expected dates `2026-07-27`, `2026-07-29`, and `2026-07-30`.

- [ ] **Step 4: Run tests and verify hashes**

Run: `node --test tests/site.test.mjs`

Expected: all tests PASS.

Run `Get-FileHash -Algorithm SHA256` for each source and destination pair.

Expected: every pair has identical hashes.

- [ ] **Step 5: Commit the initial archive**

```powershell
git add reports.json reports/2026 tests/site.test.mjs
git -c user.name="Codex" -c user.email="codex@local.invalid" commit -m "content: add initial investment reports"
```

---

### Task 4: Maintenance Documentation and End-to-End Verification

**Files:**
- Create: `README.md`
- Modify only if verification finds a defect: `index.html`, `style.css`, `script.js`, `reports.json`

**Interfaces:**
- Produces: a repeatable report-addition workflow and a GitHub Pages deployment checklist.

- [ ] **Step 1: Write maintenance documentation**

Document these exact operations in Chinese:

1. Copy a new daily HTML file into `reports/YYYY/`.
2. Add one matching object to `reports.json` using the current schema.
3. Run `node --test tests/site.test.mjs`.
4. Start a local HTTP server; explain that direct `file://` opening cannot reliably fetch JSON.
5. Commit and push, then enable GitHub Pages from the repository root branch.
6. Explain reserved fields and the future migration path to per-year JSON indexes.

Include one complete sample report object and a field-reference table. Do not include private source URLs or cookies.

- [ ] **Step 2: Start a local static server**

Prefer the available Python runtime:

```powershell
python -m http.server 8765 --bind 127.0.0.1
```

If port `8765` is occupied, select another free localhost port and record the actual URL.

- [ ] **Step 3: Verify desktop behavior in a real browser**

At `1440x1000`, verify:

- four statistics equal the values derived from `reports.json`;
- default order is July 30, July 29, July 27;
- searches for a stock name, stock code, influencer, tag, and date return the expected rows;
- year and industry intersection filtering works;
- query parameters survive reload;
- every report button opens the corresponding report;
- loading, no-results, and reset controls are coherent;
- no console errors occur.

- [ ] **Step 4: Verify mobile and tablet behavior**

At `390x844` and `768x1024`, capture screenshots and verify:

- no horizontal overflow;
- filter panel opens, closes, and returns keyboard focus;
- text and buttons do not overlap;
- report actions remain reachable;
- the first viewport shows the brand, statistics, and search without oversized empty space.

- [ ] **Step 5: Run final automated verification**

Run: `node --test tests/site.test.mjs`

Expected: all tests PASS.

Run: `git status --short`

Expected: only intended documentation or verified fixes are uncommitted before the final commit.

- [ ] **Step 6: Commit documentation and verified fixes**

```powershell
git add README.md index.html style.css script.js reports.json tests/site.test.mjs
git -c user.name="Codex" -c user.email="codex@local.invalid" commit -m "docs: add site maintenance and deployment guide"
```
