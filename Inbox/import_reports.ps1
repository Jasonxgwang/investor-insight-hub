[CmdletBinding()]
param(
    [switch]$Publish
)

$rootScript = Join-Path (Split-Path -Parent $PSScriptRoot) "import_reports.ps1"

if ($Publish) {
    & $rootScript -Publish
} else {
    & $rootScript
}
