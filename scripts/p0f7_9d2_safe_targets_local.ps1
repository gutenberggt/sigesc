param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('StaticCheck','Analyze')]
    [string]$Mode,

    [string]$Audit = 'C:\SIGESC\private\p0f7_9c1\p0f7_9c1-network-audit.json',
    [string]$Reference = 'C:\SIGESC\private\p0f7_9c1\p0f7_9c1-reference.json',
    [string]$PagesDir = 'C:\SIGESC\private\p0f7_9c1\pages',
    [string]$Output = 'C:\SIGESC\private\p0f7_9d2\p0f7_9d2-safe-targets.json'
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Analyzer = Join-Path $Root 'backend\scripts\audit_p0f7_9d2_safe_targets_offline.py'

Write-Host 'P0-F7.9D2 local/offline safe-target resolution'
Write-Host 'PRODUCTION_ACCESS=NO'
Write-Host 'DATABASE_MUTATION=NO'
Write-Host 'REMEDIATION_EXECUTED=NO'

if ($Mode -eq 'StaticCheck') {
    if (-not (Test-Path $Analyzer)) { throw "ANALYZER_NOT_FOUND=$Analyzer" }
    Write-Host 'P0F7_9D2_LOCAL_WRAPPER_STATIC_CHECK=PASS'
    exit 0
}

foreach ($Path in @($Audit, $Reference)) {
    if (-not (Test-Path $Path)) { throw "INPUT_NOT_FOUND=$Path" }
}
if (-not (Test-Path $PagesDir)) { throw "PAGES_DIR_NOT_FOUND=$PagesDir" }
$parent = Split-Path -Parent $Output
if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }

python $Analyzer --audit $Audit --reference $Reference --pages-dir $PagesDir --json $Output
if ($LASTEXITCODE -ne 0) { throw "ANALYZER_FAILED=$LASTEXITCODE" }

Write-Host 'P0F7_9D2_LOCAL_ANALYSIS_DONE=YES'
Write-Host "REPORT=$Output"
Write-Host 'PRODUCTION_ACCESS=NO'
Write-Host 'DATABASE_MUTATION=NO'
Write-Host 'REMEDIATION_EXECUTED=NO'
