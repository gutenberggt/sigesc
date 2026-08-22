$ErrorActionPreference = 'Stop'

function Assert-ExternalSuccess([string]$Step) {
  if ($LASTEXITCODE -ne 0) {
    throw "$Step falhou (exit code $LASTEXITCODE)."
  }
}

Write-Host '=== PR #88 - Contrato temporal global ===' -ForegroundColor Cyan

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root

Write-Host '[1/6] Aplicando contrato temporal global...' -ForegroundColor Yellow
python backend/scripts/apply_global_local_time_contract_pr88.py
Assert-ExternalSuccess 'Aplicador principal'

Write-Host '[2/6] Aplicando correcoes detectadas na primeira validacao...' -ForegroundColor Yellow
python backend/scripts/fix_global_local_time_contract_pr88_round2.py
Assert-ExternalSuccess 'Round 2'

Write-Host '[3/6] Auditando invariantes...' -ForegroundColor Yellow
python backend/scripts/audit_global_local_time_contract_pr88.py
Assert-ExternalSuccess 'Auditoria temporal'

Write-Host '[4/6] Compilando backend afetado...' -ForegroundColor Yellow
python -m compileall -q `
  backend/utils/client_time.py `
  backend/audit_service.py `
  backend/routers/audit_logs.py `
  backend/services/render_worker.py `
  backend/services/bulletin_renderer.py `
  backend/services/history_renderer.py `
  backend/pdf `
  backend/pdf_generator.py `
  backend/hr_pdf_generator.py
Assert-ExternalSuccess 'Compile do backend'

Write-Host '[5/6] Validando diff...' -ForegroundColor Yellow
git diff --check
Assert-ExternalSuccess 'git diff --check'

Write-Host '[6/6] Build do frontend...' -ForegroundColor Yellow
$frontendBuildRan = $false
Push-Location frontend
try {
  if (Get-Command yarn -ErrorAction SilentlyContinue) {
    yarn build
    Assert-ExternalSuccess 'Frontend yarn build'
    $frontendBuildRan = $true
  }
  elseif (Get-Command corepack -ErrorAction SilentlyContinue) {
    corepack yarn build
    Assert-ExternalSuccess 'Frontend corepack yarn build'
    $frontendBuildRan = $true
  }
  else {
    Write-Warning 'Yarn/Corepack nao encontrado. Build local do frontend sera validado pelo CI do GitHub.'
  }
}
finally {
  Pop-Location
}

Write-Host ''
if ($frontendBuildRan) {
  Write-Host 'PASS: aplicacao, auditoria, compile, diff-check e frontend build concluidos.' -ForegroundColor Green
}
else {
  Write-Host 'PASS PARCIAL LOCAL: aplicacao, auditoria, compile e diff-check concluidos.' -ForegroundColor Green
  Write-Host 'PENDENTE LOCAL: frontend build (sera obrigatorio no CI antes de qualquer merge).' -ForegroundColor Yellow
}
Write-Host 'Nenhum commit, push, deploy ou acesso a banco foi executado automaticamente.' -ForegroundColor Green
Write-Host ''
Write-Host 'Arquivos alterados:' -ForegroundColor Cyan
git status --short
