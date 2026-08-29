param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('Build','Analyze','StaticCheck')]
    [string]$Mode,

    [string]$Source = 'C:\SIGESC\private\p0f7_9a\p0f7_9a-minimal-snapshot.json',
    [string]$Inventory,
    [string]$Output,
    [string]$Collector = 'C:\SIGESC\private\p0f7_9c\p0f7_9c-inventory.js',
    [string]$DbName = 'sigesc'
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Builder = Join-Path $Root 'backend\scripts\build_p0f7_9c_inventory_snapshot_js.py'
$Analyzer = Join-Path $Root 'backend\scripts\audit_p0f7_9c_inventory_offline.py'

Write-Host 'P0-F7.9C local/offline network inventory'
Write-Host 'PRODUCTION_ACCESS=NO'
Write-Host 'DATABASE_MUTATION=NO'
Write-Host 'STUDENT_DATA_ACCESS=NO'

if ($Mode -eq 'StaticCheck') {
    if (-not (Test-Path $Builder)) { throw "BUILDER_NOT_FOUND=$Builder" }
    if (-not (Test-Path $Analyzer)) { throw "ANALYZER_NOT_FOUND=$Analyzer" }
    Write-Host 'P0F7_9C_LOCAL_WRAPPER_STATIC_CHECK=PASS'
    exit 0
}

if ($Mode -eq 'Build') {
    if (-not (Test-Path $Source)) { throw "SOURCE_NOT_FOUND=$Source" }
    $collectorDir = Split-Path -Parent $Collector
    if ($collectorDir) { New-Item -ItemType Directory -Force -Path $collectorDir | Out-Null }
    python $Builder --snapshot $Source --db $DbName --js $Collector
    if ($LASTEXITCODE -ne 0) { throw "BUILDER_FAILED=$LASTEXITCODE" }
    Write-Host 'P0F7_9C_LOCAL_BUILD_DONE=YES'
    Write-Host "COLLECTOR=$Collector"
    exit 0
}

if (-not $Inventory) { throw 'INVENTORY_REQUIRED_FOR_ANALYZE' }
if (-not $Output) { throw 'OUTPUT_REQUIRED_FOR_ANALYZE' }
if (-not (Test-Path $Source)) { throw "SOURCE_NOT_FOUND=$Source" }
if (-not (Test-Path $Inventory)) { throw "INVENTORY_NOT_FOUND=$Inventory" }
$outputDir = Split-Path -Parent $Output
if ($outputDir) { New-Item -ItemType Directory -Force -Path $outputDir | Out-Null }
python $Analyzer --source $Source --inventory $Inventory --json $Output
if ($LASTEXITCODE -ne 0) { throw "ANALYZER_FAILED=$LASTEXITCODE" }
Write-Host 'P0F7_9C_LOCAL_ANALYSIS_DONE=YES'
Write-Host 'PRODUCTION_ACCESS=NO'
Write-Host 'DATABASE_MUTATION=NO'
