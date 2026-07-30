# SPRINT 002 — Plano de Execução (Sub-Sprints) · Envio de Frequência CMDE

> **Status:** 📐 DETALHAMENTO (nenhum código). Aguarda **aprovação deste plano de execução**
> antes de qualquer implementação.
> **Base:** `SPRINT_002_PLANO_ARQUITETURAL_CMDE.md` (APROVADO).
> **Princípios herdados:** SSoT inegociável · router fino · service sem HTTP direto · todo IO externo
> via `BaseGovClient`+`RetryManager` · todo evento auditado com `correlation_id` · multi-tenant fail-closed
> · feature flags OFF por padrão em produção.
> **Ordem obrigatória:** 002.a → 002.b → 002.c → 002.d → 002.e → 002.f, com **gate humano** entre cada uma.

---

## Requisito transversal — Simulador CMDE de Homologação (Mock Provider)

Requisito **oficial** da Sprint 002. Permite exercitar o fluxo completo (Builder → Queue → Worker →
Retry → Audit → Metrics → Idempotência) **sem depender do ambiente externo do MEC**.

**Estratégia (injeção de dependência, sem `if mock` espalhado):**
- O `FrequencySendService`/`Worker` recebem um **cliente que respeita um contrato** (`CmdeFrequencyPort`).
  Em produção → `CmdeClient` real (`BaseGovClient`). Em homologação/testes → `CmdeFrequencySimulator`.
- Seleção por **feature flag** `cmde.frequency.simulator` (por tenant/ambiente) — nunca liga sozinho
  em produção; default OFF em produção, ON em ambiente de teste.
- O simulador NÃO altera o transporte real: implementa o mesmo método `enviar_frequencia(payload)` e
  devolve `CmdeFrequencyResponseDTO`, exercitando `RetryManager`/audit exatamente como o real.

**Cenários suportados (determinísticos, controláveis por regra/config do simulador):**
| Cenário | Comportamento simulado | O que valida |
|---|---|---|
| Aceite de lote | 200, todos os itens `accepted` + protocolo | Reconciliação `completed`, métricas `accepted` |
| Rejeição de registros | 200 parcial: alguns itens `rejected` (código/motivo) | `partial`, painel de rejeições, sem retry de negócio |
| Erro temporário 502/503/504 | levanta `MigUpstreamError/Unavailable` N vezes e depois 200 | RetryManager (backoff), `attempts`, idempotência no reenvio |
| Timeout | levanta `MigTimeoutError` | retry recuperável + esgotamento → `error` reagendável |
| Resposta inválida | corpo não parseável / schema fora do contrato | tratamento defensivo → `error`, sem corromper métricas |

**Gatilhos de cenário (sem poluir o código de negócio):** o cenário é escolhido por
configuração do simulador (ex.: mapa `student_id`/`competencia` → resultado, ou contadores
"falhar as 2 primeiras tentativas"), definido apenas nos testes/homologação.

**Entrega do simulador:** dentro da **002.a** (contrato `CmdeFrequencyPort` + esqueleto do
simulador) e amadurecido em cada sub-sprint que precisar dele (002.b usa aceite; 002.d usa
erros/timeout/retry; 002.f usa todos os cenários no piloto).

---

## 002.a — Modelos, contratos internos e idempotência

**Objetivo:** fundação de dados e contratos, sem enviar nada.
**Entregas:**
- DTOs em `mig/cmde/dtos.py`: `FrequencyItemDTO`, `FrequencyBatchRequestDTO`,
  `CmdeFrequencyPayloadDTO` (placeholder até contrato oficial), `CmdeFrequencyResponseDTO`.
- Contratos (core, genéricos): `QueuePort`, `IdempotencyStore`, `CmdeFrequencyPort`.
- `FrequencyRepository` (cmde): acesso às coleções `mig_cmde_frequency_batches`,
  `mig_cmde_send_queue`, `mig_cmde_send_receipts` + `mig_idempotency` (core). Índices previstos.
- Função de **idempotency_key determinística** (`sha1(tenant|provider|op|competencia|student_id|
  school_inep|payload_version)`) + índice unique.
