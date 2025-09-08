# =============================
# 🚀 SIGESC Dev Tools - PowerShell
# =============================

# Pasta de logs sempre relativa ao local do script
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $ScriptDir "logs"

# Criar pasta se não existir
if (!(Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

function Show-Menu {
    Clear-Host
    Write-Host "=============================" -ForegroundColor Cyan
    Write-Host "🚀 SIGESC Dev Tools - Menu" -ForegroundColor Green
    Write-Host "=============================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "[1] Rodar Lint (somente verificar)" -ForegroundColor Yellow
    Write-Host "[2] Corrigir com ESLint" -ForegroundColor Yellow
    Write-Host "[3] Rodar Prettier (formatar)" -ForegroundColor Yellow
    Write-Host "[4] Ver últimos logs" -ForegroundColor Yellow
    Write-Host "[5] Sair" -ForegroundColor Red
    Write-Host ""
}

do {
    Show-Menu
    $option = Read-Host "Digite o número da opção"

    switch ($option) {
        "1" {
            Write-Host "Rodando ESLint (checagem)..." -ForegroundColor Cyan
            npm run lint | Tee-Object "$LogDir\lint-report.txt"
            Write-Host "Relatório salvo em $LogDir\lint-report.txt" -ForegroundColor Green
            Pause
        }
        "2" {
            Write-Host "Corrigindo com ESLint..." -ForegroundColor Cyan
            npm run lint:fix | Tee-Object "$LogDir\lint-fix-report.txt"
            Write-Host "Relatório salvo em $LogDir\lint-fix-report.txt" -ForegroundColor Green
            Pause
        }
        "3" {
            Write-Host "Rodando Prettier..." -ForegroundColor Cyan
            npx prettier --write "src/**/*.{js,jsx}" | Tee-Object "$LogDir\prettier-report.txt"
            Write-Host "Relatório salvo em $LogDir\prettier-report.txt" -ForegroundColor Green
            Pause
        }
        "4" {
            Write-Host "Últimos logs:" -ForegroundColor Green
            Get-ChildItem $LogDir | Sort-Object LastWriteTime -Descending | Select-Object Name, LastWriteTime
            Pause
        }
        "5" {
            Write-Host "Saindo..." -ForegroundColor Red
            break
        }
        Default {
            Write-Host "Opção inválida!" -ForegroundColor Red
            Pause
        }
    }
} while ($option -ne "5")
