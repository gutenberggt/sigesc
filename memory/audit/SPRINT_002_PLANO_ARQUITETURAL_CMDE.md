# SPRINT 002 — Envio de Frequência CMDE · PLANO ARQUITETURAL

> **Status:** 📐 PLANEJAMENTO (nenhum código nesta etapa).
> **Pré-condição:** Sprint 001.1 HOMOLOGADA (audit persistente, métricas, correlation_id,
> feature flags auditáveis, retry, dashboard técnico, testes de resiliência). ✅
> **Regra de ouro:** este documento é a fonte da verdade do desenho. **NÃO** criar Batch Builder,
> Queue, Workers ou Scheduler antes da aprovação formal do owner.
> **Princípio herdado:** SSoT inegociável (a frequência enviada é apenas REPRESENTAÇÃO do dado
> pedagógico já consolidado — nunca uma nova regra de cálculo). Router fino, service sem HTTP
> direto, todo IO externo pelo `BaseGovClient` + `RetryManager`, todo evento auditado com
> `correlation_id`, todo dado escopado por tenant.

---

## 0. Objetivo e escopo

**Objetivo:** enviar a frequência escolar consolidada ao MEC (CMDE / Sistema Presença — Gestão
Presente) de forma **assíncrona, idempotente, auditável e faseável**, reusando integralmente o
núcleo operacional já homologado (`mig/core`).

**Dentro do escopo (Sprint 002):**
- Construção de lotes (batches) de frequência a partir do SSoT (coleção `attendance`).
- Enfileiramento e processamento assíncrono com workers + scheduler.
- Envio via `CmdeClient`/`BaseGovClient` com retry, correlation_id e auditoria.
- Tratamento de aceites/rejeições do MEC e reconciliação por aluno.
- Visualização no Dashboard Técnico (fila, lotes, rejeições) — reuso da UI existente.

**Fora do escopo (sprints futuras):**
- Envio de matrícula/censo/notas (outros domínios CMDE).
- Assinatura/criptografia PGP do payload (abstração `CryptoProvider` já reservada).
- Correção retroativa de dados pedagógicos (governança de migração é outra trilha).

**Premissa a confirmar com o owner antes da implementação (bloqueadores externos):**
1. **Contrato oficial da API CMDE de frequência** (endpoint, verbo, formato do payload,
   granularidade: mensal por aluno × componente ou consolidado diário, janela de competência,
   limites de tamanho de lote, formato de protocolo/recibo).
2. **Unidade de apuração aceita pelo MEC** (por DIA consolidado vs. por CARGA HORÁRIA). O sistema
   já consolida por dia (`attendance_utils.compute_monthly_valid_absences`, corte ≥50%/dia — regra
   LOCAL do owner). Precisa ser confirmada como defensável perante o Sistema Presença.
3. **Limiares de condicionalidade** (60% 4–5 anos / 75% 6–17 anos) — usados só para relatório, não
   para bloquear envio.

---

## 1. Arquitetura do fluxo de envio de frequência

Fluxo em 6 estágios, todos observáveis e retomáveis:

```
[SSoT: attendance]
      │  (1) BATCH BUILD  — seleção competência + consolidação (read-only do SSoT)
      ▼
[mig_cmde_frequency_batches]  (lote: status=draft→ready)
      │  (2) ENQUEUE      — enfileira itens do lote
      ▼
[mig_cmde_send_queue]  (item: status=pending)
      │  (3) WORKER       — consome fila, monta payload, envia via CmdeClient
      ▼
[BaseGovClient + RetryManager]  ──HTTP──►  API CMDE (MEC Gestão Presente)
      │  (4) RESPONSE     — parse aceite/rejeição por aluno
      ▼
[mig_cmde_send_receipts]  (recibo por item + protocolo MEC)
      │  (5) RECONCILE    — atualiza status do lote (accepted/rejected/partial)
      ▼
[mig_audit_events + métricas]  (6) AUDIT/METRICS  — correlation_id ponta a ponta
      ▲
[SCHEDULER]  dispara (1)/(2)/(3) periodicamente por tenant (feature-flag controlado)
```

