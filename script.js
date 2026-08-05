const FILTER_KEYS = ["q", "year", "industry", "tag", "stock", "influencer"];

const EMPTY_FILTERS = Object.freeze(
  Object.fromEntries(FILTER_KEYS.map((key) => [key, ""])),
);

const toStringArray = (value) =>
  Array.isArray(value)
    ? value.map((item) => String(item).trim()).filter(Boolean)
    : [];

const normalizeForSearch = (value) => String(value || "").trim().toLocaleLowerCase("zh-CN");

/**
 * 把 reports.json 中可能缺少可选字段的记录整理为统一结构。
 * 这个边界集中处理脏数据，后续统计和渲染就不必重复做空值判断。
 */
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

  const date = String(report.date).trim();

  return {
    id: String(report.id).trim(),
    date,
    year: Number(report.year) || Number(date.slice(0, 4)),
    title: String(report.title).trim(),
    summary: String(report.summary || "").trim(),
    file: String(report.file || "").trim(),
    industries: toStringArray(report.industries),
    tags: toStringArray(report.tags),
    stocks,
    influencers: toStringArray(report.influencers),
    sources: toStringArray(report.sources),
    featured: Boolean(report.featured),
    metrics:
      report.metrics && typeof report.metrics === "object" && !Array.isArray(report.metrics)
        ? report.metrics
        : {},
  };
}

/** 统计口径使用股票代码优先去重；无代码时再使用股票名称。 */
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

function buildSearchText(report) {
  const values = [
    report.date,
    report.title,
    report.summary,
    ...report.industries,
    ...report.tags,
    ...report.influencers,
    ...report.sources,
    ...report.stocks.flatMap((stock) => [stock.name, stock.code]),
  ];

  return normalizeForSearch(values.join(" "));
}

function includesNormalized(values, expected) {
  const needle = normalizeForSearch(expected);
  if (!needle) return true;
  return values.some((value) => normalizeForSearch(value).includes(needle));
}

/** 所有启用的筛选条件采用交集逻辑，结果固定按日期和 ID 倒序。 */
export function filterReports(reports, filters = {}) {
  const active = { ...EMPTY_FILTERS, ...filters };
  const keywords = normalizeForSearch(active.q).split(/\s+/).filter(Boolean);

  return reports
    .filter((report) => {
      if (active.year && String(report.year) !== String(active.year)) return false;
      if (!includesNormalized(report.industries, active.industry)) return false;
      if (!includesNormalized(report.tags, active.tag)) return false;
      if (!includesNormalized(report.influencers, active.influencer)) return false;

      if (active.stock) {
        const stockValues = report.stocks.flatMap((stock) => [stock.name, stock.code]);
        if (!includesNormalized(stockValues, active.stock)) return false;
      }

      const searchText = buildSearchText(report);
      return keywords.every((keyword) => searchText.includes(keyword));
    })
    .sort((left, right) =>
      right.date.localeCompare(left.date) || right.id.localeCompare(left.id),
    );
}

/** 从任意查询字符串中只读取站点支持的参数，忽略未知参数。 */
export function readFilters(search = "") {
  const params = new URLSearchParams(search);
  return Object.fromEntries(
    FILTER_KEYS.map((key) => [key, String(params.get(key) || "").trim()]),
  );
}

/** 只输出非空条件，并保持固定顺序，便于生成稳定、可分享的 URL。 */
export function createSearchParams(filters = {}) {
  const params = new URLSearchParams();

  for (const key of FILTER_KEYS) {
    const value = String(filters[key] || "").trim();
    if (value) params.set(key, value);
  }

  return params;
}
