# Investor Insight Hub 投资观点库

用于长期归档、分类和检索雪球与微博大 V 投资观点日报的纯静态网站。网站运行时只有 HTML、CSS、JavaScript 和 JSON，可直接部署到 GitHub Pages，不需要数据库或服务器。

## 每日维护：一分钟流程

### 推荐方式：本地一键导入并发布

1. 把新生成的 HTML 日报放入 `Inbox/`。
2. 在项目根目录运行：

```powershell
.\import_reports.ps1 -Publish
```

脚本会自动完成：

- 解析日期、标题、摘要、股票、大 V、行业、标签和来源。
- 按日期年份移动到 `Reports/<年份>/`。
- 全量重建并校验 `reports.json`。
- 运行 Python 解析测试和 Node.js 首页测试。
- 在工作区干净时提交并推送 GitHub。

只想先在本地检查，不提交 GitHub 时运行：

```powershell
.\import_reports.ps1
```

### 备用方式：直接在 GitHub 上传

1. 打开仓库中的 `Reports/<年份>/`，例如 `Reports/2027/`。
2. 点击 `Add file` → `Upload files`，上传 HTML 并提交。
3. GitHub Actions 自动扫描全部日报、更新 `reports.json` 并运行测试。
4. GitHub Pages 随默认分支更新，不需要手工编辑 JSON。

GitHub Pages 不能在浏览器运行时枚举服务器目录，因此目录扫描发生在本地脚本或 GitHub Actions 中；线上首页仍然是纯静态页面。

## 目录结构

```text
Investor Insight Hub/
├─ Inbox/                         # 本地待导入日报，HTML 不提交到 Git
├─ Reports/
│  ├─ 2026/
│  ├─ 2027/
│  └─ ...                         # 脚本按日期自动创建年份目录
├─ data/
│  ├─ entities.json               # 股票、大 V、行业、标签和来源词典
│  └─ report-overrides.json       # 少量历史日报的人工校准元数据
├─ tools/
│  └─ build_reports_index.py      # HTML 解析与确定性索引生成器
├─ .github/workflows/
│  └─ update-reports.yml          # GitHub 端自动重建和校验
├─ tests/
│  ├─ site.test.mjs               # 首页、搜索、统计和路径测试
│  ├─ test_report_import.py       # 解析、归档和索引测试
│  └─ test_workflow_config.py     # GitHub Actions 契约测试
├─ import_reports.ps1             # Windows 一键导入入口
├─ reports.json                   # 首页唯一日报索引
├─ index.html
├─ style.css
└─ script.js
```

## 自动解析规则

解析器按稳定优先级提取元数据：

| 字段 | 识别顺序 |
| --- | --- |
| 日期 | `report:date` → 文件名日期 → `<title>`、`<h1>` 和正文前部日期 |
| 标题 | `report:title` → `<title>` → `<h1>` → 清理后的文件名 |
| 摘要 | `report:summary` 或 `description` → “核心结论”等章节 → 第一段有效正文 |
| 股票 | `report:stocks` → 股票表格列 → 受控股票别名词典 |
| 大 V | `report:influencers` → 作者表格列 → 作者文本模式和别名词典 |
| 标签、行业 | 显式元数据 → 受控关键词评分，避免产生大量近义分类 |
| 来源 | `report:sources` → 雪球、微博等受控关键词 |

文件缺少可识别日期时会停止导入，并把原 HTML 留在 `Inbox/`。同名归档文件存在时不会覆盖；内容冲突会明确报错。

## 推荐的 HTML 元数据

现有格式可以直接自动解析。为了让以后 AI 生成的日报达到更高准确率，建议在 `<head>` 中加入：

```html
<meta name="report:date" content="2027-01-05">
<meta name="report:title" content="大 V 多空观点与交易动作总结">
<meta name="report:summary" content="本期最重要的观点、动作和风险摘要。">
<meta name="report:tags" content="多空观点,仓位变化,风险提示">
<meta name="report:industries" content="半导体,有色金属">
<meta name="report:stocks" content="紫金矿业|601899;腾讯控股|00700">
<meta name="report:influencers" content="飞翔芸;挖地瓜的超级鹿鼎公">
<meta name="report:sources" content="雪球,微博">
```

这些字段不是必填项。存在时会覆盖启发式结果，但不会改变日报正文和视觉样式。

## 首页统计与搜索

首页每次加载 `reports.json` 后自动计算：

- 日报总数。
- 最近更新日期。
- 去重后的覆盖股票数。
- 去重后的大 V 数。

搜索框支持标题、摘要、日期、股票代码、股票名称、大 V 姓名、标签、行业和来源。左侧导航支持按年份和行业过滤；多个条件使用交集筛选。

支持的 URL 参数：

| 参数 | 用途 |
| --- | --- |
| `q` | 通用关键词 |
| `year` | 年份 |
| `industry` | 行业 |
| `tag` | 标签 |
| `stock` | 股票名称或代码 |
| `influencer` | 大 V 名称 |

## 本地预览

浏览器直接使用 `file://` 打开 `index.html` 时通常不能读取 `reports.json`。请在项目根目录启动静态服务：

```powershell
python -m http.server 8765 --bind 127.0.0.1
```

然后访问：

```text
http://127.0.0.1:8765/
```

## 手工检查与测试

只重建索引：

```powershell
python tools/build_reports_index.py --root . --write
```

检查索引是否最新，不修改文件：

```powershell
python tools/build_reports_index.py --root . --check
```

运行全部测试：

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
node --test tests/site.test.mjs
```

项目不依赖 npm 包或 Python 第三方库。

## 失败恢复

- **无法识别日期**：把 `YYYYMMDD` 加到文件名前部，或加入 `report:date` 元数据。
- **同名文件冲突**：原文件仍在 `Inbox/`；确认内容后改名或删除重复文件，不要覆盖归档。
- **摘要使用默认文字**：在 HTML 加入 `report:summary`，或使用“核心结论”章节。
- **股票或大 V 未识别**：优先在 HTML 加显式元数据；长期使用的别名可加入 `data/entities.json`。
- **Git 工作区不干净**：先提交或处理其他改动，再运行 `-Publish`，避免误提交无关文件。
- **GitHub Actions 失败**：在仓库 `Actions` 页面查看“更新投资日报索引”日志；失败不会替换已有有效索引。

解析器和索引日志只输出文件名、归档路径、数量、警告和错误原因，不输出 Cookie 或日报正文。

## 数据维护边界

`data/entities.json` 使用受控分类，负责规范股票别名、大 V 别名、行业、标签和来源。新增长期出现的实体时，沿用现有数组结构添加一条记录即可。

`data/report-overrides.json` 只用于保存历史日报的人工校准结果。正常新日报不需要修改；优先改进 HTML 元数据或通用解析规则。

## 扩展接口

所有后续页面都应消费 `reports.json` 中统一记录，而不是重新解析 HTML：

- 股票页面使用 `stocks[].code` 和 `stocks[].name` 聚合。
- 大 V 页面使用 `influencers[]` 聚合。
- 标签页面使用 `tags[]` 聚合。
- 热门排行可以读取预留的 `metrics`。
- 观点时间线可以组合日期、股票和大 V 条件。
- 月度汇总可以由生成器输出独立静态 JSON。

数据量显著增长后，可由生成器增加年度分片索引，同时保持首页数据访问接口不变。

## GitHub Pages

当前仓库从 `master` 分支根目录部署 GitHub Pages。所有资源都使用相对路径，并严格保留 `Reports` 的大小写，因此既支持项目仓库 Pages 路径，也支持本地静态预览。
