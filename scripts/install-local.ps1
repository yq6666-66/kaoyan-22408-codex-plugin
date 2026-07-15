[CmdletBinding()]
param(
    [switch]$ValidateOnly
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path

& python (Join-Path $repoRoot 'scripts/check.py')
if ($LASTEXITCODE -ne 0) {
    throw 'Validation failed.'
}

if ($ValidateOnly) {
    Write-Output 'Validation completed; marketplace installation skipped.'
    exit 0
}

$codex = Get-Command codex -ErrorAction SilentlyContinue
if (-not $codex) {
    Write-Output 'Validation passed. Restart the ChatGPT desktop app and install the plugin from the repo marketplace.'
    exit 0
}

$codexHelp = (& codex --help 2>&1 | Out-String)
$pluginCommandsAvailable = $LASTEXITCODE -eq 0 -and $codexHelp -match '(?m)^\s+plugin\s'
if (-not $pluginCommandsAvailable) {
    Write-Output 'Validation passed. This Codex CLI build has no plugin subcommand; restart the ChatGPT desktop app and use the repo marketplace.'
    exit 0
}

$marketplaces = (& codex plugin marketplace list 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to list Codex marketplaces.'
}

if ($marketplaces -notmatch '(?m)^kaoyan-22408\b') {
    & codex plugin marketplace add $repoRoot
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to add the local marketplace.'
    }
}

& codex plugin add 'kaoyan-22408@kaoyan-22408'
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to install the local plugin.'
}

Write-Output 'Installed kaoyan-22408. Start a new task before testing the Skills.'
