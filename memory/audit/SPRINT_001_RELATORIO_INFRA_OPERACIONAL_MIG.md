# SPRINT 001 — Infra Operacional do MIG — Relatório Técnico

> Executada sobre a Fundação da Sprint 000. **Sem envio real de frequência CMDE, sem Batch/Queue/
> Workers/Scheduler, sem alterar regras de negócio.** Contratos dos endpoints existentes preservados
> (testes de paridade verdes). Junho/2026.

## 1. Resumo Executivo
A base arquitetural do MIG ganhou uma **camada operacional auditável e observável**: auditoria
persistente de eventos de integração (SSoT em `mig_audit_events`), métricas derivadas desses
eventos, endpoint técnico `GET /mec/metrics`, feature flags dinâmicas por tenant/ambiente,
RetryManager completo (backoff + classificação de erros) e um **Dashboard Técnico** na página MEC
(separado da configuração administrativa).

## 2. Entregas por diretriz
| Diretriz | Implementação | Evidência |
|----------|---------------|-----------|
| Auditoria persistente | `MigAuditService` grava em `mig_audit_events` (tenant, operação, provider, início/fim, status, duração, volume, tentativas, http_status, erro, responsável) | `mig/core/audit.py`; teste `sprint001: auditoria persistente` |
| Monitoring operacional | Métricas agregadas do audit (SSoT): total, sucesso/erro, taxa, latência média, volume, última execução, falhas recentes + contadores runtime | `audit.metrics()` + `MigMonitoring`; `GET /mec/metrics` |
| Endpoint técnico | `GET /mec/metrics`, `GET /mec/audit`, `GET/PUT /mec/flags` (novos; não alteram contratos) | `routers/mec_integration.py` |
| Dashboard Técnico | Aba "Operação Técnica" (métricas, flags com toggle, falhas, histórico) separada de "Configuração" | `pages/MECIntegration.js` |
| Feature flags dinâmicas | `FeatureFlagService` com resolução hierárquica (tenant/ambiente > tenant > ambiente > global > default); coleção `mig_feature_flags` | `mig/core/feature_flags.py`; teste `feature flags dinâmicas` |
| RetryManager | Política completa: max_attempts, backoff exponencial, classificação recuperável (502/503/504) × não recuperável (401/403/400); integrado ao `BaseGovClient`; tentativas registradas no audit | `mig/core/retry.py`, `mig/core/http_client.py`; teste `RetryManager` |

## 3. Compatibilidade / Paridade (evidências)
- `GET /mec/sync/status` → `details` idêntico (19/18/19/6/6).
- `GET /mec/students/mapping` → linhas **byte-idênticas** ao baseline.
- `GET /mec/config` → 200 (PGP permanece removido — decisão Sprint 000).
- `GET /mec/elegibilidades?search=123` → 400, mesma mensagem.
- Novos endpoints: `/mec/metrics` 200, `/mec/audit` 200, `/mec/flags` 200.
- Frontend: aba Configuração intacta; aba Operação Técnica renderiza métricas/flags/histórico; toggle de flag funcional.

## 4. Arquitetura (evolução)
```
mig/core/  http_client (retry integrado) · retry (RetryManager completo) ·
           audit (PERSISTENTE + métricas SSoT) · monitoring · feature_flags (FeatureFlagService)
           validation · mapping · crypto (CryptoProvider)
mig/cmde/  service (auditoria por operação + flags + retry) · client (retry/audit) · ...
routers/mec_integration.py  → +/mec/metrics, /mec/audit, /mec/flags (5 originais preservados)
frontend   mecAPI (+getMetrics/getAudit/getFlags/setFlag) · MECIntegration (Dashboard Técnico)
Coleções   mig_audit_events (append-only) · mig_feature_flags (override por tenant/ambiente)
```
Invariantes mantidas: router sem regra · service sem HTTP direto · cliente HTTP único ·
auditoria/monitoring como SSoT operacional · nenhum segredo persistido/exposto.

## 5. Testes
`backend/tests/test_mig_cmde.py` (todos verdes): unit (mapper/validators, mapeamento HTTP), paridade
(status/mapping/config/query-400), Sprint 001 (auditoria persistente + métricas agregadas,
RetryManager recuperável×fatal, feature flags por tenant, service.metrics/audit/flags).

## 6. Arquivos criados / modificados
**Criados:** — (nenhum arquivo novo; evolução dos existentes do core/cmde).
**Modificados (backend):** `mig/core/audit.py`, `mig/core/retry.py`, `mig/core/http_client.py`, `mig/core/feature_flags.py`, `mig/cmde/client.py`, `mig/cmde/service.py`, `routers/mec_integration.py`, `startup/indexes.py`, `tests/test_mig_cmde.py`.
**Modificados (frontend):** `services/api.js` (+métodos ops), `pages/MECIntegration.js` (Dashboard Técnico).
**Coleções novas:** `mig_audit_events`, `mig_feature_flags` (+índices).

## 7. Débitos remanescentes
- `MigMonitoring` runtime é in-memory (reinicia com o processo); métricas históricas vêm do audit (persistido) — ok.
- `set_flag` ainda não gera evento de auditoria dedicado (apenas persiste override).
- `/mec/elegibilidades` continua sem consumidor no frontend (será a UI de envio na Sprint 002).
- Sem paginação no histórico de eventos da UI (limite fixo 50/200).

## 8. Próximos passos — Sprint 002 (Envio de Frequência CMDE)
Batch Builder + Queue + Workers + Scheduler consumindo o catálogo de motivos MEC v4.2 (Bolsa
Família / Subsistema B), reutilizando: `CmdeClient` (retry/audit já prontos), `MigAuditService`
(rastro por lote), `FeatureFlagService` (rollout gradual do envio) e o Dashboard Técnico (status
de lotes/filas). Ativar `PgpCryptoProvider` apenas se exigido pela especificação oficial.

---
*Fim. Camada operacional madura; base pronta para o fluxo de envio na Sprint 002.*
