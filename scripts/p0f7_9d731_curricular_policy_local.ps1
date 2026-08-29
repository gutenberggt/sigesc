param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('StaticCheck','Build','Seal')]
    [string]$Mode,

    [string]$Plan,
    [string]$D71Report,
    [string]$D72Report,
    [string]$Html,
    [string]$Template,
    [string]$Policy,
    [string]$Decision,
    [string]$Output
)

$ErrorActionPreference = 'Stop'

Write-Host 'P0-F7.9D7.3.1 curricular workload policy'
Write-Host 'PRODUCTION_ACCESS=NO'
Write-Host 'DATABASE_MUTATION=NO'
Write-Host 'PRODUCTION_WRITES=NO'
Write-Host 'EXECUTOR_AUTHORIZED=NO'

$Script = '.\backend\scripts\adjudicate_p0f7_9d731_curricular_policy.py'
$BackendPath = (Resolve-Path '.\backend').Path
$PreviousPythonPath = $env:PYTHONPATH

function Enable-D731PythonPath {
    if ([string]::IsNullOrWhiteSpace($PreviousPythonPath)) {
        $env:PYTHONPATH = $BackendPath
    } else {
        $env:PYTHONPATH = "$BackendPath$([IO.Path]::PathSeparator)$PreviousPythonPath"
    }
}

function Restore-D731PythonPath {
    $env:PYTHONPATH = $PreviousPythonPath
}

if ($Mode -eq 'StaticCheck') {
    if (-not (Test-Path $Script)) { throw 'D731_SCRIPT_NOT_FOUND' }
    $Body = Get-Content -Raw -Encoding UTF8 $Script
    if ($Body -match '(^|[\s])(ssh|scp|docker|mongosh)([\s]|$)') {
        throw 'D731_REMOTE_EXECUTION_SURFACE_DETECTED'
    }
    if ($Body -match '\-\-apply|\-\-execute|\-\-rollback') {
        throw 'D731_EXECUTOR_SWITCH_DETECTED'
    }

    Enable-D731PythonPath
    try {
        python -m py_compile $Script '.\backend\utils\curricular_workload_policy.py'
        $CompileExitCode = $LASTEXITCODE
        if ($CompileExitCode -ne 0) { throw "D731_COMPILE_FAILED=$CompileExitCode" }

        python $Script --help *> $null
        $CliExitCode = $LASTEXITCODE
        if ($CliExitCode -ne 0) { throw "D731_CLI_IMPORT_CHECK_FAILED=$CliExitCode" }
    } finally {
        Restore-D731PythonPath
    }

    Write-Host 'P0F7_9D731_LOCAL_WRAPPER_STATIC_CHECK=PASS'
    Write-Host 'P0F7_9D731_CLI_IMPORT_CHECK=PASS'
    return
}

if ($Mode -eq 'Build') {
    if (-not $Plan -or -not $D71Report -or -not $D72Report -or -not $Html -or -not $Template -or -not $Policy) {
        throw 'D731_BUILD_ARGS_REQUIRED'
    }

    Enable-D731PythonPath
    try {
        python $Script build `
            --plan $Plan `
            --d71-report $D71Report `
            --d72-report $D72Report `
            --html $Html `
            --template-json $Template `
            --policy-json $Policy
        $BuildExitCode = $LASTEXITCODE
    } finally {
        Restore-D731PythonPath
    }

    if ($BuildExitCode -ne 0) { throw "D731_BUILD_FAILED=$BuildExitCode" }
    Write-Host 'P0F7_9D731_LOCAL_BUILD_DONE=YES'
    Write-Host "HTML=$Html"
    Write-Host "TEMPLATE=$Template"
    Write-Host "POLICY=$Policy"
    return
}

if ($Mode -eq 'Seal') {
    if (-not $Plan -or -not $D71Report -or -not $D72Report -or -not $Decision -or -not $Output) {
        throw 'D731_SEAL_ARGS_REQUIRED'
    }

    Enable-D731PythonPath
    try {
        python $Script seal `
            --plan $Plan `
            --d71-report $D71Report `
            --d72-report $D72Report `
            --decision $Decision `
            --json $Output
        $SealExitCode = $LASTEXITCODE
    } finally {
        Restore-D731PythonPath
    }

    if ($SealExitCode -ne 0) { throw "D731_SEAL_FAILED=$SealExitCode" }
    Write-Host 'P0F7_9D731_LOCAL_SEAL_DONE=YES'
    Write-Host "REPORT=$Output"
    return
}
