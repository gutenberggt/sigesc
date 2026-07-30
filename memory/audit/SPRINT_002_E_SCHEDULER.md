# SPRINT 002.e — Scheduler · RELATÓRIO

**Status:** ✅ CONCLUÍDA (aguardando aprovação para iniciar a 002.f).
**Escopo entregue:** Scheduler que apenas orquestra o acionamento periódico do `FrequencyWorker`,
guardado por feature flag (OFF por padrão), habilitável por tenant, com janela operacional, lock
por tenant, auditoria de cada disparo, métricas e painéis no Dashboard (Scheduler + Dead Letters).
**Provider ativo permanece o Simulador CMDE — nenhuma chamada real ao MEC. Sem provider real/HTTP.**

---

## Regras cumpridas
- Responsabilidade ÚNICA = orquestrar o Worker. O Scheduler **não conhece** regra de negócio,
  Queue, RetryManager, Provider nem MEC — dispara o Worker via **runner injetável**.
- Usa **exclusivamente** o `FrequencyWorker` (runner padrão = `FrequencyWorker(db).run`).
- **OFF por padrão em produção** (`cmde.frequency.scheduler_enabled` default False).
- **Ativação somente por feature flag**, habilitável **por tenant**.
- **Janela operacional** configurável por tenant. **Lock** por tenant (compare-and-set atômico).
- **Auditoria de cada disparo** (`SCHEDULER_TICK`) + **métricas** (`scheduler.tick` + eventos).
- **Simulador CMDE** como provider ativo; nenhuma chamada real ao MEC.

## Entregas (arquivos)
- **`mig/cmde/scheduler.py`** — `FrequencyScheduler`:
  `tick()` (flag → janela → lock → runner → last/next_run + auditoria + release),
  `set_config`/`get_config` (janela/intervalo/max_items por tenant), `status_view()`,
  lock por `_acquire_lock`/`_release_lock` (atômico), disparo manual (`manual=True`) ignora
  flag/janela.
- **`mig/core/feature_flags.py`** — flags `cmde.frequency.scheduler_enabled` (False) e
  `cmde.frequency.simulator` (True) no `DEFAULT_FLAGS`.
- **`mig/cmde/queue.py`** — `reprocess(item_id)` (DEAD_LETTER/FAILED → PENDING, idempotente).
- **`mig/cmde/service.py`** — `scheduler_status`/`scheduler_set_config`/`scheduler_tick`,
  `dead_letters(page,page_size)`, `reprocess_dead_letter` (audita `FREQUENCY_ITEM_REPROCESS`).
- **`routers/mec_integration.py`** — endpoints finos: `GET /mec/scheduler`,
  `POST /mec/scheduler/config`, `POST /mec/scheduler/tick`, `GET /mec/dead-letters`,
  `POST /mec/dead-letters/{item_id}/reprocess`.
- **Frontend** `pages/MECIntegration.js` + `services/api.js` — painéis **Scheduler de Envio**
  (Status ON/OFF, Tenant, Feature Flag, Última/Próxima execução, Último resultado, disparo manual)
  e **Dead Letters** (Correlation ID, Tenant, Competência, Motivo, Tentativas, Última tentativa,
  botão **Reprocessar** respeitando idempotência). Screenshot confirmado.

## Testes (7 blocos PASS · `tests/test_mig_cmde_002e.py`)
- **Flag OFF (default)** → `disabled` (Worker NÃO acionado).
- **Flag ON (tenant A)** → `ran` + auditoria `SCHEDULER_TICK` + métrica `scheduler.tick` + last/next_run.
- **Multi-tenant:** B permanece OFF; runner nunca chamado para B.
- **Lock:** 2 ticks concorrentes → 1 `ran`, 1 `locked` (só um Worker executa).
- **Janela operacional:** fora da janela → `outside_window`; disparo manual ignora.
- **Integração real Worker + Simulador:** 5 itens → 5 SUCCESS, protocolo `SIM-…`
  (**prova de nenhuma chamada real ao MEC**), `port` é `CmdeFrequencySimulator`.
- **Dead letter + reprocessamento:** DEAD_LETTER → PENDING, `attempts=0`, mesmo `idempotency_key`
  (sem duplicação).

**Regressão:** 000/001/001.1 **15/15** (ajustado para tolerar novas flags), 002.a **12/12**,
002.b **7/7**, 002.c **11 blocos**, 002.d **8 blocos** verdes.
**E2E:** `GET /mec/scheduler` (status OFF, provider simulator), `GET /mec/dead-letters` (paginado),
`POST /mec/scheduler/tick` (manual → `ran`), 401 sem auth.

## Observações
- O Scheduler NÃO auto-inicia um loop em background nesta etapa (sem daemon/timer no boot):
  o ciclo é `tick()` disparado por endpoint (`/mec/scheduler/tick`) ou por um agendador externo
  futuro. O acoplamento a um timer periódico do processo pode ser adicionado quando o piloto exigir.
- A seleção real-vs-simulador via `cmde.frequency.simulator` será efetivada na 002.f (transporte real).

## Próximo passo (após aprovação)
**002.f — Homologação e piloto gradual** (Simulador → homologação MEC → dry-run → piloto → rollout).
**Aguardando "sim" do owner** e a resolução dos bloqueadores externos (incl. normalização de caracteres).

## Bloqueadores externos (mantidos + novo)
1. Contrato oficial da API CMDE de frequência.
2. Unidade de apuração aceita pelo MEC.
3. Limiares 60%/75% — apenas para relatório.
4. **[NOVO] Normalização de caracteres na integração CMDE** (ver PRD/ROADMAP): validar UTF-8,
   caixa alta obrigatória, acentos, cedilha, til, caracteres especiais e tamanho máximo dos campos
   textuais. Normalização SOMENTE na camada Mapper/Serializer — **o SSoT do SIGESC nunca perde
   acentos/cedilhas/caracteres originais**.
