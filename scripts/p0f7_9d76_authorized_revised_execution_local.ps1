param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('StaticCheck','Build','ValidateReceipt')]
    [string]$Mode,

    [string]$Manifest,
    [string]$Executor,
    [string]$Metadata,
    [string]$Receipt,
    [string]$ReceiptReport,
    [string]$DbName = 'sigesc',
    [switch]$AuthorizeProductionWrites
)

$ErrorActionPreference = 'Stop'

Write-Host 'P0-F7.9D7.6.3 authorized revised production executor'
Write-Host 'MANIFEST_SHA256=89e0f72d97f7cfa8b2d4b5dd7b5d35a01376a813d69d46f5bce7fa9c11440fcc'
Write-Host 'EXPECTED_FORWARD_WRITES=23'
Write-Host 'STRATEGY=CAS_WITH_COMPENSATING_ROLLBACK_REQUIRED'
Write-Host 'RETIRE_STATUS_CAS=EXACT_SEALED_ACTIVE_STATUS'
Write-Host 'MONGOSH_FINDONE_PROJECTION=DIRECT_SECOND_ARGUMENT'
Write-Host 'HARD_DELETE=NO'
Write-Host 'REMOTE_EXECUTION_BY_WRAPPER=NO'

$Builder = '.\backend\scripts\build_p0f7_9d763_authorized_revised_executor_js.py'
$Validator = '.\backend\scripts\validate_p0f7_9d76_execution_receipt_offline.py'

if ($Mode -eq 'StaticCheck') {
    if (-not (Test-Path $Builder)) { throw 'D763_BUILDER_NOT_FOUND' }
    if (-not (Test-Path $Validator)) { throw 'D76_VALIDATOR_NOT_FOUND' }

    python -m py_compile $Builder $Validator
    if ($LASTEXITCODE -ne 0) { throw "D763_COMPILE_FAILED=$LASTEXITCODE" }

    python $Builder --help | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "D763_BUILDER_CLI_IMPORT_FAILED=$LASTEXITCODE" }
    python $Validator --help | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "D76_VALIDATOR_CLI_IMPORT_FAILED=$LASTEXITCODE" }

    Write-Host 'P0F7_9D763_LOCAL_WRAPPER_STATIC_CHECK=PASS'
    Write-Host 'P0F7_9D763_BUILDER_CLI_IMPORT_CHECK=PASS'
    Write-Host 'P0F7_9D76_VALIDATOR_CLI_IMPORT_CHECK=PASS'
    Write-Host 'DATABASE_MUTATION=NO'
    Write-Host 'PRODUCTION_WRITES=NO'
    return
}

if ($Mode -eq 'Build') {
    if (-not $Manifest -or -not $Executor -or -not $Metadata) {
        throw 'D763_BUILD_ARGS_REQUIRED'
    }
    if (-not (Test-Path $Manifest)) { throw 'D763_MANIFEST_NOT_FOUND' }
    if (-not $AuthorizeProductionWrites) {
        throw 'D763_EXPLICIT_PRODUCTION_WRITE_AUTHORIZATION_REQUIRED'
    }

    python $Builder `
        --manifest $Manifest `
        --db $DbName `
        --js $Executor `
        --metadata $Metadata `
        --authorize-production-writes

    if ($LASTEXITCODE -ne 0) { throw "D763_BUILDER_FAILED=$LASTEXITCODE" }
    Write-Host 'P0F7_9D763_LOCAL_BUILD_DONE=YES'
    Write-Host "EXECUTOR=$Executor"
    Write-Host "METADATA=$Metadata"
    Write-Host 'EXECUTION_NOT_PERFORMED=YES'
    Write-Host 'DATABASE_MUTATION=NO'
    Write-Host 'PRODUCTION_WRITES=NO'
    return
}

if ($Mode -eq 'ValidateReceipt') {
    if (-not $Manifest -or -not $Executor -or -not $Metadata -or -not $Receipt -or -not $ReceiptReport) {
        throw 'D76_RECEIPT_ARGS_REQUIRED'
    }
    foreach ($Path in @($Manifest, $Executor, $Metadata, $Receipt)) {
        if (-not (Test-Path $Path)) { throw "D76_VALIDATION_INPUT_NOT_FOUND=$Path" }
    }

    python $Validator `
        --manifest $Manifest `
        --executor $Executor `
        --metadata $Metadata `
        --receipt $Receipt `
        --json $ReceiptReport

    if ($LASTEXITCODE -ne 0) { throw "D76_RECEIPT_VALIDATOR_FAILED=$LASTEXITCODE" }
    Write-Host 'P0F7_9D76_LOCAL_RECEIPT_VALIDATION_DONE=YES'
    Write-Host "REPORT=$ReceiptReport"
    Write-Host 'VALIDATOR_DATABASE_MUTATION=NO'
    Write-Host 'VALIDATOR_PRODUCTION_WRITES=NO'
    return
}
