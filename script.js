const FILTER_KEYS = ["q", "year", "type", "industry", "tag", "stock", "influencer"];
const REPORT_TYPES = Object.freeze(["daily", "trend", "portfolio"]);

const REPORT_TYPE_OPTIONS = Object.freeze([
  ["daily", "大V每日观点"],
  ["trend", "全站观点趋势专题"],
  ["portfolio", "大V雪球组合专题"],
]);

const REPORT_TYPE_LABELS = Object.freeze(
  Object.fromEntries(REPORT_TYPE_OPTIONS),
);

export function formatFilterValue(key, value) {
  if (key === "type") return REPORT_TYPE_LABELS[value] || value;
  return value;
}

export function getReportTypeOptions(reports) {
  return [
    {
      value: "",
      label: "全部类型",
      count: reports.length,
    },
    ...REPORT_TYPE_OPTIONS.map(([value, label]) => ({
      value,
      label,
      count: reports.filter((report) => report.type === value).length,
    })),
  ];
}

const EMPTY_FILTERS = Object.freeze(
  Object.fromEntries(FILTER_KEYS.map((key) => [key, ""])),
);

const toStringArray = (value) =>
  Array.isArray(value)
    ? value.map((item) => String(item).trim()).filter(Boolean)
    : [];

const normalizeForSearch = (value) => String(value || "").trim().toLocaleLowerCase("zh-CN");
const compactForSearch = (value) => normalizeForSearch(value).replace(/\s+/g, "");

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
  const rawType = String(report.type || "").trim();
  const type = REPORT_TYPES.includes(rawType) ? rawType : "daily";

  return {
    id: String(report.id).trim(),
    date,
    type,
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

  return values.map(compactForSearch).join(" ");
}

function includesNormalized(values, expected) {
  const needle = compactForSearch(expected);
  if (!needle) return true;
  return values.some((value) => compactForSearch(value).includes(needle));
}

