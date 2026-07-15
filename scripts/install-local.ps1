[CmdletBinding()]
param(
    [switch]$ValidateOnly
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$installer = Join-Path $repoRoot 'scripts/install_local.py'
$python = Get-Command python3 -ErrorAction SilentlyContinue
if (-not $python) {
    $python = Get-Command python -ErrorAction SilentlyContinue
}
if (-not $python) {
    Write-Error 'Python 3 was not found on PATH.'
    exit 1
}

$arguments = @($installer)
if ($ValidateOnly) {
    $arguments += '--validate-only'
}

& $python.Source @arguments
exit [int]$LASTEXITCODE
