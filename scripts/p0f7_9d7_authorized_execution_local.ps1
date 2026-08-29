param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('StaticCheck','Build')]
    [string]$Mode,

    [string]$Plan,
    [string]$D5Report,
    [string]$D6Package,
    [string]$D6Report,
    [string]$D71Report,
    [string]$Executor,
    [string]$DbName = 'sigesc',
    [switch]$AuthorizeProductionWrites
)

$ErrorActionPreference = 'Stop'

Write-Host 'P0-F7.9D7 authorized production CAS executor builder'
Write-Host 'WRITER_EXECUTION_BY_WRAPPER=NO'
Write-Host 'EXPECTED_FORWARD_WRITES=23'
Write-Host 'STRATEGY=CAS_WITH_COMPENSATING_ROLLBACK_REQUIRED'
Write-Host 'D71_INTRA_BATCH_GATE=REQUIRED'

if ($Mode -eq 'StaticCheck') {
    $Builder = '.\backend\scripts\build_p0f7_9d7_authorized_executor_js.py'
    $D71Analyzer = '.\backend\scripts\analyze_p0f7_9d71_intra_batch_collisions.py'
    if (-not (Test-Path $Builder)) { throw 'D7_BUILDER_NOT_FOUND' }
    if (-not (Test-Path $D71Analyzer)) { throw 'D71_ANALYZER_NOT_FOUND' }
    Write-Host 'P0F7_9D7_LOCAL_WRAPPER_STATIC_CHECK=PASS'
    return
}

if ($Mode -eq 'Build') {
    if (-not $Plan -or -not $D5Report -or -not $D6Package -or -not $D6Report -or -not $D71Report -or -not $Executor) {
        throw 'D7_BUILD_ARGS_REQUIRED'
    }
    if (-not $AuthorizeProductionWrites) {
        throw 'D7_EXPLICIT_PRODUCTION_WRITE_AUTHORIZATION_REQUIRED'
    }

    $PlanObj = Get-Content -Raw -Encoding UTF8 $Plan | ConvertFrom-Json
    $D71 = Get-Content -Raw -Encoding UTF8 $D71Report | ConvertFrom-Json

    if ($D71.phase -ne 'P0F7.9D7.1-INTRA-BATCH-COLLISION-PREFLIGHT-2026' -or $D71.status -ne 'PASS') {
        throw 'D71_REPORT_INVALID'
    }
    if ($D71.sealed_plan_sha256 -ne $PlanObj.plan_sha256) {
        throw 'D71_PLAN_CHAIN_MISMATCH'
    }
    if (
        $D71.summary.entries -ne 23 -or
        $D71.summary.safe_noncolliding -ne 23 -or
        $D71.summary.blocked_intra_batch -ne 0 -or
        $D71.summary.collision_groups -ne 0 -or
        $D71.summary.execution_gate_open -ne $true
    ) {
        throw 'D71_INTRA_BATCH_COLLISION_GATE_CLOSED'
    }

    python .\backend\scripts\build_p0f7_9d7_authorized_executor_js.py `
        --plan $Plan `
        --d5-report $D5Report `
        --d6-package $D6Package `
        --d6-report $D6Report `
        --db $DbName `
        --js $Executor `
        --authorize-production-writes

    if ($LASTEXITCODE -ne 0) { throw "D7_BUILDER_FAILED=$LASTEXITCODE" }
    Write-Host 'P0F7_9D7_LOCAL_BUILD_DONE=YES'
    Write-Host "EXECUTOR=$Executor"
    Write-Host 'D71_INTRA_BATCH_GATE=OPEN'
    Write-Host 'EXECUTION_NOT_PERFORMED=YES'
    return
}