- Esqueleto do **Simulador CMDE** implementando `CmdeFrequencyPort` (cenário "aceite" inicial).
**Não faz:** build/enqueue/send/scheduler.
**Testes:** unit de idempotency_key (determinística e colisão-segura); shape dos DTOs;
repositório com Mongo de teste (CRUD + índice unique rejeita duplicata); simulador devolve DTO válido.
**Critério de aceite:** coleções/índices definidos; chave idempotente estável; simulador plugável;
`test_mig_cmde.py` (15/15) **inalterado** (contratos existentes preservados).
**Dependências:** nenhuma.

## 002.b — Batch Builder

**Objetivo:** montar lotes a partir do SSoT (`attendance`), read-only, com dry-run.
**Entregas:**
- `FrequencyBatchBuilder`: lê `attendance` por (tenant, competência, escopo), consolida por
  `(student_id, competencia)` via `attendance_utils.compute_monthly_valid_absences` (SEM regra nova).
- `FrequencyMapper` (item consolidado → `FrequencyItemDTO`) e `FrequencyValidators` (prontidão:
  INEP escola, identificador do aluno, competência fechada) reusando `ValidationEngine`.
- Persistência do `batch` (draft/ready) + `queue items` (pending) com upsert por idempotency_key.
- Endpoint fino `GET/POST /mec/frequency/batches` (preview `dry_run=true` padrão; `ready` só p/
  competência fechada). Auditoria da operação `FREQUENCY_BATCH_BUILT` com correlation_id.
**Não faz:** enviar (worker/scheduler).
**Testes:** consolidação espelha o helper SSoT; re-run não duplica itens (idempotência); prontidão
separa itens válidos/pendentes; dry-run não persiste fila; competência aberta = preview informativo.
**Critério de aceite:** preview E2E no dashboard; contagens conferem com a tela de frequência (SSoT);
zero escrita em coleções pedagógicas.
**Dependências:** 002.a.

## 002.c — Queue Manager

**Objetivo:** fila durável no MongoDB com reserva atômica.
**Entregas:**
- Implementação `QueuePort` sobre `mig_cmde_send_queue`: `enqueue`, `reserve` (find_one_and_update
  pending→leased + lease_until), `complete`, `release`, `requeue_expired`.
- Backpressure por tenant (limite de `leased` simultâneos) e paginação configurável por flag.
- Endpoints de observação `GET /mec/frequency/queue` (status agregados) — fino, delega ao service.
**Não faz:** envio HTTP (o worker vem na 002.d).
**Testes:** 2 "consumidores" não reservam o mesmo item (atomicidade); lease expirado volta a pending;
isolamento por tenant; backpressure respeita o teto.
**Critério de aceite:** fila drena em ordem, sem corrida, sem vazamento entre tenants.
**Dependências:** 002.b.

## 002.d — Workers + Retry

**Objetivo:** processar a fila enviando via `CmdeFrequencyPort` (real OU simulador) com retry, audit
e reconciliação de resposta.
**Entregas:**
- `FrequencyWorker` (idempotente/reentrante): reserva item → mapper → `port.enviar_frequencia` (com
  `RetryManager`/`CMDE_DEFAULT`) → grava recibo (`mig_cmde_send_receipts`) → reconcilia item+batch.
- `CmdeClient.enviar_frequencia()` (transporte real via `BaseGovClient`, correlation_id do batch).
- Tratamento de aceite/rejeição/erro/timeout/resposta inválida (usa **todos os cenários do
  Simulador**). Uso dos campos de audit já reservados (`records_sent/accepted/rejected/
  rejection_reasons`) + métricas (`students_sent/accepted/rejected/processing_rate`).
- Verificação pré-envio em `mig_idempotency` (curto-circuita reenvio de item já aceito) + header
  `Idempotency-Key` quando suportado.
**Não faz:** disparo automático (scheduler é 002.e); rodada manual só via endpoint.
**Testes (com Simulador):** aceite total; rejeição parcial → `partial`; 502/503/504 → retry→sucesso;
timeout→esgota→`error` reagendável; resposta inválida→`error` sem corromper métricas; **invariante
de idempotência** (`accepted ≤ 1` por tenant/competência/aluno); crash no meio (lease) → reprocessa
sem duplo aceite; multi-tenant concorrente.
**Critério de aceite:** fluxo completo verde contra o Simulador; audit com correlation_id ponta a
ponta; métricas consistentes; sem duplicação/perda.
**Dependências:** 002.c.

