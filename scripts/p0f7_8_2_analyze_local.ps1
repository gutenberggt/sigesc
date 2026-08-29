[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Series,

    [Parameter(Mandatory = $true)]
    [string]$Snapshot,

    [string]$Output,
    [string]$PythonCommand = "python",
    [switch]$StaticCheck
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Analyzer = Join-Path $RepoRoot "backend/scripts/audit_p0f7_8_2_offline_snapshot.py"

if ($StaticCheck) {
    if (-not (Test-Path $Analyzer -PathType Leaf)) {
        throw "Offline analyzer not found: $Analyzer"
    }
    Write-Output "P0F7_8_2_LOCAL_WRAPPER_STATIC_CHECK=PASS"
    Write-Output "PRODUCTION_ACCESS=NO"
    exit 0
}

if (-not (Test-Path $Series -PathType Leaf)) {
    throw "P0-F7.5 report not found: $Series"
}
if (-not (Test-Path $Snapshot -PathType Leaf)) {
    throw "Minimal snapshot not found: $Snapshot"
}
if (-not (Test-Path $Analyzer -PathType Leaf)) {
    throw "Offline analyzer not found: $Analyzer"
}

if ([string]::IsNullOrWhiteSpace($Output)) {
    $Output = Join-Path (Split-Path -Parent (Resolve-Path $Snapshot)) "p0f7_8_2-offline-report.json"
}

Write-Output "P0-F7.8.2 local/offline analysis"
Write-Output "PRODUCTION_ACCESS=NO"
Write-Output "SERIES=$Series"
Write-Output "SNAPSHOT=$Snapshot"
Write-Output "OUTPUT=$Output"

& $PythonCommand $Analyzer --series $Series --snapshot $Snapshot --json $Output
if ($LASTEXITCODE -ne 0) {
    throw "Offline analyzer failed with exit code $LASTEXITCODE."
}

Write-Output "P0F7_8_2_LOCAL_ANALYSIS_DONE=YES"
Write-Output "REPORT=$Output"