/** 所有启用的筛选条件采用交集逻辑，结果固定按日期和 ID 倒序。 */
export function filterReports(reports, filters = {}) {
  const active = { ...EMPTY_FILTERS, ...filters };
  const keywords = String(active.q || "").trim().split(/\s+/).map(compactForSearch).filter(Boolean);

  return reports
    .filter((report) => {
      if (active.year && String(report.year) !== String(active.year)) return false;
      if (active.type && report.type !== active.type) return false;
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
  const filters = Object.fromEntries(
    FILTER_KEYS.map((key) => [key, String(params.get(key) || "").trim()]),
  );

  if (filters.type && !REPORT_TYPES.includes(filters.type)) {
    filters.type = "";
  }

  return filters;
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

/**
 * 加载并验证日报索引。fetchImpl 参数只用于自动化测试，浏览器运行时使用原生 fetch。
 * 这里返回的永远是完成标准化的有效记录，页面层不直接接触原始 JSON。
 */
export async function loadReports(url = "./reports.json", fetchImpl = globalThis.fetch) {
  let response;

  try {
    response = await fetchImpl(url, { cache: "no-cache" });
  } catch (error) {
    throw new Error("无法读取日报索引，请检查网络或部署路径。", { cause: error });
  }

  if (!response?.ok) {
    throw new Error(`无法读取日报索引（HTTP ${response?.status || "未知"}）。`);
  }

  let payload;
  try {
    payload = await response.json();
  } catch (error) {
    throw new Error("日报索引不是有效的 JSON 文件。", { cause: error });
  }

  if (!payload || !Array.isArray(payload.reports)) {
    throw new Error("日报索引格式无效：缺少 reports 数组。");
  }

  return payload.reports.map(normalizeReport).filter(Boolean);
}

const FILTER_LABELS = {
  q: "搜索",
  year: "年份",
  type: "报告类型",
  industry: "行业",
  tag: "标签",
  stock: "股票",
  influencer: "大 V",
};

const formatDate = (date, options = { year: "numeric", month: "2-digit", day: "2-digit" }) => {
  if (!date) return "暂无";
  return new Intl.DateTimeFormat("zh-CN", options).format(new Date(`${date}T00:00:00`));
};

const createTextElement = (tagName, className, text) => {
  const element = document.createElement(tagName);
  if (className) element.className = className;
  element.textContent = text;
  return element;
};

function collectCounts(reports, field) {
  const counts = new Map();

  for (const report of reports) {
    const values = field === "year" ? [String(report.year)] : report[field];
    for (const value of values) counts.set(value, (counts.get(value) || 0) + 1);
  }

  return [...counts.entries()].sort(([left], [right]) =>
    field === "year" ? right.localeCompare(left) : left.localeCompare(right, "zh-CN"),
  );
}

function renderStats(reports) {
  const stats = calculateStats(reports);
  document.querySelector("#stat-reports").textContent = stats.reportCount.toLocaleString("zh-CN");
  document.querySelector("#stat-updated").textContent = formatDate(stats.latestDate);
  document.querySelector("#stat-stocks").textContent = stats.stockCount.toLocaleString("zh-CN");
  document.querySelector("#stat-influencers").textContent =
    stats.influencerCount.toLocaleString("zh-CN");
}

function createFilterOption(label, count, key, value, activeValue, onSelect) {
  const button = document.createElement("button");
  button.className = "filter-option";
  button.type = "button";
  button.dataset.filter = key;
  button.dataset.value = value;
  button.setAttribute("aria-pressed", String(activeValue === value));
  button.append(
    createTextElement("span", "filter-name", label),
    createTextElement("span", "filter-count", String(count)),
  );
  button.addEventListener("click", () => onSelect(key, value));
  return button;
}

function renderFilterNavigation(reports, filters, onSelect) {
  const yearContainer = document.querySelector("#year-filters");
  const typeContainer = document.querySelector("#type-filters");
  const industryContainer = document.querySelector("#industry-filters");
  yearContainer.replaceChildren();
  typeContainer.replaceChildren();
  industryContainer.replaceChildren();

  yearContainer.append(
    createFilterOption("全部年份", reports.length, "year", "", filters.year, onSelect),
  );
  for (const [year, count] of collectCounts(reports, "year")) {
    yearContainer.append(createFilterOption(year, count, "year", year, filters.year, onSelect));
  }

  for (const option of getReportTypeOptions(reports)) {
    typeContainer.append(
      createFilterOption(
        option.label,
        option.count,
        "type",
        option.value,
        filters.type,
        onSelect,
      ),
    );
  }

  industryContainer.append(
    createFilterOption("全部行业", reports.length, "industry", "", filters.industry, onSelect),
  );
  for (const [industry, count] of collectCounts(reports, "industries")) {
    industryContainer.append(
      createFilterOption(industry, count, "industry", industry, filters.industry, onSelect),
    );
  }
}

function createDetail(label, values) {
  const row = document.createElement("div");
  row.className = "report-detail";
  row.append(
    createTextElement("dt", "", label),
    createTextElement("dd", "", values.length ? values.join("、") : "未标注"),
  );
  return row;
}

function renderReport(report) {
  const fragment = document.querySelector("#report-template").content.cloneNode(true);
  const card = fragment.querySelector(".report-card");
  const dateElement = fragment.querySelector(".report-date");
  dateElement.dateTime = report.date;
  dateElement.textContent = formatDate(report.date, { month: "2-digit", day: "2-digit" });
  fragment.querySelector(".report-year").textContent = `${report.year} 年`;
  fragment.querySelector(".report-title").textContent = report.title;
  fragment.querySelector(".report-summary").textContent = report.summary || "本期日报暂无摘要。";

  const sourceRow = fragment.querySelector(".report-source-row");
  const sources = report.sources.length ? report.sources : ["日报"];
  for (const source of sources) {
    sourceRow.append(createTextElement("span", "source-badge", source));
  }

  const details = fragment.querySelector(".report-details");
  const stockNames = report.stocks.map((stock) =>
    stock.code ? `${stock.name}（${stock.code}）` : stock.name,
  );
  details.append(
    createDetail("股票", stockNames),
    createDetail("大 V", report.influencers),
  );

  const tags = fragment.querySelector(".report-tags");
  for (const item of [...report.industries, ...report.tags].slice(0, 8)) {
    tags.append(createTextElement("span", "tag-chip", item));
  }

  if (report.file) {
    const link = document.createElement("a");
    link.className = "view-report";
    link.href = report.file;
    link.target = "_blank";
    link.rel = "noopener";
    link.setAttribute("aria-label", `查看报告：${report.title}`);
    link.append(
      createTextElement("span", "", "查看报告"),
      createTextElement("span", "view-arrow", "↗"),
    );
    fragment.querySelector(".report-action").append(link);
  }

  card.dataset.reportId = report.id;
  return fragment;
}

function renderState({ title, description, actionLabel = "", onAction = null, symbol = "i" }) {
  const list = document.querySelector("#report-list");
  const fragment = document.querySelector("#state-template").content.cloneNode(true);
  fragment.querySelector(".state-symbol").textContent = symbol;
  fragment.querySelector(".state-title").textContent = title;
  fragment.querySelector(".state-description").textContent = description;

  const action = fragment.querySelector(".state-action");
  if (actionLabel && onAction) {
    action.textContent = actionLabel;
    action.addEventListener("click", onAction);
  } else {
    action.remove();
  }

  list.replaceChildren(fragment);
}

function renderActiveFilters(filters, onRemove) {
  const container = document.querySelector("#active-filters");
  container.replaceChildren();

  for (const key of FILTER_KEYS) {
    if (!filters[key]) continue;
    const chip = createTextElement(
      "span",
      "active-filter",
      `${FILTER_LABELS[key]}：${formatFilterValue(key, filters[key])}`,
    );
    const remove = createTextElement("button", "", "×");
    remove.type = "button";
    remove.title = `移除${FILTER_LABELS[key]}筛选`;
    remove.setAttribute("aria-label", remove.title);
    remove.addEventListener("click", () => onRemove(key));
    chip.append(remove);
    container.append(chip);
  }
}

function renderReports(reports, allReports, filters, resetFilters) {
  const list = document.querySelector("#report-list");
  const count = document.querySelector("#result-count");
  count.textContent = `显示 ${reports.length} / ${allReports.length} 份日报`;

  if (!allReports.length) {
    renderState({
      title: "资料库尚无日报",
      description: "将日报 HTML 放入 reports 目录并更新 reports.json 后，内容会显示在这里。",
      symbol: "＋",
    });
    return;
  }

  if (!reports.length) {
    renderState({
      title: "没有匹配的日报",
      description: "尝试缩短关键词，或清除年份、行业及其他筛选条件。",
      actionLabel: "清除筛选",
      onAction: resetFilters,
      symbol: "0",
    });
    return;
  }

  const fragment = document.createDocumentFragment();
  for (const report of reports) fragment.append(renderReport(report));
  list.replaceChildren(fragment);
}

function syncUrl(filters) {
  const params = createSearchParams(filters);
  const query = params.toString();
  const nextUrl = `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`;
  window.history.replaceState(null, "", nextUrl);
}

function setupMobileFilters() {
  const panel = document.querySelector("#filters-panel");
  const toggle = document.querySelector("#filter-toggle");
  const close = document.querySelector("#filters-close");

  const closePanel = (restoreFocus = true) => {
    panel.classList.remove("is-open");
    document.body.classList.remove("filters-open");
    toggle.setAttribute("aria-expanded", "false");
    if (restoreFocus) toggle.focus();
  };

  toggle.addEventListener("click", () => {
    panel.classList.add("is-open");
    document.body.classList.add("filters-open");
    toggle.setAttribute("aria-expanded", "true");
    close.focus();
  });
  close.addEventListener("click", () => closePanel());
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && panel.classList.contains("is-open")) closePanel();
  });
  window.addEventListener("resize", () => {
    if (window.innerWidth > 820 && panel.classList.contains("is-open")) closePanel(false);
  });

  return closePanel;
}

