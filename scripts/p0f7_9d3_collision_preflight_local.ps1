param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('StaticCheck','Build','Analyze')]
    [string]$Mode,

    [string]$D2Report,
    [string]$Collector,
    [string]$Snapshot,
    [string]$Output,
    [string]$DbName = 'sigesc'
)

$ErrorActionPreference = 'Stop'

Write-Host 'P0-F7.9D3 local/offline collision preflight'
Write-Host 'DATABASE_MUTATION=NO'
Write-Host 'REMEDIATION_EXECUTED=NO'

if ($Mode -eq 'StaticCheck') {
    $Builder = '.\backend\scripts\build_p0f7_9d3_collision_snapshot_js.py'
    $Analyzer = '.\backend\scripts\audit_p0f7_9d3_collision_preflight_offline.py'
    if (-not (Test-Path $Builder)) { throw 'D3_BUILDER_NOT_FOUND' }
    if (-not (Test-Path $Analyzer)) { throw 'D3_ANALYZER_NOT_FOUND' }
    if (Select-String -Path $Analyzer -Pattern 'pymongo|motor|mongosh|docker exec|ssh |requests\.|httpx\.' -Quiet) {
        throw 'D3_ANALYZER_MUST_BE_OFFLINE_ONLY'
    }
    Write-Host 'P0F7_9D3_LOCAL_WRAPPER_STATIC_CHECK=PASS'
    return
}

if ($Mode -eq 'Build') {
    if (-not $D2Report -or -not $Collector) { throw 'D3_BUILD_ARGS_REQUIRED' }
    python .\backend\scripts\build_p0f7_9d3_collision_snapshot_js.py `
        --d2-report $D2Report `
        --db $DbName `
        --js $Collector
    if ($LASTEXITCODE -ne 0) { throw "D3_BUILDER_FAILED=$LASTEXITCODE" }
    Write-Host 'P0F7_9D3_LOCAL_BUILD_DONE=YES'
    Write-Host "COLLECTOR=$Collector"
    return
}

if ($Mode -eq 'Analyze') {
    if (-not $D2Report -or -not $Snapshot -or -not $Output) { throw 'D3_ANALYZE_ARGS_REQUIRED' }
    python .\backend\scripts\audit_p0f7_9d3_collision_preflight_offline.py `
        --d2-report $D2Report `
        --snapshot $Snapshot `
        --json $Output
    if ($LASTEXITCODE -ne 0) { throw "D3_ANALYZER_FAILED=$LASTEXITCODE" }
    Write-Host 'P0F7_9D3_LOCAL_ANALYSIS_DONE=YES'
    Write-Host 'PRODUCTION_ACCESS=NO'
    Write-Host 'DATABASE_MUTATION=NO'
    Write-Host 'REMEDIATION_EXECUTED=NO'
    return
}
