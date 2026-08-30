param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('StaticCheck','Seal')]
    [string]$Mode,

    [string]$SealedReport,
    [string]$D74Report,
    [string]$Output
)

$ErrorActionPreference = 'Stop'

Write-Host 'P0-F7.9D7.5 sealed revised executor manifest'
Write-Host 'PRODUCTION_ACCESS=NO'
Write-Host 'DATABASE_MUTATION=NO'
Write-Host 'PRODUCTION_WRITES=NO'
Write-Host 'EXECUTOR_AUTHORIZED=NO'
Write-Host 'EXECUTOR_MATERIALIZED=NO'
Write-Host 'WRITER_IMPLEMENTATION_PRESENT=NO'
Write-Host 'REMEDIATION_EXECUTED=NO'

$Script = '.\backend\scripts\seal_p0f7_9d75_revised_executor_manifest.py'

if ($Mode -eq 'StaticCheck') {
    if (-not (Test-Path $Script)) { throw 'D75_SEALER_NOT_FOUND' }
    python -m py_compile $Script
    if ($LASTEXITCODE -ne 0) { throw "D75_COMPILE_FAILED=$LASTEXITCODE" }
    python $Script --help | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "D75_CLI_IMPORT_FAILED=$LASTEXITCODE" }
    Write-Host 'P0F7_9D75_LOCAL_WRAPPER_STATIC_CHECK=PASS'
    Write-Host 'P0F7_9D75_CLI_IMPORT_CHECK=PASS'
    return
}

if ($Mode -eq 'Seal') {
    if (-not $SealedReport -or -not $D74Report -or -not $Output) {
        throw 'D75_SEAL_ARGS_REQUIRED'
    }
    if (-not (Test-Path $SealedReport)) { throw 'D75_SEALED_REPORT_NOT_FOUND' }
    if (-not (Test-Path $D74Report)) { throw 'D75_D74_REPORT_NOT_FOUND' }

    python $Script `
        --sealed-report $SealedReport `
        --d74-report $D74Report `
        --json $Output

    if ($LASTEXITCODE -ne 0) { throw "D75_SEALER_FAILED=$LASTEXITCODE" }
    Write-Host 'P0F7_9D75_LOCAL_SEAL_DONE=YES'
    Write-Host "MANIFEST=$Output"
    Write-Host 'EXECUTION_NOT_PERFORMED=YES'
    return
}
