param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('StaticCheck','Build')]
    [string]$Mode,

    [string]$D2Report,
    [string]$D3Report,
    [string]$Output
)

$ErrorActionPreference = 'Stop'

Write-Host 'P0-F7.9D4 local/offline sealed remediation plan'
Write-Host 'PRODUCTION_ACCESS=NO'
Write-Host 'DATABASE_MUTATION=NO'
Write-Host 'PRODUCTION_WRITES=NO'
Write-Host 'REMEDIATION_EXECUTED=NO'

$Builder = '.\backend\scripts\build_p0f7_9d4_sealed_remediation_plan.py'

if ($Mode -eq 'StaticCheck') {
    if (-not (Test-Path $Builder)) { throw 'D4_BUILDER_NOT_FOUND' }
    if (Select-String -Path $Builder -Pattern 'pymongo|motor|mongosh|docker exec|ssh |subprocess|requests\.|httpx\.' -Quiet) {
        throw 'D4_BUILDER_MUST_BE_OFFLINE_ONLY'
    }
    if (Select-String -Path $Builder -Pattern 'update_one|update_many|insert_one|insert_many|delete_one|delete_many|bulk_write' -Quiet) {
        throw 'D4_BUILDER_MUST_NOT_CONTAIN_DATABASE_WRITES'
    }
    Write-Host 'P0F7_9D4_LOCAL_WRAPPER_STATIC_CHECK=PASS'
    return
}

if ($Mode -eq 'Build') {
    if (-not $D2Report -or -not $D3Report -or -not $Output) { throw 'D4_BUILD_ARGS_REQUIRED' }
    python $Builder `
        --d2-report $D2Report `
        --d3-report $D3Report `
        --json $Output
    if ($LASTEXITCODE -ne 0) { throw "D4_BUILDER_FAILED=$LASTEXITCODE" }
    Write-Host 'P0F7_9D4_LOCAL_BUILD_DONE=YES'
    Write-Host "PLAN=$Output"
    Write-Host 'PRODUCTION_ACCESS=NO'
    Write-Host 'DATABASE_MUTATION=NO'
    Write-Host 'PRODUCTION_WRITES=NO'
    Write-Host 'REMEDIATION_EXECUTED=NO'
    return
}
