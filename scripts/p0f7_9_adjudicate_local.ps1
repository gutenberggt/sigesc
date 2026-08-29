param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("Build","Seal","StaticCheck")]
    [string]$Mode,

    [string]$Series = "",
    [string]$Reevaluation = "",
    [string]$Html = "",
    [string]$Decisions = "",
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Script = Join-Path $Root "backend\scripts\audit_p0f7_9_component_adjudication.py"

if (-not (Test-Path $Script)) {
    throw "P0-F7.9 analyzer not found: $Script"
}

if ($Mode -eq "StaticCheck") {
    Write-Host "P0F7_9_LOCAL_WRAPPER_STATIC_CHECK=PASS"
    Write-Host "PRODUCTION_ACCESS=NO"
    Write-Host "WORKLOAD_DECISION=NO"
    Write-Host "EXECUTOR_AUTHORIZED=NO"
    exit 0
}

foreach ($Required in @($Series, $Reevaluation)) {
    if ([string]::IsNullOrWhiteSpace($Required) -or -not (Test-Path $Required)) {
        throw "Required local file not found: $Required"
    }
}

Write-Host "P0-F7.9 local/offline component adjudication"
Write-Host "PRODUCTION_ACCESS=NO"
Write-Host "WORKLOAD_DECISION=NO"
Write-Host "SERIES=$Series"
Write-Host "REEVALUATION=$Reevaluation"

if ($Mode -eq "Build") {
    if ([string]::IsNullOrWhiteSpace($Html)) {
        throw "-Html is required in Build mode."
    }
    & python $Script build --series $Series --reevaluation $Reevaluation --html $Html
    if ($LASTEXITCODE -ne 0) {
        throw "P0-F7.9 station build failed with exit code $LASTEXITCODE."
    }
    Write-Host "STATION=$Html"
    exit 0
}

if ([string]::IsNullOrWhiteSpace($Decisions) -or -not (Test-Path $Decisions)) {
    throw "-Decisions must point to the exported p0f7_9-decisions.json file."
}
if ([string]::IsNullOrWhiteSpace($Output)) {
    throw "-Output is required in Seal mode."
}

& python $Script seal --series $Series --reevaluation $Reevaluation --decisions $Decisions --json $Output
if ($LASTEXITCODE -ne 0) {
    throw "P0-F7.9 seal failed with exit code $LASTEXITCODE."
}
Write-Host "SEALED_REPORT=$Output"