**Camadas (mantém o isolamento Core / Providers / CMDE):**
- **`mig/core`** (agnóstico, reuso): `RetryManager`, `MigAuditService`, `MigMonitoring`,
  `FeatureFlagService`, `ids.generate_correlation_id`, `BaseGovClient`. **+ NOVO, genérico:**
  contratos de fila (`QueuePort`), de scheduler (`SchedulerPort`) e de idempotência
  (`IdempotencyStore`) — reutilizáveis por qualquer provider governamental futuro.
- **`mig/cmde`** (isolado, específico): `FrequencyBatchBuilder`, `FrequencyMapper`,
  `FrequencyValidators`, `FrequencySendService`, `FrequencyRepository`, extensão do `CmdeClient`
  com o método de envio de frequência. **Nenhuma regra CMDE vaza para o core.**
- **`routers/mec_integration.py`** (fino): novos endpoints operacionais delegando ao service.

---

## 2. Componentes e responsabilidades

| Componente | Camada | Responsabilidade | NÃO faz |
|---|---|---|---|
| `FrequencyBatchBuilder` | cmde | Lê `attendance` do SSoT p/ (tenant, competência, escopo), consolida por aluno×competência, gera itens do lote com **chave de idempotência determinística** | Não recalcula regra pedagógica nova; não faz HTTP |
| `FrequencyMapper` | cmde | Traduz item consolidado SIGESC → DTO de payload CMDE (INEP, CPF/NIS, competência, % ou faltas) | Não decide o que enviar |
| `FrequencyValidators` | cmde | Prontidão do item (INEP escola, identificador do aluno, competência fechada) — reusa `ValidationEngine` | Não persiste |
| `FrequencyRepository` | cmde | Acesso exclusivo às coleções de batch/queue/receipt | Não conhece transporte |
| `FrequencySendService` | cmde | Orquestra build→enqueue→send→reconcile; audita cada passo com correlation_id | Não faz HTTP direto (usa `CmdeClient`) |
| `CmdeClient.enviar_frequencia()` | cmde | Única saída HTTP de frequência; compõe `BaseGovClient` + retry + correlation_id | Não tem regra de negócio |
| `QueuePort` / impl Mongo | core | Enfileirar/reservar/concluir itens com lock atômico e visibilidade (lease) | — |
| `FrequencyWorker` | cmde (runner) | Loop que reserva itens `pending`, envia, grava recibo, reconcilia | Não é chamado direto por HTTP (idempotente e reentrante) |
| `MigScheduler` | core (runner) | Dispara build/enqueue/worker por tenant em intervalo, respeitando feature flags | Não contém regra CMDE |
| Router `/mec/frequency/*` | router | Auth/permissão, parse, delegação, resposta | Sem regra de negócio |

---

## 3. Modelo de domínio e DTOs

### 3.1 Coleções novas (append/estado — nunca tocam coleções pedagógicas)
- **`mig_cmde_frequency_batches`**
  `{ id, correlation_id, tenant, environment, competencia (YYYY-MM), scope {school_id?, class_id?},
    status (draft|ready|processing|completed|partial|failed), totals {items, sent, accepted, rejected},
    created_by, created_at, updated_at }`
- **`mig_cmde_send_queue`** (itens de envio)
  `{ id, batch_id, correlation_id, tenant, idempotency_key, student_id, school_inep, competencia,
    payload_snapshot (consolidado, sem segredos), status (pending|leased|sent|accepted|rejected|error),
    attempts, lease_until, last_error, created_at, updated_at }`
- **`mig_cmde_send_receipts`** (resposta do MEC por item)
  `{ id, queue_item_id, batch_id, correlation_id, tenant, mec_protocol, http_status,
    accepted (bool), rejection_code, rejection_reason, raw_response_hash, received_at }`
- **`mig_idempotency`** (genérico, core) — guarda `idempotency_key → resultado` para curto-circuitar reenvio.

Índices previstos: `send_queue {tenant, status, lease_until}`, `{idempotency_key unique}`,
`batches {tenant, competencia, status}`, `receipts {queue_item_id}`.

