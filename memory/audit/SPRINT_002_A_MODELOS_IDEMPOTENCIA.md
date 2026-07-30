# SPRINT 002.a — Modelos, Contratos Internos e Idempotência · RELATÓRIO

**Status:** ✅ CONCLUÍDA (aguardando aprovação para iniciar a 002.b)
**Escopo entregue:** modelos de domínio CMDE, DTOs, contratos internos (`QueuePort`,
`IdempotencyStore`, `CmdeFrequencyPort`), idempotência determinística e **Simulador CMDE**
plugável com 5 cenários + modo caótico determinístico/auditável.
**Fora do escopo (não implementado, conforme regra):** envio real ao MEC, Batch Builder,
Queue Manager real (Mongo), Worker, Scheduler. Nenhum endpoint novo; nada ligado ao `server.py`
(apenas biblioteca) — comportamento do sistema inalterado.

---

## Entregas (arquivos)
- **`mig/core/ports.py`** — contratos abstratos genéricos `QueuePort` (enqueue/reserve/complete/
  release/requeue_expired/stats) e `IdempotencyStore` (seen/remember).
- **`mig/core/inmemory.py`** — implementações de REFERÊNCIA em memória (`InMemoryQueue`,
  `InMemoryIdempotencyStore`) para testes/simulador. **NÃO é a fila de produção** (002.c).
- **`mig/core/ids.py`** — `compute_idempotency_key(...)` determinística
  (`sha1(tenant|provider|operation|competencia|student_id|school_inep|payload_version)`).
- **`mig/core/audit.py`** — campos aditivos `scenario` e `simulated` no evento de auditoria
  (backward-compatible, default `None`/`False`).
- **`mig/cmde/dtos.py`** — `FrequencyItemDTO`, `FrequencyBatchRequestDTO` (dry_run padrão True),
  `CmdeFrequencyPayloadDTO` (placeholder até contrato oficial), `CmdeItemResultDTO`,
  `CmdeFrequencyResponseDTO` (com `valid` para resposta fora do contrato).
- **`mig/cmde/frequency_models.py`** — documentos `FrequencyBatch`, `QueueItem`, `SendReceipt`
  (id uuid4, `to_doc()`), com constantes de status.
- **`mig/cmde/frequency_port.py`** — `CmdeFrequencyPort` (porta plugável do envio).
- **`mig/cmde/frequency_simulator.py`** — `CmdeFrequencySimulator` + `SimulatorConfig`.
- **`tests/test_mig_cmde_002a.py`** — testes automatizados (12 checks).

## Idempotência determinística
- Chave = `sha1` das dimensões `(tenant, provider, operation, competencia, student_id,
  school_inep, payload_version)`. Mesmas entradas → mesma chave (índice unique impedirá
  duplicidade na 002.c). Correção de dado → incrementar `payload_version` gera **nova** chave
  (reenvio controlado, auditável). Validado: estabilidade + sensibilidade a aluno/competência/versão.

## Simulador CMDE (provider plugável — parte OFICIAL da arquitetura)
Implementa `CmdeFrequencyPort` (mesmo contrato do cliente real futuro). Seleção real vs. simulado
será por feature flag `cmde.frequency.simulator` (a partir da 002.e). Cada envio simulado registra
**correlation_id, cenário, resultado, métricas (MigMonitoring) e evento de auditoria (MigAuditService)**.

Cenários controlados:
| Cenário | Comportamento | Auditoria |
|---|---|---|
| `accept` | 200, todos aceitos, protocolo `SIM-YYYY-MM-XXXXXXXX` | status=success, records_accepted=N |
| `reject` | parcial: rejeita por `reject_refs` ou `reject_every` (código/motivo) | status=success, records_rejected>0, rejection_reasons |
| `error_502` / `error_503` / `error_504` | levanta `MigUpstreamError/Unavailable` (recuperável) | status=error, http_status/error_code |
| `timeout` | levanta `MigTimeoutError` (504) | status=error, http_status=504 |
| `invalid_response` | `CmdeFrequencyResponseDTO(valid=False)` | status=error, error_code=INVALID_RESPONSE |

**Modo caótico (`chaos=True`):** cenário sorteado por peso, **determinístico** (RNG por
`seed:correlation_id:call_index`) e **auditável** (cenário sorteado gravado). Mesmo seed → mesma
sequência; seeds diferentes → sequências diferentes. `transient_failures=N` faz erros/timeout
falharem N vezes por correlation_id e depois aceitarem — valida o RetryManager de ponta a ponta.

## Testes automatizados — 12/12 PASS ✅ (`tests/test_mig_cmde_002a.py`)
idempotency_key (determinística + sensível) · modelos/DTOs (defaults) · IdempotencyStore ·
QueuePort (reserva atômica, isolamento por tenant, lease/requeue) · simulador ACCEPT (protocolo+
audit+métricas) · REJECT (parcial) · ERRO 503 + TIMEOUT 504 · RESPOSTA INVÁLIDA ·
simulador+RetryManager (falha 2x→aceita na 3ª, correlation_id estável) · modo caótico
determinístico · `audit.record` mapeia `scenario`/`simulated`.

**Regressão:** `tests/test_mig_cmde.py` (Sprint 000/001/001.1) segue **15/15 PASS**. Backend
saudável (`/api/mec/metrics` sem auth → 401). Import dos novos módulos OK. Zero endpoint novo.

## Bloqueadores externos (mantidos em aberto — não impedem 002.a–002.e via Simulador)
1. **Contrato oficial da API CMDE de frequência** (endpoint/payload/limites/protocolo).
2. **Unidade de apuração aceita pelo MEC** (consolidação por dia ≥50%/dia vs. carga horária).
3. **Limiares 60%/75%** — apenas para relatório, nunca para bloquear envio.

## Próximo passo (após aprovação)
**002.b — Batch Builder:** montar lotes a partir do SSoT (`attendance`), read-only, com dry-run,
consumindo `attendance_utils.compute_monthly_valid_absences` (sem regra nova), persistindo
`FrequencyBatch` + `QueueItem` com `idempotency_key`. **Aguardando "sim" do owner.**
