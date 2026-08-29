param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('StaticCheck','BuildReference','BuildPages','Analyze')]
    [string]$Mode,

    [string]$InventoryReport = 'C:\SIGESC\private\p0f7_9c\p0f7_9c-inventory-report.json',
    [string]$Reference,
    [string]$ReferenceCollector = 'C:\SIGESC\private\p0f7_9c1\p0f7_9c1-reference.js',
    [string]$CollectorsDir = 'C:\SIGESC\private\p0f7_9c1\collectors',
    [string]$PagesDir = 'C:\SIGESC\private\p0f7_9c1\pages',
    [string]$Output = 'C:\SIGESC\private\p0f7_9c1\p0f7_9c1-network-audit.json',
    [string]$DbName = 'sigesc'
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$ReferenceBuilder = Join-Path $Root 'backend\scripts\build_p0f7_9c1_reference_snapshot_js.py'
$PageBuilder = Join-Path $Root 'backend\scripts\build_p0f7_9c1_school_pages_js.py'
$Analyzer = Join-Path $Root 'backend\scripts\audit_p0f7_9c1_school_pages_offline.py'

Write-Host 'P0-F7.9C1 local/offline paged school curricular audit'
Write-Host 'PRODUCTION_ACCESS=NO'
Write-Host 'DATABASE_MUTATION=NO'
Write-Host 'STUDENT_DATA_ACCESS=NO'

if ($Mode -eq 'StaticCheck') {
    foreach ($Path in @($ReferenceBuilder, $PageBuilder, $Analyzer)) {
        if (-not (Test-Path $Path)) { throw "TOOL_NOT_FOUND=$Path" }
    }
    Write-Host 'P0F7_9C1_LOCAL_WRAPPER_STATIC_CHECK=PASS'
    exit 0
}

if (-not (Test-Path $InventoryReport)) { throw "INVENTORY_REPORT_NOT_FOUND=$InventoryReport" }

if ($Mode -eq 'BuildReference') {
    $dir = Split-Path -Parent $ReferenceCollector
    if ($dir) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    python $ReferenceBuilder --inventory-report $InventoryReport --db $DbName --js $ReferenceCollector
    if ($LASTEXITCODE -ne 0) { throw "REFERENCE_BUILDER_FAILED=$LASTEXITCODE" }
    Write-Host 'P0F7_9C1_REFERENCE_LOCAL_BUILD_DONE=YES'
    Write-Host "REFERENCE_COLLECTOR=$ReferenceCollector"
    exit 0
}

if (-not $Reference) { throw 'REFERENCE_REQUIRED' }
if (-not (Test-Path $Reference)) { throw "REFERENCE_NOT_FOUND=$Reference" }

if ($Mode -eq 'BuildPages') {
    New-Item -ItemType Directory -Force -Path $CollectorsDir | Out-Null
    python $PageBuilder --inventory-report $InventoryReport --reference $Reference --db $DbName --out-dir $CollectorsDir
    if ($LASTEXITCODE -ne 0) { throw "PAGE_BUILDER_FAILED=$LASTEXITCODE" }
    Write-Host 'P0F7_9C1_PAGE_COLLECTORS_LOCAL_BUILD_DONE=YES'
    Write-Host "COLLECTORS_DIR=$CollectorsDir"
    exit 0
}

if (-not (Test-Path $PagesDir)) { throw "PAGES_DIR_NOT_FOUND=$PagesDir" }
$parent = Split-Path -Parent $Output
if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
python $Analyzer --inventory-report $InventoryReport --reference $Reference --pages-dir $PagesDir --json $Output
if ($LASTEXITCODE -ne 0) { throw "ANALYZER_FAILED=$LASTEXITCODE" }
Write-Host 'P0F7_9C1_LOCAL_ANALYSIS_DONE=YES'
Write-Host "REPORT=$Output"
Write-Host 'PRODUCTION_ACCESS=NO'
Write-Host 'DATABASE_MUTATION=NO'
Write-Host 'REMEDIATION_EXECUTED=NO'
