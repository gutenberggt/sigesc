param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('StaticCheck','Analyze')]
    [string]$Mode,

    [string]$Plan,
    [string]$D5Snapshot,
    [string]$Output
)

$ErrorActionPreference = 'Stop'

Write-Host 'P0-F7.9D7.1 local/offline intra-batch collision preflight'
Write-Host 'PRODUCTION_ACCESS=NO'
Write-Host 'DATABASE_MUTATION=NO'
Write-Host 'PRODUCTION_WRITES=NO'
Write-Host 'REMEDIATION_EXECUTED=NO'

if ($Mode -eq 'StaticCheck') {
    $Analyzer = '.\backend\scripts\analyze_p0f7_9d71_intra_batch_collisions.py'
    if (-not (Test-Path $Analyzer)) { throw 'D71_ANALYZER_NOT_FOUND' }
    Write-Host 'P0F7_9D71_LOCAL_WRAPPER_STATIC_CHECK=PASS'
    return
}

if ($Mode -eq 'Analyze') {
    if (-not $Plan -or -not $D5Snapshot -or -not $Output) {
        throw 'D71_ANALYZE_ARGS_REQUIRED'
    }

    python .\backend\scripts\analyze_p0f7_9d71_intra_batch_collisions.py `
        --plan $Plan `
        --d5-snapshot $D5Snapshot `
        --json $Output

    if ($LASTEXITCODE -ne 0) { throw "D71_ANALYZER_FAILED=$LASTEXITCODE" }
    Write-Host 'P0F7_9D71_LOCAL_ANALYSIS_DONE=YES'
    Write-Host "REPORT=$Output"
    return
}