### 3.2 DTOs (contratos explícitos, em `mig/cmde/dtos.py`)
- `FrequencyItemDTO` — consolidado por aluno: `{ student_id, cpf, nis, inep_aluno, school_inep,
  competencia, dias_letivos, faltas_validas, frequencia_percentual, situacao }`.
- `FrequencyBatchRequestDTO` — parâmetros do build: `{ competencia, school_id?, class_id?, dry_run }`.
- `CmdeFrequencyPayloadDTO` — payload EXATO da API CMDE (a definir com o contrato oficial).
- `CmdeFrequencyResponseDTO` — normalização da resposta: `{ protocol, items:[{ref, accepted, code, reason}] }`.

> A fórmula de `faltas_validas`/`frequencia_percentual` **NÃO é nova**: consome
> `attendance_utils.compute_monthly_valid_absences` (SSoT). O mapper apenas traduz.

---

## 4. Estratégia de construção de lotes (Batch Builder)

- **Entrada:** `(tenant, competencia=YYYY-MM, escopo opcional school_id/class_id)`.
- **Fonte:** coleção `attendance` filtrada por tenant + `academic_year`/mês, **somente leitura**.
- **Consolidação:** por `(student_id, competencia)` via helper SSoT existente (dias letivos,
  faltas válidas, % frequência). Sem duplicação de contagem (o helper já consolida por dia).
- **Prontidão:** `FrequencyValidators` marca itens não-prontos (sem INEP escola / sem
  identificador de aluno / competência não fechada) → ficam FORA da fila, listados como pendências.
- **Saída:** cria 1 `batch` (status `draft`) + N `queue items` (status `pending`) com
  `idempotency_key` determinística (ver §7).
- **`dry_run=true` (padrão):** monta e retorna o preview (contagens, amostra, pendências) **sem
  persistir a fila** — espelha o padrão já usado nas migrações do sistema.
- **Fechamento de competência:** só permite `ready` para competências encerradas (evita reenvio de
  mês em curso); competência aberta = preview informativo.

---

## 5. Estratégia de filas e processamento assíncrono

- **Fila durável no MongoDB** (`mig_cmde_send_queue`) — sem broker externo (mantém a stack atual:
  FastAPI + MongoDB). Contrato abstrato `QueuePort` no core permite trocar por Redis/SQS no futuro.
- **Reserva atômica (lease):** worker faz `find_one_and_update({status:pending}, {status:leased,
  lease_until: now+T})` — garante que 1 item é processado por 1 worker de cada vez.
- **Visibility timeout:** item `leased` cujo `lease_until` expirou volta a `pending` (worker morreu)
  → reprocessável, protegido por idempotência contra duplo-envio.
- **Concorrência controlada:** N itens por ciclo, tamanho de página configurável por feature flag.
- **Backpressure:** limite de itens `leased` simultâneos por tenant (evita saturar a API do MEC).

## 6. Estratégia de workers e scheduler

- **`FrequencyWorker`** (idempotente/reentrante): reserva item → monta payload (mapper) → envia
  (`CmdeClient` + retry) → grava recibo → atualiza status do item e agrega no batch. Cada item
  carrega o **`correlation_id` do batch** (rastreio ponta a ponta) + um `attempt_id` por tentativa.
- **`MigScheduler`** (core, genérico): tarefa periódica (APScheduler já é padrão comum, ou task
  asyncio no lifespan do FastAPI — decidir na implementação) que, **por tenant**, dispara:
  (a) enqueue de batches `ready`; (b) drenagem da fila pelo worker. Tudo **guardado por feature
  flags** (`cmde.frequency.scheduler_enabled`, por tenant/ambiente) → ativação gradual sem deploy.
- **Modos de operação:** MANUAL (via endpoint, gestor dispara build/enqueue/run) e AUTOMÁTICO
  (scheduler). Ambos usam o mesmo service — o scheduler não tem regra própria.
- **Segurança operacional:** o scheduler NÃO envia nada enquanto `cmde.enabled=false` ou a
  competência não estiver fechada; começa DESLIGADO por padrão em produção.

---

## 7. Idempotência e prevenção de duplicidade

