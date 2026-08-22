$ErrorActionPreference = 'Stop'

Write-Host '=== PR #88 — Contrato temporal global ===' -ForegroundColor Cyan

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root

Write-Host '[1/5] Aplicando contrato temporal global...' -ForegroundColor Yellow
python backend/scripts/apply_global_local_time_contract_pr88.py

Write-Host '[2/5] Auditando invariantes...' -ForegroundColor Yellow
python backend/scripts/audit_global_local_time_contract_pr88.py

Write-Host '[3/5] Compilando backend afetado...' -ForegroundColor Yellow
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

Write-Host '[4/5] Validando diff...' -ForegroundColor Yellow
git diff --check

Write-Host '[5/5] Build do frontend...' -ForegroundColor Yellow
Push-Location frontend
try {
  yarn build
}
finally {
  Pop-Location
}

Write-Host ''
Write-Host 'PASS: aplicação, auditoria, compile, diff-check e frontend build concluídos.' -ForegroundColor Green
Write-Host 'Nenhum commit ou push foi feito automaticamente.' -ForegroundColor Green
Write-Host ''
Write-Host 'Arquivos alterados:' -ForegroundColor Cyan
git status --short
