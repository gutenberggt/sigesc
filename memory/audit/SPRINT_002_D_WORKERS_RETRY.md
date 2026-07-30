# SPRINT 002.d — Workers + Retry · RELATÓRIO

**Status:** ✅ CONCLUÍDA (aguardando aprovação para iniciar a 002.e).
**Escopo entregue:** Worker que consome a fila (002.c) via `CmdeFrequencyPort`, usando RetryManager,
Audit, Metrics e Correlation ID existentes, com o **Simulador CMDE como provider padrão**.
Reconciliação via `SendReceipt` + totais/estado do lote. **Nenhuma chamada real ao MEC.
Sem Scheduler.**

---

## Regras cumpridas
- Consome **apenas** `MongoFrequencyQueue` + `CmdeFrequencyPort` (nenhuma outra fonte/transporte).
- Usa `RetryManager` (`run_with_retry` + `CMDE_DEFAULT`), `MigAuditService`, `MigMonitoring` e
  Correlation ID (`item.correlation_id`, propagado ponta a ponta).
- **Provider padrão = `CmdeFrequencySimulator`** (nenhuma chamada real ao MEC).
- **Todos os caminhos auditados** (`operation = FREQUENCY_ITEM_<estado>`).

## Entregas (arquivos)
- **`mig/cmde/worker.py`** — `FrequencyWorker`:
  - `bootstrap()` — executa `ensure_indexes()` e **valida a infraestrutura** (ping da coleção +
    conferência dos índices `uq_idem`/`reserve_idx`/`lease_idx`; erro → `MigError`).
  - `process_one(tenant)` — reserva → `start_processing` → envia via porta com RetryManager →
    reconcilia por item → grava `SendReceipt` → audita → reconcilia o lote.
  - `run(tenant, max_items, requeue_first)` — loop de drenagem (com `requeue_expired` no início);
    **sem Scheduler**.
- **`mig/cmde/frequency_repository.py`** — `save_receipt`, `batch_item_counts`, `update_batch`.
- **`mig/cmde/frequency_simulator.py`** — contagem de tentativas transitórias por
  `(correlation_id + aluno)` (itens de um mesmo lote compartilham o correlation_id).

## Mapa de caminhos de processamento (máquina de estados + auditoria)
| Situação | Transição de estado | Recibo | Auditoria |
|---|---|---|---|
| Aceite | → **SUCCESS** | accepted=True, `mec_protocol`, `raw_response_hash` | `FREQUENCY_ITEM_SUCCESS` (records_accepted=1) |
| Rejeição de negócio | `fail(recoverable=False)` → **FAILED** | accepted=False, code/reason | `FREQUENCY_ITEM_FAILED` (records_rejected=1) |
| Erro de transporte (após retries) | `fail(recoverable=True)` → **RETRYING**/**DEAD_LETTER** | accepted=False, http_status/erro | `FREQUENCY_ITEM_RETRYING`/`_DEAD_LETTER` |
| Timeout (após retries) | → **RETRYING** | http_status=504 | `FREQUENCY_ITEM_RETRYING` |
| Resposta fora do contrato | `fail(recoverable=True)` → **RETRYING** | code=INVALID_RESPONSE | `FREQUENCY_ITEM_RETRYING` |

Reconciliação de lote: `completed` (todos SUCCESS), `failed` (todos rejeitados), `partial` (misto),
`processing` (ainda há itens não terminais); `totals={items,sent,accepted,rejected}`.

## Testes (8 blocos PASS · `tests/test_mig_cmde_002d.py`)
- **Bootstrap** (ensure_indexes + validação de infraestrutura).
- **Integração com Simulador (accept):** SUCCESS + recibo (protocolo + hash) + auditoria.
- **Múltiplos workers concorrentes:** 4 workers, 30 itens → 30 SUCCESS, **1 recibo por item**
  (sem duplo processamento).
- **Retry recuperável:** 503,503,200 → SUCCESS em 3 tentativas (RetryManager), `attempts=3` auditado.
- **Timeout:** sempre 504 → após retries → RETRYING durável (recibo + auditoria).
- **Rejeição definitiva:** cenário reject → FAILED (não recuperável) + recibo com código.
- **Recuperação após interrupção:** item preso em PROCESSING com lease vencido → `run()` faz
  `requeue_expired` → reprocessa → SUCCESS.
- **Reconciliação de lote:** 1 accepted + 1 rejected → lote `partial` com totais corretos.

**Regressão:** 000/001/001.1 **15/15**, 002.a **12/12**, 002.b **7/7**, 002.c **11 blocos** verdes.
Backend saudável (`/api/mec/metrics` sem auth → 401). Import do worker OK.

## Observações
- O worker NÃO é acionado automaticamente (sem Scheduler nesta etapa); é disparado por chamada
  direta (`run`/`process_one`). O agendamento periódico é escopo da **002.e**.
- O Simulador também audita cada tentativa de transporte (`FREQUENCY_SEND`); o worker audita o
  desfecho do item (`FREQUENCY_ITEM_<estado>`) — visibilidade completa de tentativas + resultado.

## Próximo passo (após aprovação)
**002.e — Scheduler:** acionamento periódico por tenant, guardado por feature flags
(`cmde.frequency.scheduler_enabled`, `cmde.frequency.simulator`, etc.), OFF por padrão em produção.
**Aguardando "sim" do owner.**

## Bloqueadores externos (mantidos)
1. Contrato oficial da API CMDE. 2. Unidade de apuração aceita pelo MEC. 3. Limiares 60%/75% só p/ relatório.