- **Chave determinística por item:** `idempotency_key = sha1(tenant | provider=cmde |
  op=frequency | competencia | student_id | school_inep | payload_version)`. Índice **unique**.
- **No build:** re-rodar o builder para a mesma competência/escopo **não duplica** itens (upsert
  por `idempotency_key`); itens já `accepted` não são recriados.
- **No envio:** antes do HTTP, consulta `mig_idempotency`; se já houve aceite para a chave,
  curto-circuita (marca `accepted` sem reenviar). Se a API CMDE suportar `Idempotency-Key` no
  header, o `CmdeClient` o envia (double-safety).
- **Retomada após crash:** lease expirado → reprocessa; a chave impede duplo aceite.
- **Versão de payload (`payload_version`):** correção de dado gera nova versão → reenvio
  controlado, auditável, sem colidir com o envio anterior.
- **Invariante testável:** `count(accepted por (tenant, competencia, student_id)) ≤ 1`.

---

## 8. Integração com o RetryManager existente

- Reuso direto de `mig/core/retry.py` (`CMDE_DEFAULT` = 3 tentativas, backoff exponencial).
- **Recuperável** (502/503/504/timeout) → retenta dentro do worker (mesma tentativa de item).
- **Não recuperável** (400/401/403 / rejeição de negócio) → NÃO retenta; item vai a `rejected`/`error`
  com motivo; **não** reduz a métrica de forma inconsistente (audit registra `attempts`).
- **Backoff entre ciclos** (nível fila) além do backoff intra-request (nível HTTP): item `error`
  transitório reagenda com atraso crescente até um teto de tentativas.
- `retry_enabled` continua governado por `cmde.retry` (feature flag por tenant/ambiente).

## 9. Integração com Audit/Metrics existentes

- **Cada operação** (build, enqueue, send de item, reconcile, mudança de flag do scheduler) grava
  evento em `mig_audit_events` via `MigAuditService.record(...)` com **o mesmo `correlation_id` do
  batch** — rastreio ponta a ponta de todo o lote.
- **Campos já reservados na Sprint 001** entram em uso agora (sem alterar schema de auditoria):
  `records_sent`, `records_accepted`, `records_rejected`, `rejection_reasons`.
- **Métricas** (`MigAuditService.metrics`) passam a popular `students_sent/accepted/rejected` e
  `processing_rate` (já derivadas por agregação — SSoT operacional). `runtime_counters`
  (`MigMonitoring`) contam requests/retries/ok/erros por provider.
- **Dashboard Técnico:** reusa a página `/admin/mec` (aba Operação Técnica). Novos painéis (só
  frontend, sem regra): "Lotes de Frequência" (competência, status, totais), "Fila" (pendentes/
  processando/erro) e "Rejeições" (aluno, código, motivo). Filtros/paginação já existentes.

## 10. Tratamento de respostas e rejeições do MEC

- Resposta normalizada em `CmdeFrequencyResponseDTO` (`protocol` + itens `{ref, accepted, code, reason}`).
- **Aceite:** item → `accepted`, grava `mec_protocol` no recibo, incrementa `records_accepted`.
- **Rejeição de negócio** (ex.: aluno sem vínculo no CMDE, INEP inválido, competência inválida):
  item → `rejected` com `rejection_code`/`rejection_reason`; **não** retenta; aparece no painel de
  rejeições para ação do gestor (corrigir cadastro → reenviar com nova `payload_version`).
- **Erro de transporte** (5xx/timeout): retry; esgotado → `error` (reagendável).
- **Resposta parcial** (lote com aceites e rejeições): batch → `partial`; reconciliação por item.
- **Persistência de evidência:** `raw_response_hash` no recibo (auditoria) sem guardar segredos.
- **Reconciliação idempotente:** reprocessar a mesma resposta não altera contagens (upsert por recibo).

## 11. Estratégia multi-tenant

- Todo build/fila/envio é **escopado por `tenant`** (herda `tenant_scope`/`get_mantenedora_scope`
  já usado no router). Coleções carregam `tenant`; filtros sempre incluem tenant (fail-closed).