/** 页面启动器只负责协调状态，数据处理仍由上方可独立测试的纯函数完成。 */
async function initializeSite() {
  const searchInput = document.querySelector("#search-input");
  const clearSearch = document.querySelector("#clear-search");
  const resetButton = document.querySelector("#reset-filters");
  const closeMobileFilters = setupMobileFilters();
  let reports = [];
  let filters = readFilters(window.location.search);
  let debounceTimer;

  searchInput.value = filters.q;
  clearSearch.hidden = !filters.q;
  renderState({ title: "正在载入日报", description: "正在读取资料库索引，请稍候。", symbol: "…" });

  const resetFilters = () => {
    filters = { ...EMPTY_FILTERS };
    searchInput.value = "";
    clearSearch.hidden = true;
    applyState();
  };

  const setFilter = (key, value) => {
    filters = { ...filters, [key]: value };
    applyState();
    if (window.innerWidth <= 820) closeMobileFilters();
  };

  const applyState = () => {
    const visibleReports = filterReports(reports, filters);
    renderFilterNavigation(reports, filters, setFilter);
    renderActiveFilters(filters, (key) => {
      filters = { ...filters, [key]: "" };
      if (key === "q") {
        searchInput.value = "";
        clearSearch.hidden = true;
      }
      applyState();
    });
    renderReports(visibleReports, reports, filters, resetFilters);
    syncUrl(filters);
  };

  searchInput.addEventListener("input", () => {
    clearTimeout(debounceTimer);
    clearSearch.hidden = !searchInput.value;
    debounceTimer = setTimeout(() => {
      filters = { ...filters, q: searchInput.value.trim() };
      applyState();
    }, 150);
  });

  clearSearch.addEventListener("click", () => {
    searchInput.value = "";
    filters = { ...filters, q: "" };
    clearSearch.hidden = true;
    applyState();
    searchInput.focus();
  });
  resetButton.addEventListener("click", resetFilters);

  try {
    reports = await loadReports();
    renderStats(reports);
    applyState();
  } catch (error) {
    document.querySelector("#result-count").textContent = "载入失败";
    renderState({
      title: "无法载入日报",
      description: error.message,
      actionLabel: "重新加载",
      onAction: () => window.location.reload(),
      symbol: "!",
    });
  }
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeSite, { once: true });
  } else {
    initializeSite();
  }
}
