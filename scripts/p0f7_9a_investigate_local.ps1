param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('BuildCollector', 'Analyze', 'StaticCheck')]
    [string]$Mode,

    [string]$Series,
    [string]$Snapshot,
    [string]$Output,
    [string]$DbName,
    [string]$Collector
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Builder = Join-Path $RepoRoot 'backend\scripts\build_p0f7_9a_curricular_allocation_snapshot_js.py'
$Analyzer = Join-Path $RepoRoot 'backend\scripts\audit_p0f7_9a_curricular_allocation_offline.py'

Write-Host 'P0-F7.9A local/offline curricular allocation forensics'
Write-Host 'PRODUCTION_ACCESS=NO'
Write-Host 'DATABASE_MUTATION=NO'
Write-Host 'STUDENT_DATA_ACCESS=NO'

if ($Mode -eq 'StaticCheck') {
    if (-not (Test-Path $Builder)) { throw "Builder not found: $Builder" }
    if (-not (Test-Path $Analyzer)) { throw "Analyzer not found: $Analyzer" }
    Write-Host 'P0F7_9A_LOCAL_WRAPPER_STATIC_CHECK=PASS'
    exit 0
}

if ([string]::IsNullOrWhiteSpace($Series)) {
    throw '-Series is required.'
}
if (-not (Test-Path $Series)) {
    throw "Series report not found: $Series"
}

if ($Mode -eq 'BuildCollector') {
    if ([string]::IsNullOrWhiteSpace($DbName)) { throw '-DbName is required for BuildCollector.' }
    if ([string]::IsNullOrWhiteSpace($Collector)) { throw '-Collector is required for BuildCollector.' }

    Write-Host "SERIES=$Series"
    Write-Host "COLLECTOR=$Collector"
    python $Builder --series $Series --db $DbName --js $Collector
    if ($LASTEXITCODE -ne 0) {
        throw "Collector build failed with exit code $LASTEXITCODE."
    }
    Write-Host 'P0F7_9A_BUILD_COLLECTOR_DONE=YES'
    exit 0
}

if ([string]::IsNullOrWhiteSpace($Snapshot)) { throw '-Snapshot is required for Analyze.' }
if ([string]::IsNullOrWhiteSpace($Output)) { throw '-Output is required for Analyze.' }
if (-not (Test-Path $Snapshot)) { throw "Snapshot not found: $Snapshot" }

Write-Host "SERIES=$Series"
Write-Host "SNAPSHOT=$Snapshot"
Write-Host "OUTPUT=$Output"
python $Analyzer --series $Series --snapshot $Snapshot --json $Output
if ($LASTEXITCODE -ne 0) {
    throw "Offline analyzer failed with exit code $LASTEXITCODE."
}
Write-Host 'P0F7_9A_LOCAL_ANALYSIS_DONE=YES'
Write-Host 'PRODUCTION_ACCESS=NO'