- **Isolamento de fila:** worker reserva itens **por tenant**; um tenant não vê/afeta outro
  (validado no padrão da Sprint 001.1 — correlation_ids e eventos por tenant, sem vazamento).
- **Configuração por tenant:** `mec_integration` (api_key/ambiente) já é por tenant; o scheduler
  respeita a config e as flags de cada tenant.
- **Feature flags por (tenant, environment):** ativação gradual tenant a tenant.
- **Concorrência justa:** limite de envio por tenant evita que um tenant grande monopolize o worker.

## 12. Estratégia de testes

- **Unitários (sem IO):** `FrequencyMapper` (SIGESC→DTO), `FrequencyValidators` (prontidão),
  idempotency_key determinística, consolidação (delegada ao helper SSoT já testado).
- **Fila/worker (Mongo real de teste):** reserva atômica (2 workers não pegam o mesmo item),
  lease expira→reprocessa, idempotência impede duplo aceite, backpressure.
- **Envio com `CmdeClient` mockado** (padrão já usado em `test_mig_cmde.py::_FakeClient`):
  sucesso, rejeição parcial, 5xx+retry→sucesso, erro definitivo, resposta parcial.
- **Auditoria/métricas:** 1 evento por operação com correlation_id do batch; `records_sent/
  accepted/rejected` conferem; sem duplicação nem perda.
- **Multi-tenant/carga:** 3 tenants concorrentes, itens isolados, correlation_ids únicos por lote.
- **Paridade/regressão:** endpoints existentes (`/mec/config|elegibilidades|metrics|audit|flags`)
  **inalterados** (contratos preservados) — rodar `test_mig_cmde.py` completo (15/15) + novos.
- **E2E preview:** build dry-run → ready → run manual (contra CMDE de **homologação**) → recibos →
  reconciliação → dashboard. **Nunca** contra produção MEC sem autorização.

## 13. Estratégia de implantação gradual

1. **Merge desligado:** tudo atrás de flags OFF em produção (`cmde.frequency.*`). Zero efeito.
2. **Homologação MEC:** exercitar o fluxo completo contra o ambiente de HOMOLOGAÇÃO do CMDE
   (nunca produção) com 1 tenant piloto e 1 competência fechada pequena (1 escola/turma).
3. **Dry-run em produção:** builder em produção **sem enviar** (só preview/validação de prontidão).
4. **Piloto controlado:** ligar `scheduler_enabled` para 1 tenant + 1 escola; observar recibos,
   rejeições e métricas por um período; rollback = desligar flag (sem reverter dados).
5. **Rollout por tenant:** expandir tenant a tenant conforme aprovação; teto de lote/concorrência
   ajustável por flag.
6. **Gate humano final:** só liberar envio amplo após homologação assistida + aprovação do owner
   (mesmo rigor das transferências institucionais).

---

## Riscos e mitigação
| Risco | Mitigação |
|---|---|
| Contrato CMDE de frequência ainda não confirmado | Bloquear implementação até termos endpoint/payload/limites oficiais (§0) |
| Super-reporte de frequência (regra ≥50%/dia local vs. expectativa MEC) | Confirmar unidade de apuração antes do piloto; manter dado auditável |
| Duplicidade de envio | Idempotency key unique + verificação pré-envio + `Idempotency-Key` header |
| Perda de item por crash de worker | Lease + visibility timeout + reprocessamento idempotente |
| Crescimento de `mig_audit_events`/filas | P1: política de arquivamento (já documentada; endereçar antes do rollout amplo) |
| Envio acidental de mês em curso | Só envia competência fechada; scheduler OFF por padrão |

## Entregáveis desta etapa (planejamento)
- [x] Este plano arquitetural (`SPRINT_002_PLANO_ARQUITETURAL_CMDE.md`).
- [ ] **Aprovação formal do owner** + confirmação dos bloqueadores externos (§0).
- [ ] Só então: cronograma de implementação em sub-sprints (002.a Builder/DTOs → 002.b Fila/Worker
      → 002.c Scheduler/Flags → 002.d Reconciliação/Rejeições → 002.e UI/Dashboard → 002.f Homolog).

> **A implementação da Sprint 002 permanece BLOQUEADA até a aprovação deste plano.**
