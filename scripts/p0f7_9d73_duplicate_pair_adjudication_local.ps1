param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('StaticCheck','Build','Seal')]
    [string]$Mode,

    [string]$Plan,
    [string]$D71Report,
    [string]$D72Report,
    [string]$Html,
    [string]$Template,
    [string]$Decision,
    [string]$Output
)

$ErrorActionPreference = 'Stop'

Write-Host 'P0-F7.9D7.3 duplicate-pair adjudication'
Write-Host 'PRODUCTION_ACCESS=NO'
Write-Host 'DATABASE_MUTATION=NO'
Write-Host 'PRODUCTION_WRITES=NO'
Write-Host 'EXECUTOR_AUTHORIZED=NO'

$Script = '.\backend\scripts\adjudicate_p0f7_9d73_duplicate_pair.py'

if ($Mode -eq 'StaticCheck') {
    if (-not (Test-Path $Script)) {
        throw 'D73_SCRIPT_NOT_FOUND'
    }

    $Body = Get-Content -Raw -Encoding UTF8 $Script
    if ($Body -match '(^|[\s])(ssh|scp|docker|mongosh)([\s]|$)') {
        throw 'D73_REMOTE_EXECUTION_SURFACE_DETECTED'
    }
    if ($Body -match '\-\-apply|\-\-execute|\-\-rollback') {
        throw 'D73_EXECUTOR_SWITCH_DETECTED'
    }

    python -m py_compile $Script
    if ($LASTEXITCODE -ne 0) {
        throw "D73_COMPILE_FAILED=$LASTEXITCODE"
    }

    Write-Host 'P0F7_9D73_LOCAL_WRAPPER_STATIC_CHECK=PASS'
    return
}

if ($Mode -eq 'Build') {
    if (-not $Plan -or -not $D71Report -or -not $D72Report -or -not $Html -or -not $Template) {
        throw 'D73_BUILD_ARGS_REQUIRED'
    }

    python $Script build `
        --plan $Plan `
        --d71-report $D71Report `
        --d72-report $D72Report `
        --html $Html `
        --template-json $Template

    if ($LASTEXITCODE -ne 0) {
        throw "D73_BUILD_FAILED=$LASTEXITCODE"
    }

    Write-Host 'P0F7_9D73_LOCAL_BUILD_DONE=YES'
    Write-Host "HTML=$Html"
    Write-Host "TEMPLATE=$Template"
    return
}

if ($Mode -eq 'Seal') {
    if (-not $Plan -or -not $D71Report -or -not $D72Report -or -not $Decision -or -not $Output) {
        throw 'D73_SEAL_ARGS_REQUIRED'
    }

    python $Script seal `
        --plan $Plan `
        --d71-report $D71Report `
        --d72-report $D72Report `
        --decision $Decision `
        --json $Output

    if ($LASTEXITCODE -ne 0) {
        throw "D73_SEAL_FAILED=$LASTEXITCODE"
    }

    Write-Host 'P0F7_9D73_LOCAL_SEAL_DONE=YES'
    Write-Host "REPORT=$Output"
    return
}
