param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('StaticCheck','Build','Analyze')]
    [string]$Mode,

    [string]$Plan,
    [string]$Collector,
    [string]$Snapshot,
    [string]$Output,
    [string]$DbName = 'sigesc'
)

$ErrorActionPreference = 'Stop'

Write-Host 'P0-F7.9D5 local/offline last-mile execution preflight'
Write-Host 'DATABASE_MUTATION=NO'
Write-Host 'PRODUCTION_WRITES=NO'
Write-Host 'REMEDIATION_EXECUTED=NO'

if ($Mode -eq 'StaticCheck') {
    $Builder = '.\backend\scripts\build_p0f7_9d5_last_mile_snapshot_js.py'
    $Analyzer = '.\backend\scripts\audit_p0f7_9d5_last_mile_preflight_offline.py'
    if (-not (Test-Path $Builder)) { throw 'D5_BUILDER_NOT_FOUND' }
    if (-not (Test-Path $Analyzer)) { throw 'D5_ANALYZER_NOT_FOUND' }
    Write-Host 'P0F7_9D5_LOCAL_WRAPPER_STATIC_CHECK=PASS'
    return
}

if ($Mode -eq 'Build') {
    if (-not $Plan -or -not $Collector) { throw 'D5_BUILD_ARGS_REQUIRED' }
    python .\backend\scripts\build_p0f7_9d5_last_mile_snapshot_js.py `
        --plan $Plan `
        --db $DbName `
        --js $Collector
    if ($LASTEXITCODE -ne 0) { throw "D5_BUILDER_FAILED=$LASTEXITCODE" }
    Write-Host 'P0F7_9D5_LOCAL_BUILD_DONE=YES'
    Write-Host "COLLECTOR=$Collector"
    return
}

if ($Mode -eq 'Analyze') {
    if (-not $Plan -or -not $Snapshot -or -not $Output) { throw 'D5_ANALYZE_ARGS_REQUIRED' }
    python .\backend\scripts\audit_p0f7_9d5_last_mile_preflight_offline.py `
        --plan $Plan `
        --snapshot $Snapshot `
        --json $Output
    if ($LASTEXITCODE -ne 0) { throw "D5_ANALYZER_FAILED=$LASTEXITCODE" }
    Write-Host 'P0F7_9D5_LOCAL_ANALYSIS_DONE=YES'
    Write-Host 'PRODUCTION_ACCESS=NO'
    Write-Host 'DATABASE_MUTATION=NO'
    Write-Host 'PRODUCTION_WRITES=NO'
    Write-Host 'REMEDIATION_EXECUTED=NO'
    return
}
