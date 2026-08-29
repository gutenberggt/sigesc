param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('StaticCheck','Build','Simulate')]
    [string]$Mode,

    [string]$Plan,
    [string]$D5Report,
    [string]$D5Snapshot,
    [string]$Package,
    [string]$Output
)

$ErrorActionPreference = 'Stop'

Write-Host 'P0-F7.9D6 local/offline CAS dry-run'
Write-Host 'PRODUCTION_ACCESS=NO'
Write-Host 'DATABASE_MUTATION=NO'
Write-Host 'PRODUCTION_WRITES=NO'
Write-Host 'REMEDIATION_EXECUTED=NO'

if ($Mode -eq 'StaticCheck') {
    $Builder = '.\backend\scripts\build_p0f7_9d6_cas_dry_run_package.py'
    $Simulator = '.\backend\scripts\simulate_p0f7_9d6_cas_dry_run.py'
    if (-not (Test-Path $Builder)) { throw 'D6_BUILDER_NOT_FOUND' }
    if (-not (Test-Path $Simulator)) { throw 'D6_SIMULATOR_NOT_FOUND' }
    Write-Host 'P0F7_9D6_LOCAL_WRAPPER_STATIC_CHECK=PASS'
    return
}

if ($Mode -eq 'Build') {
    if (-not $Plan -or -not $D5Report -or -not $Package) { throw 'D6_BUILD_ARGS_REQUIRED' }
    python .\backend\scripts\build_p0f7_9d6_cas_dry_run_package.py `
        --plan $Plan `
        --d5-report $D5Report `
        --json $Package
    if ($LASTEXITCODE -ne 0) { throw "D6_BUILDER_FAILED=$LASTEXITCODE" }
    Write-Host 'P0F7_9D6_LOCAL_BUILD_DONE=YES'
    Write-Host "PACKAGE=$Package"
    return
}

if ($Mode -eq 'Simulate') {
    if (-not $Package -or -not $D5Snapshot -or -not $Output) { throw 'D6_SIMULATE_ARGS_REQUIRED' }
    python .\backend\scripts\simulate_p0f7_9d6_cas_dry_run.py `
        --package $Package `
        --snapshot $D5Snapshot `
        --json $Output
    if ($LASTEXITCODE -ne 0) { throw "D6_SIMULATOR_FAILED=$LASTEXITCODE" }
    Write-Host 'P0F7_9D6_LOCAL_SIMULATION_DONE=YES'
    Write-Host "REPORT=$Output"
    Write-Host 'PRODUCTION_ACCESS=NO'
    Write-Host 'DATABASE_MUTATION=NO'
    Write-Host 'PRODUCTION_WRITES=NO'
    Write-Host 'REMEDIATION_EXECUTED=NO'
    return
}
