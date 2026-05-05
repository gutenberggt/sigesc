# ============================================================
# SIGESC Backend — Makefile (in-container)
# ------------------------------------------------------------
# Disponível tanto no preview Emergent (/app/backend) quanto em
# produção Coolify (/app, pois o Dockerfile faz COPY . . a partir
# de ./backend). Use:  cd para o diretório do backend e rode `make`.
#
# Em produção: cd /app && make help
# Em preview:  cd /app/backend && make help
# ============================================================

SHELL := /bin/bash
PYTHON ?= python

.DEFAULT_GOAL := help

.PHONY: help
help: ## Lista alvos disponíveis
	@awk 'BEGIN {FS = ":.*##"; printf "Alvos disponíveis:\n\n"} \
		/^[a-zA-Z0-9_-]+:.*##/ {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ------------------------------------------------------------
# Migração de NOMES (CAPS → Title Case) — afeta documento original com backup
# ------------------------------------------------------------
.PHONY: migrate-dry-run
migrate-dry-run: ## Inspeção de nomes (sem alterar)
	@bash scripts/run_migration.sh dry-run

.PHONY: migrate-names
migrate-names: ## Migração de nomes em 3 fases com prompts
	@bash scripts/run_migration.sh apply

.PHONY: migrate-names-yes
migrate-names-yes: ## Migração de nomes em 3 fases sem prompts (CI/cron)
	@bash scripts/run_migration.sh apply --yes

.PHONY: migrate-status
migrate-status: ## Lista coleções e backups
	@bash scripts/run_migration.sh status

.PHONY: migrate-rollback
migrate-rollback: ## Reverte (uso: make migrate-rollback TS=20260505T105357Z)
	@if [[ -z "$(TS)" ]]; then \
		echo "Uso: make migrate-rollback TS=<timestamp>"; \
		exit 2; \
	fi
	@bash scripts/run_migration.sh rollback $(TS)

# ------------------------------------------------------------
# Normalização de CONTEÚDO TEXTUAL (CAPS → sentence case) — fila de revisão
# ------------------------------------------------------------
.PHONY: content-dry-run
content-dry-run: ## Relatório de candidatos a normalização (sem enfileirar)
	@$(PYTHON) scripts/normalize_content.py --dry-run

.PHONY: content-scan
content-scan: ## Enfileira sugestões em content_review_queue (admin revisa em /admin/content-review)
	@$(PYTHON) scripts/normalize_content.py --scan

.PHONY: content-clear-pending
content-clear-pending: ## Remove itens pending da fila (não afeta docs originais)
	@$(PYTHON) scripts/normalize_content.py --clear-pending
