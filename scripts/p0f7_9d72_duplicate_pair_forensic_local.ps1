param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('StaticCheck','Build','Analyze')]
    [string]$Mode,

    [string]$Plan,
    [string]$D71Report,
    [string]$Collector,
    [string]$Snapshot,
    [string]$Output,
    [string]$DbName = 'sigesc'
)

$ErrorActionPreference = 'Stop'

Write-Host 'P0-F7.9D7.2 duplicate-pair forensic'
Write-Host 'PRODUCTION_WRITES=NO'
Write-Host 'DATABASE_MUTATION=NO'
Write-Host 'STUDENT_DATA_ACCESS=NO'

$Builder  = '.\backend\scripts\build_p0f7_9d72_duplicate_pair_snapshot_js.py'
$Analyzer = '.\backend\scripts\analyze_p0f7_9d72_duplicate_pair_forensic.py'

if ($Mode -eq 'StaticCheck') {
    foreach ($F in @($Builder,$Analyzer)) {
        if (-not (Test-Path $F)) { throw "D72_FILE_NOT_FOUND=$F" }
    }

    $Forbidden = 'pymongo|motor|AsyncIOMotorClient|MongoClient\(|requests\.|httpx\.|subprocess\.|ssh\s|scp\s|docker exec|update_one\(|update_many\(|insert_one\(|insert_many\(|delete_one\(|delete_many\(|replace_one\(|bulk_write\('
    $AnalyzerBody = Get-Content -Raw -Encoding UTF8 $Analyzer
    if ($AnalyzerBody -match $Forbidden) {
        throw 'D72_ANALYZER_OFFLINE_BOUNDARY_FAILED'
    }

    $BuilderBody = Get-Content -Raw -Encoding UTF8 $Builder
    if ($BuilderBody -match 'updateOne\(|updateMany\(|deleteOne\(|deleteMany\(|insertOne\(|insertMany\(|replaceOne\(|bulkWrite\(') {
        throw 'D72_COLLECTOR_MUTATOR_TEMPLATE_DETECTED'
    }

    Write-Host 'P0F7_9D72_LOCAL_WRAPPER_STATIC_CHECK=PASS'
    return
}

if ($Mode -eq 'Build') {
    if (-not $Plan -or -not $D71Report -or -not $Collector) {
        throw 'D72_BUILD_ARGS_REQUIRED'
    }

    python $Builder `
        --plan $Plan `
        --d71-report $D71Report `
        --db $DbName `
        --js $Collector

    if ($LASTEXITCODE -ne 0) { throw "D72_BUILD_FAILED=$LASTEXITCODE" }
    Write-Host 'P0F7_9D72_LOCAL_BUILD_DONE=YES'
    Write-Host "COLLECTOR=$Collector"
    return
}

if ($Mode -eq 'Analyze') {
    if (-not $Plan -or -not $D71Report -or -not $Snapshot -or -not $Output) {
        throw 'D72_ANALYZE_ARGS_REQUIRED'
    }

    python $Analyzer `
        --plan $Plan `
        --d71-report $D71Report `
        --snapshot $Snapshot `
        --json $Output

    if ($LASTEXITCODE -ne 0) { throw "D72_ANALYSIS_FAILED=$LASTEXITCODE" }
    Write-Host 'P0F7_9D72_LOCAL_ANALYSIS_DONE=YES'
    Write-Host "REPORT=$Output"
    return
}
