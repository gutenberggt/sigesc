# SPRINT 001.1 — Hardening Operacional do MIG · RELATÓRIO DE HOMOLOGAÇÃO

**Status:** ✅ HOMOLOGADA (Jun/2026)
**Escopo:** Correlation IDs ponta a ponta · Auditoria automática de Feature Flags ·
Paginação/filtros no `GET /mec/audit` · Testes de resiliência do RetryManager e da
gravação de auditoria. **Nenhum envio real ao MEC** (reservado à Sprint 002, que permanece BLOQUEADA).

---

## 1. Correlation ID — VALIDADO ✅
- Gerador único em `mig/core/ids.py::generate_correlation_id(provider)` → formato
  `CMDE-YYYYMMDD-XXXXX` (prefixo do provider + data UTC + sufixo hex de 5 chars).
- Criado no início de cada operação de integração (`CmdeService.query`) e propagado ao
  `CmdeClient → BaseGovClient` como header `X-Correlation-Id` (`http_client.py` linhas 28-29).
- Persistido no evento de auditoria (`mig_audit_events.correlation_id`) tanto no sucesso
  quanto no erro (`service.py` linhas 112, 132, 144).
- Permanece o MESMO durante todo o fluxo de retry (o id é criado ANTES do `run_with_retry`
  e reutilizado em todas as tentativas do `BaseGovClient`).
- Rastreabilidade ponta a ponta: cada execução gera um id ÚNICO — validado no teste de carga
  multi-tenant (3 tenants → 3 correlation_ids distintos).
- **Evidência E2E:** eventos `FEATURE_FLAG_UPDATED` retornados com
  `correlation_id=FLAG-20260730-71018` / `FLAG-20260730-03678` (únicos por execução).

## 2. Auditoria de Feature Flags — VALIDADO ✅
Endpoint `PUT /mec/flags` → `CmdeService.set_feature_flag` grava evento automático
`operation=FEATURE_FLAG_UPDATED` em `mig_audit_events` com TODOS os campos exigidos:
| Campo | Evidência E2E |
|---|---|
| tenant | `null` (super_admin sem header de tenant) — identificação correta |
| actor (responsável) | `gutenberg@sigesc.com` |
| feature | `cmde.retry` |
| previous_value | `true` → depois `false` (transições registradas) |
| new_value | `false` → depois `true` |
| timestamp | `created_at`/`started_at`/`finished_at` ISO-8601 UTC |
| correlation_id | `FLAG-20260730-XXXXX` |
| environment | `homologacao` |

Cobre criação/alteração/desativação de flag (a persistência é upsert por
`{flag, tenant, environment}` em `mig_feature_flags`, e cada mudança gera 1 evento de auditoria).

## 3. Auditoria paginada (`GET /mec/audit`) — VALIDADO ✅
| Cenário | Resultado E2E |
|---|---|
| Paginação (`page`/`page_size`) | `page_size=2` → `total=2, total_pages=1, returned=2` ✅ |
| Filtro por status | `status=success` → `total=2`, todos `success` ✅ |
| Filtro por operação | `operation=FEATURE_FLAG_UPDATED` → 2 eventos corretos ✅ |
| Filtro por período | `date_from=2026-07-30&date_to=2026-07-31` → `total=2`; `date_from=2027-01-01` → `total=0` ✅ |
| Ordenação | desc por `created_at` (`desc_ok: True`) ✅ |
| Compatibilidade legada | `?limit=3` mapeia para `page=1, page_size=3` sem quebra ✅ |
| Segurança | `GET /mec/metrics` sem auth → **401** ✅ |

## 4. Dashboard Técnico — VALIDADO (evidência por screenshot) ✅
Rota `/admin/mec`, aba **Operação Técnica** (`data-testid="tab-operacao"`). Login como
super_admin (`gutenberg@sigesc.com`). Confirmado visualmente:
- **Saúde da Integração:** Total de chamadas=2, Sucesso=2, Erros=0, Taxa de sucesso=100%,
  Latência média=0ms, Volume processado=0, Última execução 30/07/2026 16:17:01.
- **Feature Flags (ambiente: homologacao):** `cmde.enabled`, `cmde.elegibilidades`,
  `cmde.retry` — todas "Habilitado". Aviso "Alterações são auditadas".
- **Histórico de Eventos (2):** colunas Correlation ID, Operação (FEATURE_FLAG_UPDATED),
  Status (success), Registros, Tentativas, Duração, Responsável (gutenberg@sigesc.com), Quando.
- **Filtro de status** ("Todos os status") presente no histórico.
- **Separação clara** entre aba *Configuração* (administrativa) e *Operação Técnica*.
- Elementos presentes: `mec-integration-page`, `mec-ops-panel`, `mec-metrics`,
  `mec-flags`, `mec-audit-table`.

## 5. Testes de resiliência — VALIDADO (automatizados verdes) ✅
Suíte `backend/tests/test_mig_cmde.py` — **15/15 asserts PASS**:
- Sucesso da integração (multi-tenant paralelo: 3 tenants → 1 evento `success`/tenant, `attempts=1`, `records_processed=2`).
- Erro recuperável + retry (RetryManager: 504 recuperável retenta até sucesso; `BaseGovClient` 503,503,200 → ok em 3 tentativas).
- Erro definitivo (401 `MigAuthError` NÃO retenta; erro definitivo grava 1 evento `error`, `http_status=503`).
- Múltiplas execuções concorrentes sem **duplicação** (1 evento por execução) nem **perda de auditoria**.
- Múltiplos tenants isolados (correlation_ids únicos por execução).
- **Consistência de métricas:** agregação derivada do audit (SSoT) — `success_rate`, `avg_latency_ms`, `volume_processed` conferem.
- Métricas já preparadas para a Sprint 002 (`students_sent/accepted/rejected/processing_rate` presentes, default 0/None).

## Critério de aprovação — ATENDIDO ✅
- [x] Testes automatizados verdes (15/15).
- [x] Validação ponta a ponta (E2E via API contra o preview).
- [x] Evidências registradas (respostas E2E + screenshot do Dashboard Técnico).
- [x] Relatório atualizado (este documento).

## Nota de execução
- Harness de teste (`_load_env`) lê `backend/.env` cujos valores estão entre aspas; ao rodar
  manualmente, exportar `MONGO_URL`/`DB_NAME` sem aspas (`setdefault` respeita o ambiente).
  Não afeta a aplicação (o backend usa `python-dotenv`, que remove as aspas).

## Débito documentado (P1 — Sprint futura)
- Política real de limpeza/arquivamento da coleção `mig_audit_events` (hoje apenas documentada).

**A Sprint 002 — Envio de Frequência CMDE permanece BLOQUEADA até liberação explícita do owner.
Após esta homologação, o próximo passo é apresentar o plano arquitetural da Sprint 002 (sem código).**
