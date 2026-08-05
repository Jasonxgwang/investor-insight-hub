# Inbox 待导入日报

把每天新生成的 HTML 日报直接放在本目录，然后在项目根目录运行：

```powershell
.\import_reports.ps1
```

脚本会识别日报日期，把文件移动到 `Reports/<年份>/`，重新生成 `reports.json` 并运行测试。

需要同时提交并推送到 GitHub 时运行：

```powershell
.\import_reports.ps1 -Publish
```

本目录中的 HTML 不会提交到 Git。解析失败或存在同名冲突时，原文件会保留在这里，脚本不会覆盖归档文件。
