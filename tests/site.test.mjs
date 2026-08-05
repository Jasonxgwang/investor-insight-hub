import test from "node:test";
import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import {
  calculateStats,
  createSearchParams,
  filterReports,
  loadReports,
  normalizeReport,
  readFilters,
} from "../script.js";

test("数据模块提供归档检索所需的公共接口", async () => {
  let siteModule = {};

  try {
    siteModule = await import("../script.js");
  } catch {
    // 首次红灯运行时模块尚不存在，继续通过断言展示缺失的公共契约。
  }

  assert.equal(typeof siteModule.normalizeReport, "function");
  assert.equal(typeof siteModule.calculateStats, "function");
  assert.equal(typeof siteModule.filterReports, "function");
  assert.equal(typeof siteModule.readFilters, "function");
  assert.equal(typeof siteModule.createSearchParams, "function");
  assert.equal(typeof siteModule.loadReports, "function");
});

const makeReports = () => [
  normalizeReport({
    id: "20260730-market-summary",
    date: "2026-07-30",
    title: "大 V 多空观点与交易动作总结",
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
    title: "雪球大 V 观点总结",
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

test("标准化记录会推导年份并填充安全默认值", () => {
  const report = normalizeReport({ id: "one", date: "2026-07-30", title: "标题" });

  assert.equal(report.year, 2026);
  assert.deepEqual(report.tags, []);
  assert.deepEqual(report.metrics, {});
});

test("标准化记录会拒绝缺少标识、日期或标题的数据", () => {
  assert.equal(normalizeReport({ date: "2026-07-30", title: "标题" }), null);
  assert.equal(normalizeReport({ id: "one", title: "标题" }), null);
  assert.equal(normalizeReport({ id: "one", date: "2026-07-30" }), null);
});

test("统计会对股票和大 V 去重并找出最近日期", () => {
  assert.deepEqual(calculateStats(makeReports()), {
    reportCount: 2,
    latestDate: "2026-07-30",
    stockCount: 3,
    influencerCount: 3,
  });
});

test("关键词可匹配代码、大 V、标签和日期", () => {
  const reports = makeReports();
  assert.equal(filterReports(reports, { q: "TCL科技" }).length, 1);
  assert.deepEqual(filterReports(reports, { q: "000100" }).map((item) => item.id), [
    "20260730-market-summary",
  ]);
  assert.equal(filterReports(reports, { q: "伊夫圣洛朗" }).length, 1);
  assert.equal(filterReports(reports, { q: "仓位变化" }).length, 1);
  assert.equal(filterReports(reports, { q: "2026-07-29" }).length, 1);
});

test("关键词、年份和行业使用交集筛选并按日期倒序", () => {
  const result = filterReports(makeReports(), {
    q: "紫金",
    year: "2026",
    industry: "科技",
  });

  assert.equal(result.length, 2);
  assert.ok(result[0].date > result[1].date);
});

test("预留 URL 筛选条件可往返且不保留空参数", () => {
  const filters = readFilters("?q=TCL&year=2026&stock=000100&tag=");

  assert.equal(filters.q, "TCL");
  assert.equal(filters.stock, "000100");
  assert.equal(createSearchParams(filters).toString(), "q=TCL&year=2026&stock=000100");
});

test("首页提供完整的语义区域和可访问检索控件", async () => {
  const html = await readFile(new URL("../index.html", import.meta.url), "utf8").catch(() => "");

  assert.match(html, /<html[^>]+lang="zh-CN"/);
  assert.match(html, /<meta[^>]+name="viewport"/);
  assert.match(html, /<header[\s>]/);
  assert.match(html, /<aside[^>]+id="filters-panel"/);
  assert.match(html, /<main[\s>]/);
  assert.match(html, /id="search-input"/);
  assert.match(html, /id="year-filters"/);
  assert.match(html, /id="industry-filters"/);
  assert.match(html, /id="report-list"/);
  assert.match(html, /<script[^>]+type="module"[^>]+src="\.\/script\.js"/);
});

test("样式表覆盖键盘焦点和两档响应式布局", async () => {
  const css = await readFile(new URL("../style.css", import.meta.url), "utf8").catch(() => "");

  assert.match(css, /:focus-visible/);
  assert.match(css, /@media[^\{]+max-width:\s*820px/);
  assert.match(css, /@media[^\{]+max-width:\s*560px/);
  assert.match(css, /prefers-reduced-motion/);
});

test("索引加载器只返回通过标准化的有效记录", async () => {
  const fetchIndex = async () => ({
    ok: true,
    json: async () => ({
      reports: [
        { id: "valid", date: "2026-07-30", title: "有效日报" },
        { date: "2026-07-30", title: "缺少 ID" },
      ],
    }),
  });

  const loaded = await loadReports("./reports.json", fetchIndex);

  assert.equal(loaded.length, 1);
  assert.equal(loaded[0].id, "valid");
});

test("索引加载器会把网络失败和错误结构转换为明确错误", async () => {
  const failedRequest = async () => ({ ok: false, status: 503 });
  const invalidPayload = async () => ({ ok: true, json: async () => ({ reports: null }) });

  await assert.rejects(loadReports("./reports.json", failedRequest), /无法读取日报索引/);
  await assert.rejects(loadReports("./reports.json", invalidPayload), /日报索引格式无效/);
});

test("首批索引包含三条唯一、有效且可访问的日报", async () => {
  const indexUrl = new URL("../reports.json", import.meta.url);
  const indexText = await readFile(indexUrl, "utf8").catch(() => "");
  assert.notEqual(indexText, "", "reports.json 必须存在且可读取");

  const payload = JSON.parse(indexText);
  const normalized = payload.reports.map(normalizeReport).filter(Boolean);
  assert.equal(payload.schemaVersion, 1);
  assert.equal(normalized.length, 3);
  assert.equal(new Set(normalized.map((report) => report.id)).size, 3);
  assert.deepEqual(
    normalized.map((report) => report.date).sort(),
    ["2026-07-27", "2026-07-29", "2026-07-30"],
  );

  for (const report of normalized) {
    await access(new URL(`../${report.file}`, import.meta.url));
  }
});
