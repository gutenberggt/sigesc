param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('StaticCheck','Build','Analyze')]
    [string]$Mode,

    [string]$SealedReport,
    [string]$Collector,
    [string]$Snapshot,
    [string]$Output,
    [string]$DbName = 'sigesc'
)

$ErrorActionPreference = 'Stop'

$Builder = '.\backend\scripts\build_p0f7_9d74_revised_preflight_snapshot_js.py'
$Analyzer = '.\backend\scripts\audit_p0f7_9d74_revised_preflight_offline.py'
$BackendPath = (Resolve-Path '.\backend').Path
$PreviousPythonPath = $env:PYTHONPATH

Write-Host 'P0-F7.9D7.4 revised last-mile preflight / CAS dry-run'
Write-Host 'DATABASE_MUTATION=NO'
Write-Host 'PRODUCTION_WRITES=NO'
Write-Host 'EXECUTOR_AUTHORIZED=NO'
Write-Host 'REMEDIATION_EXECUTED=NO'

try {
    if ($PreviousPythonPath) {
        $env:PYTHONPATH = "$BackendPath$([IO.Path]::PathSeparator)$PreviousPythonPath"
    } else {
        $env:PYTHONPATH = $BackendPath
    }

    if ($Mode -eq 'StaticCheck') {
        if (-not (Test-Path $Builder)) { throw 'D74_BUILDER_NOT_FOUND' }
        if (-not (Test-Path $Analyzer)) { throw 'D74_ANALYZER_NOT_FOUND' }
        python $Builder --help *> $null
        if ($LASTEXITCODE -ne 0) { throw "D74_BUILDER_IMPORT_CHECK_FAILED=$LASTEXITCODE" }
        python $Analyzer --help *> $null
        if ($LASTEXITCODE -ne 0) { throw "D74_ANALYZER_IMPORT_CHECK_FAILED=$LASTEXITCODE" }
        Write-Host 'P0F7_9D74_LOCAL_WRAPPER_STATIC_CHECK=PASS'
        Write-Host 'P0F7_9D74_CLI_IMPORT_CHECK=PASS'
        return
    }

    if ($Mode -eq 'Build') {
        if (-not $SealedReport -or -not $Collector) { throw 'D74_BUILD_ARGS_REQUIRED' }
        python $Builder `
            --sealed-report $SealedReport `
            --db $DbName `
            --js $Collector
        if ($LASTEXITCODE -ne 0) { throw "D74_BUILDER_FAILED=$LASTEXITCODE" }
        Write-Host 'P0F7_9D74_LOCAL_BUILD_DONE=YES'
        Write-Host "COLLECTOR=$Collector"
        return
    }

    if ($Mode -eq 'Analyze') {
        if (-not $SealedReport -or -not $Snapshot -or -not $Output) { throw 'D74_ANALYZE_ARGS_REQUIRED' }
        python $Analyzer `
            --sealed-report $SealedReport `
            --snapshot $Snapshot `
            --json $Output
        if ($LASTEXITCODE -ne 0) { throw "D74_ANALYZER_FAILED=$LASTEXITCODE" }
        Write-Host 'P0F7_9D74_LOCAL_ANALYSIS_DONE=YES'
        Write-Host 'DATABASE_MUTATION=NO'
        Write-Host 'PRODUCTION_WRITES=NO'
        Write-Host 'EXECUTOR_AUTHORIZED=NO'
        Write-Host 'REMEDIATION_EXECUTED=NO'
        return
    }
}
finally {
    $env:PYTHONPATH = $PreviousPythonPath
}