## 002.e — Scheduler

**Objetivo:** automação periódica por tenant, guardada por feature flags (OFF por padrão em prod).
**Entregas:**
- `MigScheduler` (core, genérico): tarefa periódica no lifespan do FastAPI (ou APScheduler — decidir
  na implementação) que, por tenant com `cmde.frequency.scheduler_enabled=true`, dispara enqueue de
  batches `ready` + drenagem via worker. Nunca envia com `cmde.enabled=false` ou competência aberta.
- Flags novas: `cmde.frequency.scheduler_enabled`, `cmde.frequency.simulator`,
  `cmde.frequency.batch_page_size`, `cmde.frequency.max_inflight_per_tenant` — todas auditadas
  (reuso do `FEATURE_FLAG_UPDATED` já homologado).
- Modo MANUAL preservado (endpoint dispara build/enqueue/run) usando o MESMO service.
**Testes:** scheduler OFF = zero efeito; liga só o tenant com flag; respeita `cmde.enabled` e
competência fechada; não sobrepõe execuções (lock por tenant).
**Critério de aceite:** liga/desliga por flag sem deploy; auditoria da mudança de flag; sem envio
acidental de mês em curso.
**Dependências:** 002.d.

## 002.f — Homologação e piloto gradual

**Objetivo:** validar ponta a ponta e liberar com segurança.
**Entregas / passos:**
1. **Homologação com Simulador:** roda todos os cenários (aceite, rejeição, 502/503/504, timeout,
   resposta inválida) em ambiente de teste; relatório de evidências.
2. **Homologação MEC (externo):** só após confirmação do **contrato oficial** — exercitar contra o
   ambiente de **HOMOLOGAÇÃO** do CMDE (nunca produção) com 1 tenant piloto + 1 competência fechada
   pequena (1 escola/turma).
3. **Dry-run em produção:** builder em produção sem enviar (preview/prontidão).
4. **Piloto controlado:** ligar `scheduler_enabled` para 1 tenant + 1 escola; observar recibos,
   rejeições e métricas por período; rollback = desligar a flag (sem reverter dados).
5. **Rollout por tenant:** expandir conforme aprovação; ajustar teto de lote/concorrência por flag.
6. **Gate humano final:** liberação ampla só com homologação assistida + aprovação do owner.
**Critério de aceite:** relatório de homologação (Simulador + MEC homologação) + aprovação formal.
**Dependências:** 002.e + bloqueadores externos resolvidos.

---

## Bloqueadores externos (mantidos em aberto — necessários antes de 002.f/produção)
1. **Contrato oficial da API CMDE de frequência** — endpoint, verbo, formato do payload,
   granularidade, janela de competência, limites de lote, protocolo/recibo. *(Bloqueia o payload
   real e a homologação MEC; NÃO bloqueia 002.a–002.e usando o Simulador.)*
2. **Unidade de apuração aceita pelo MEC** — consolidação por DIA (≥50%/dia, regra LOCAL do owner)
   vs. apuração por CARGA HORÁRIA. *(Precisa ser defensável em auditoria antes do piloto.)*
3. **Limiares de condicionalidade (60% / 75%)** — usados **apenas para relatório**, nunca para
   bloquear envio.

## Observações de sequência
- **002.a–002.e podem ser 100% desenvolvidas e testadas com o Simulador**, independentes do MEC.
- O **contrato oficial** só é imprescindível para o transporte real (`CmdeClient.enviar_frequencia`)
  e para a homologação externa (002.f) — por isso o Simulador destrava o progresso.
- Cada sub-sprint fecha com testes verdes + gate humano; nada avança sem aprovação.

> **A implementação permanece BLOQUEADA até a aprovação deste plano de execução.**
> Próximo passo após o "sim": iniciar **002.a** (modelos, contratos, idempotência e esqueleto do Simulador).
