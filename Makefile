# ============================================================
# SIGESC — Makefile
# ------------------------------------------------------------
# Comandos curtos para tarefas operacionais. Uso: `make <alvo>`
# Executa relativo à raiz do projeto (/app em dev, /app em prod
# quando o Dockerfile copia `.` para `/app`).
# ============================================================

SHELL := /bin/bash
PYTHON ?= python
BACKEND_DIR := backend
MIGRATION_RUNNER := $(BACKEND_DIR)/scripts/run_migration.sh

.DEFAULT_GOAL := help

.PHONY: help
help: ## Lista todos os alvos disponíveis
	@awk 'BEGIN {FS = ":.*##"; printf "Alvos disponíveis:\n\n"} \
		/^[a-zA-Z0-9_-]+:.*##/ {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ------------------------------------------------------------
# Migração de nomes (CAPS → Title Case)
# ------------------------------------------------------------
.PHONY: migrate-dry-run
migrate-dry-run: ## Relatório sem alterar dados
	@bash $(MIGRATION_RUNNER) dry-run

.PHONY: migrate-names
migrate-names: ## Aplica migração em 3 fases com prompts
	@bash $(MIGRATION_RUNNER) apply

.PHONY: migrate-names-yes
migrate-names-yes: ## Aplica migração em 3 fases sem prompts (CI/cron)
	@bash $(MIGRATION_RUNNER) apply --yes

.PHONY: migrate-status
migrate-status: ## Lista coleções e backups existentes
	@bash $(MIGRATION_RUNNER) status

.PHONY: migrate-rollback
migrate-rollback: ## Reverte migração (ex: make migrate-rollback TS=20260505T105357Z)
	@if [[ -z "$(TS)" ]]; then \
		echo "Uso: make migrate-rollback TS=<timestamp>"; \
		echo "     ex: make migrate-rollback TS=20260505T105357Z"; \
		exit 2; \
	fi
	@bash $(MIGRATION_RUNNER) rollback $(TS)
