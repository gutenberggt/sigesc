# ============================================================
# SIGESC — Makefile
# ------------------------------------------------------------
# Comandos curtos para tarefas operacionais. Uso: `make <alvo>`
# Executa relativo à raiz do projeto (/app em dev, /app em prod
# quando o Dockerfile copia `.` para `/app`).
# ============================================================

SHELL := /bin/bash
PYTHON ?= python
# Detecta layout: preview Emergent tem /app/backend/, produção Coolify tem /app/
BACKEND_DIR := $(shell if [ -d "backend" ]; then echo "backend"; else echo "."; fi)
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

# ------------------------------------------------------------
# Normalização de conteúdo textual (CAPS → sentence case)
# ------------------------------------------------------------
.PHONY: content-dry-run
content-dry-run: ## Relatório de candidatos a normalização de conteúdo (sem alterar)
	@cd $(BACKEND_DIR) && $(PYTHON) scripts/normalize_content.py --dry-run

.PHONY: content-scan
content-scan: ## Enfileira sugestões em content_review_queue (admin revisa em /admin/content-review)
	@cd $(BACKEND_DIR) && $(PYTHON) scripts/normalize_content.py --scan

.PHONY: content-clear-pending
content-clear-pending: ## Remove itens pending da fila (não afeta docs originais)
	@cd $(BACKEND_DIR) && $(PYTHON) scripts/normalize_content.py --clear-pending

# ------------------------------------------------------------
# Higienização Textual Fase 1 — FORMATAÇÃO determinística
# ------------------------------------------------------------
.PHONY: text-dry-run
text-dry-run: ## Relatório de anomalias de FORMATAÇÃO (sem enfileirar)
	@cd $(BACKEND_DIR) && $(PYTHON) scripts/text_improvement.py --dry-run

.PHONY: text-scan
text-scan: ## Enfileira sugestões em text_improvement_queue (admin revisa em /admin/text-improvement)
	@cd $(BACKEND_DIR) && $(PYTHON) scripts/text_improvement.py --scan

.PHONY: text-clear-pending
text-clear-pending: ## Remove itens pending da fila de formatação
	@cd $(BACKEND_DIR) && $(PYTHON) scripts/text_improvement.py --clear-pending

# ------------------------------------------------------------
# GATE de regressão — Transferência Institucional (sandbox isolado)
# ------------------------------------------------------------
.PHONY: regression
regression: ## GATE DURO: smoke test de regressão do ciclo de Transferência (cycle). Exit 1 bloqueia.
	@echo "============================================================"
	@echo "GATE DE REGRESSÃO — Transferência Institucional"
	@echo "Detecta regressões. NÃO certifica o sistema nem libera produção."
	@echo "Liberação exige homologação assistida (gates humanos) + aprovação formal."
	@echo "============================================================"
	@cd $(BACKEND_DIR) && $(PYTHON) scripts/homolog_transfer_sandbox.py cycle \
		--email "$${HOMOLOG_ADMIN_EMAIL:-gutenberg@sigesc.com}" \
		--password "$${HOMOLOG_ADMIN_PASSWORD}"
