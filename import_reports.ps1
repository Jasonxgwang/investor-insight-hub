[CmdletBinding()]
param(
    [switch]$Publish
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# 统一子进程和控制台编码，确保中文日志在 Windows PowerShell 5 中可读。
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom
$env:PYTHONIOENCODING = "utf-8"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectRoot

function Resolve-PythonCommand {
    # 优先使用系统 Python；Codex 桌面环境没有加入 PATH 时使用其内置运行时。
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return [PSCustomObject]@{ File = $python.Source; Prefix = @() }
    }

    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        return [PSCustomObject]@{ File = $launcher.Source; Prefix = @("-3") }
    }

    $bundled = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path -LiteralPath $bundled) {
        return [PSCustomObject]@{ File = $bundled; Prefix = @() }
    }

    throw "未找到 Python 3。请安装 Python 3 后重新运行。"
}

function Resolve-NodeCommand {
    # Node.js 只用于执行首页回归测试，不参与网站线上运行。
    $node = Get-Command node -ErrorAction SilentlyContinue
    if ($node) {
        return $node.Source
    }

    $bundled = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
    if (Test-Path -LiteralPath $bundled) {
        return $bundled
    }

    throw "未找到 Node.js。请安装 Node.js 18 或更高版本后重新运行。"
}

function Invoke-Python {
    param([Parameter(Mandatory)][string[]]$Arguments)

    & $script:PythonCommand.File @($script:PythonCommand.Prefix) @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python 命令执行失败，退出代码：$LASTEXITCODE"
    }
}

function Normalize-GitProxy {
    param([string]$Proxy)

    if ([string]::IsNullOrWhiteSpace($Proxy)) {
        return $null
    }

    $value = $Proxy.Trim()
    if ($value.Contains(";")) {
        $parts = @($value -split ";" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
        $https = $parts | Where-Object { $_ -like "https=*" } | Select-Object -First 1
        $http = $parts | Where-Object { $_ -like "http=*" } | Select-Object -First 1
        if ($https) {
            $value = $https
        } elseif ($http) {
            $value = $http
        } elseif ($parts.Count -gt 0) {
            $value = $parts[0]
        }
    }

    $value = $value -replace "^(https?|socks5?)=", ""
    if ($value -notmatch "^[a-z]+://") {
        $value = "http://$value"
    }

    return $value
}

function Add-GitProxyCandidate {
    param(
        [System.Collections.ArrayList]$Candidates,
        [System.Collections.Generic.HashSet[string]]$Seen,
        [Parameter(Mandatory)][string]$Label,
        [string]$Proxy
    )

    $normalized = Normalize-GitProxy -Proxy $Proxy
    if (-not $normalized) {
        return
    }

    if ($Seen.Add($normalized)) {
        [void]$Candidates.Add([PSCustomObject]@{
            Label = "$Label $normalized"
            Args = @("-c", "http.https://github.com.proxy=$normalized")
        })
    }
}

function Get-GitHubPushArgs {
    param([Parameter(Mandatory)][string]$Branch)

    $candidates = New-Object System.Collections.ArrayList
    $seen = New-Object "System.Collections.Generic.HashSet[string]"

    [void]$candidates.Add([PSCustomObject]@{
        Label = "直连"
        Args = @("-c", "http.https://github.com.proxy=")
    })

    $repoProxy = git config --get http.https://github.com.proxy
    if ($LASTEXITCODE -eq 0) {
        Add-GitProxyCandidate -Candidates $candidates -Seen $seen -Label "仓库代理" -Proxy $repoProxy
    }

    $internetSettings = Get-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings" -ErrorAction SilentlyContinue
    if ($internetSettings -and $internetSettings.ProxyEnable -eq 1) {
        Add-GitProxyCandidate -Candidates $candidates -Seen $seen -Label "系统代理" -Proxy $internetSettings.ProxyServer
    }

    foreach ($port in @(7897, 7890, 7899, 10809, 1080)) {
        $listening = Get-NetTCPConnection -State Listen -LocalAddress 127.0.0.1 -LocalPort $port -ErrorAction SilentlyContinue
        if ($listening) {
            Add-GitProxyCandidate -Candidates $candidates -Seen $seen -Label "本地代理" -Proxy "127.0.0.1:$port"
        }
    }

    $timeoutArgs = @("-c", "http.lowSpeedLimit=1", "-c", "http.lowSpeedTime=8")
    foreach ($candidate in $candidates) {
        Write-Host "检查 GitHub 连接：$($candidate.Label)..."
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            & git @timeoutArgs @($candidate.Args) ls-remote --heads origin $Branch > $null 2> $null
            $probeExitCode = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
        if ($probeExitCode -eq 0) {
            Write-Host "使用 GitHub 连接：$($candidate.Label)"
            return @($candidate.Args)
        }
    }

    throw "无法连接 GitHub。已尝试直连、系统代理和常见本地代理端口；本地提交已保留，可切换 VPN 后重新运行。"
}

if ($Publish) {
    # 发布前要求工作区干净，避免把与日报导入无关的用户文件一起提交。
    $existingChanges = @(git status --porcelain --untracked-files=all)
    if ($LASTEXITCODE -ne 0) {
        throw "无法读取 Git 工作区状态。"
    }
    if ($existingChanges.Count -gt 0) {
        throw "检测到与 Inbox 输入无关的 Git 改动。请先提交或处理这些改动，再运行 -Publish。"
    }

    $branch = (git branch --show-current).Trim()
    if ($branch -notin @("master", "main")) {
        throw "自动发布只允许在 master 或 main 分支执行；当前分支：$branch"
    }
}

$script:PythonCommand = Resolve-PythonCommand
$nodeCommand = Resolve-NodeCommand

Write-Host "[1/3] 扫描 Inbox、归档 HTML 并更新 reports.json..."
Invoke-Python -Arguments @("tools/build_reports_index.py", "--root", ".", "--import-inbox", "--write")

Write-Host "[2/3] 运行 Python 自动导入测试..."
Invoke-Python -Arguments @("-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v")

Write-Host "[3/3] 运行静态首页测试..."
& $nodeCommand --test tests/site.test.mjs
if ($LASTEXITCODE -ne 0) {
    throw "静态首页测试失败，退出代码：$LASTEXITCODE"
}

if (-not $Publish) {
    Write-Host "导入与测试完成。确认页面后，可运行 .\import_reports.ps1 -Publish 发布。"
    exit 0
}

# 只暂存归档目录和索引，不使用 git add -A。
git add -- Reports reports.json
if ($LASTEXITCODE -ne 0) {
    throw "无法暂存日报归档和索引。"
}

git diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Host "没有需要发布的新日报。"
    exit 0
}

$index = Get-Content -LiteralPath "reports.json" -Raw -Encoding UTF8 | ConvertFrom-Json
$latestDate = $index.site.updatedAt
git commit -m "content: import reports through $latestDate"
if ($LASTEXITCODE -ne 0) {
    throw "无法提交日报更新。"
}

$gitHubArgs = Get-GitHubPushArgs -Branch $branch
git @gitHubArgs push origin $branch
if ($LASTEXITCODE -ne 0) {
    throw "Git 推送失败；本地提交已保留，可排查网络后重新推送。"
}

Write-Host "日报已推送到 GitHub，GitHub Pages 将自动更新。"
