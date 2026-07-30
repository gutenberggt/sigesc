# SPRINT 002.c — Queue Manager (Fila Durável MongoDB) · RELATÓRIO

**Status:** ✅ CONCLUÍDA (aguardando aprovação para iniciar a 002.d).
**Escopo entregue:** fila durável em MongoDB com máquina de estados, reserva atômica (lease),
requeue por expiração, backpressure por tenant, limite de tentativas → DEAD_LETTER, métricas de
fila e índices. **Sem Worker, sem Scheduler, sem envio ao MEC.**

---

## Máquina de estados dos itens
`PENDING → RESERVED → PROCESSING → SUCCESS` · `PROCESSING → FAILED` (não recuperável) ·
`PROCESSING → RETRYING` (recuperável, `attempts < max`) → reservável de novo ·
`RETRYING/PROCESSING → DEAD_LETTER` (excedeu `max_attempts`) ·
`RESERVED/PROCESSING → PENDING` (requeue por expiração de lease).
Estados: **PENDING, RESERVED, PROCESSING, RETRYING, SUCCESS, FAILED, DEAD_LETTER**.

## Entregas (arquivos)
- **`mig/cmde/queue.py`** — `MongoFrequencyQueue`:
  - `reserve(tenant, lease_seconds)` — reserva ATÔMICA via `find_one_and_update` (PENDING ou
    RETRYING com `next_attempt_at<=agora`), incrementa `attempts`, grava `reserved_at`/
    `first_reserved_at`; respeita **backpressure** (`_inflight_count >= limite → None`).
  - `renew_lease(item_id, lease_seconds)` — renovação de lease para itens in-flight.
  - `start_processing` (RESERVED→PROCESSING), `succeed` (→SUCCESS), `fail(recoverable)`
    (→FAILED | RETRYING com backoff | DEAD_LETTER), `release`, `complete`.
  - `requeue_expired()` — devolve itens in-flight com `lease_until` vencido → PENDING.
  - `queue_metrics(tenant?)` — pendentes/processando/retries/dead_letters/success/failed +
    **tempo médio em fila (ms)**.
  - `ensure_indexes()` — `uq_idem` (unique em `idempotency_key`), `reserve_idx`
    `(tenant,status,next_attempt_at)`, `lease_idx` `(status,lease_until)`, `metrics_idx`
    `(tenant,status)`. **Índices criados na base real** (verificado).
- **`mig/cmde/frequency_models.py`** — `QUEUE_STATUSES` = máquina nova; `QueueItem` ganhou
  `next_attempt_at`, `reserved_at`, `first_reserved_at`; default `status="PENDING"`.
  `batch_builder` passou a criar itens em `PENDING`.
- **`mig/cmde/service.py`** — `metrics()` agora inclui `queue` (métricas da fila por tenant).
- **Frontend** `pages/MECIntegration.js` — card **"Fila de Envio"** na aba Operação Técnica
  (pendentes, processando, retries, dead letters, concluídos, tempo médio em fila). Screenshot OK.

## Integração com idempotência existente
Índice **unique** em `idempotency_key` + `enqueue` via `$setOnInsert` → nunca duplica item
(coerente com o upsert do Batch Builder da 002.b).

## Testes de concorrência e recuperação (11 blocos PASS · `tests/test_mig_cmde_002c.py`)
- `ensure_indexes` idempotente; `enqueue` idempotente (unique).
- **Reserva simultânea:** 20 itens, 40 `reserve` concorrentes → 20 reservados, **zero duplicidade**.
- **Expiração de lease → requeue automático** (20 in-flight vencidos voltam a PENDING).
- **Renovação de lease** impede requeue.
- **Múltiplos tenants:** reserva isolada por tenant.
- **Backpressure:** limite de 2 in-flight → 3ª reserva bloqueada; concluir 1 libera a próxima.
- **RETRYING×2 → DEAD_LETTER** ao exceder `max_attempts=3` (depois não é mais reservável).
- **Falha não recuperável → FAILED** (terminal).
- **Grande volume:** 500 itens drenados até SUCCESS.
- **Métricas da fila:** contagens por estado + tempo médio em fila.

**Regressão:** 002.a **12/12**, 002.b **7/7**, 000/001/001.1 **15/15** verdes. E2E:
`/api/mec/metrics` passa a expor a seção `queue`. Backend saudável.

## Observações
- `MongoFrequencyQueue` é a fila REAL desta sprint; a `InMemoryQueue` (002.a) permanece como
  implementação de referência para testes do contrato genérico `QueuePort`.
- `ensure_indexes()` deve ser chamado no startup do backend na 002.d (quando o Worker for ligado);
  os índices já foram criados na base atual.

## Próximo passo (após aprovação)
**002.d — Workers + Retry:** consumir a fila (reserve→process→succeed/fail) enviando via
`CmdeFrequencyPort` (Simulador ou cliente real), com RetryManager, recibos e reconciliação.
**Aguardando "sim" do owner.**

## Bloqueadores externos (mantidos)
1. Contrato oficial da API CMDE. 2. Unidade de apuração aceita pelo MEC. 3. Limiares 60%/75% só p/ relatório.
