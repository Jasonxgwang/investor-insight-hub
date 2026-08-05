# Investor Insight Hub 投资观点库

一个用于长期归档、分类和检索雪球与微博大 V 投资观点日报的纯静态网站。站点只包含 HTML、CSS、JavaScript 和 JSON，可直接部署到 GitHub Pages，不需要数据库、服务器或构建工具。

## 本地预览

浏览器直接使用 `file://` 打开 `index.html` 时，通常会因浏览器安全策略而无法读取 `reports.json`。请在项目根目录启动一个本地 HTTP 服务：

```powershell
python -m http.server 8765 --bind 127.0.0.1
```

然后访问：

```text
http://127.0.0.1:8765/
```

如果系统找不到 `python`，可以使用任意静态文件服务器；站点本身没有服务器端依赖。

## 目录说明

```text
Investor Insight Hub/
├─ index.html          # 首页结构
├─ style.css           # 视觉与响应式样式
├─ script.js           # 数据加载、搜索、筛选和渲染
├─ reports.json        # 日报目录索引，也是首页唯一数据源
├─ reports/
│  └─ 2026/            # 按年份保存原始 HTML 日报
├─ tests/
│  └─ site.test.mjs    # 数据与目录完整性测试
└─ docs/               # 设计说明和实施计划
```

## 新增一份日报

### 1．复制 HTML 文件

把新日报复制到对应年份目录：

```text
reports/2027/20270105_投资观点日报.html
```

日报文件可以保留自己的完整样式。首页不会读取正文，只通过“查看报告”按钮打开它。

### 2．更新 reports.json

在 `reports` 数组最前面增加一条记录。下面是一条完整示例：

```json
{
  "id": "20270105-market-summary",
  "date": "2027-01-05",
  "year": 2027,
  "title": "2027-01-05 投资观点日报",
  "summary": "概括当日最重要的多空观点、交易动作和风险提示。",
  "file": "reports/2027/20270105_投资观点日报.html",
  "industries": ["半导体", "有色金属"],
  "tags": ["多空观点", "仓位变化"],
  "stocks": [
    { "name": "紫金矿业", "code": "601899" },
    { "name": "腾讯控股", "code": "00700" }
  ],
  "influencers": ["大 V 名称"],
  "sources": ["雪球", "微博"],
  "featured": false,
  "metrics": {}
}
```

字段维护规则：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `id` | 是 | 全站唯一且长期不变，建议使用日期加英文短名 |
| `date` | 是 | `YYYY-MM-DD` 格式，用于排序和日期搜索 |
| `year` | 否 | 可省略，脚本会从 `date` 推导 |
| `title` | 是 | 首页显示的日报标题 |
| `summary` | 否 | 建议用一至两句话概括最重要的信息 |
| `file` | 否 | 相对首页的日报路径；缺少时不会显示查看按钮 |
| `industries` | 否 | 左侧行业导航与搜索使用的分类数组 |
| `tags` | 否 | 观点类型、动作或风险标签 |
| `stocks` | 否 | 股票名称与代码对象数组；代码不确定时留空字符串 |
| `influencers` | 否 | 正文中明确出现的大 V 名称数组 |
| `sources` | 否 | 例如“雪球主贴”“雪球评论”“微博” |
| `featured` | 否 | 预留精选功能，默认 `false` |
| `metrics` | 否 | 预留阅读量、帖文数或排行指标，默认 `{}` |

不要在 `reports.json` 中保存 Cookie、登录凭证、私有接口地址或原帖正文。

### 3．运行检查

项目不需要安装 npm 包。使用 Node.js 内置测试运行：

```powershell
node --test tests/site.test.mjs
```

测试会检查数据函数、搜索筛选、首页基础结构、`reports.json` 格式、记录 ID 唯一性和日报文件路径。

### 4．本地查看并提交

启动本地 HTTP 服务，确认新增日报出现在首页，并测试股票名称、代码、大 V、标签和日期检索。确认后提交并推送到 GitHub，GitHub Pages 会自动更新。

## GitHub Pages 部署

1. 在 GitHub 新建公开仓库，例如 `investor-insight-hub`。
2. 将本项目推送到仓库的 `master` 或 `main` 分支。
3. 打开仓库的 `Settings` → `Pages`。
4. 在 `Build and deployment` 中选择 `Deploy from a branch`。
5. 选择站点分支和 `/(root)` 目录，保存设置。
6. 等待部署完成后，从 Pages 页面打开公开网址。

站点资源全部使用相对路径，因此既支持用户主页仓库，也支持普通项目仓库路径。

## URL 筛选接口

首页支持以下查询参数：

| 参数 | 用途 |
| --- | --- |
| `q` | 通用关键词 |
| `year` | 年份 |
| `industry` | 行业 |
| `tag` | 标签 |
| `stock` | 股票名称或代码 |
| `influencer` | 大 V 名称 |

例如：

```text
/?year=2026&industry=半导体&q=长鑫
```

将来增加股票页、大 V 页或标签页时，可以通过这些参数跳回已经筛选好的日报列表。

## 数据量增长后的扩展

第一版一次加载单个 `reports.json`，适合数百份以内的日报。当索引体积明显影响加载速度时，可保留一个轻量清单，再按年份拆分为 `reports/2027/reports.json` 等文件。只需替换 `loadReports()` 的数据加载实现，统计、筛选和渲染函数无需重写。

可继续扩展的页面包括股票详情、大 V 档案、标签聚合、热门排行和每月汇总。新页面应继续以 JSON 静态索引为数据边界，避免让首页逐份读取日报正文。
