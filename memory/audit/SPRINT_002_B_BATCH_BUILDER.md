# SPRINT 002.b — Batch Builder de Frequência CMDE · RELATÓRIO

**Status:** ✅ CONCLUÍDA (aguardando aprovação para iniciar a 002.c).
**Escopo entregue:** Builder que transforma o SSoT de frequência (`attendance`) em lotes CMDE,
com validação de prontidão, idempotência, dry-run, relatório de inconsistências e preview no
Dashboard Técnico. **Somente leitura sobre `attendance`; nenhuma regra nova de frequência;
nenhum envio ao MEC; nenhum Queue Manager/Worker/Scheduler.**

---

## Regras cumpridas
- **Read-only sobre `attendance`** (e apoio students/schools/medical_certificates). Validado por
  teste que confirma `attendance` inalterado após o build.
- **Sem regra nova de frequência:** faltas válidas vêm de
  `services.attendance_utils.compute_monthly_valid_absences` (consolidação por dia ≥50%, SSoT).
  `dias_letivos` = dias com aula registrada do aluno na competência (representação derivada);
  `frequencia_percentual` = `(dias_letivos - faltas)/dias_letivos*100` (derivado, não persiste no SSoT).
- **Sem alterar dados acadêmicos**, sem envio ao MEC, sem fila real.

## Entregas (arquivos)
- **`mig/cmde/batch_builder.py`** — `FrequencyBatchBuilder.build(request, context)`:
  lê `attendance` por (tenant, competência AAAA-MM, escopo school/class), consolida, mapeia para
  itens, valida prontidão, gera `idempotency_key`, monta preview e (fora do dry-run) persiste.
- **`mig/cmde/frequency_validators.py`** — prontidão do item (INEP escola + identificador CPF/NIS)
  via `ValidationEngine`.
- **`mig/cmde/frequency_repository.py`** — escrita de lotes/itens (insert do batch + **upsert
  idempotente do item por `idempotency_key`**). Sem reserva/lease (isso é 002.c).
- **`mig/cmde/service.py`** — `build_frequency_batch(...)` delega ao builder.
- **`routers/mec_integration.py`** — endpoint fino `POST /api/mec/frequency/preview`
  (guard super_admin + CSRF; `dry_run` padrão True; erros MigError → HTTP).
- **Frontend** `pages/MECIntegration.js` + `services/api.js` (`mecAPI.previewFrequency`):
  painel **"Preview de Lotes de Frequência"** na aba Operação Técnica.

## Preview no Dashboard Técnico (visão operacional)
Selo **DRY-RUN (não envia)**. Campo de competência (mês) + "Gerar preview". Exibe cards:
**Competência · Alunos analisados · Prontos · Pendências · Lotes previstos · Modo (Dry-run)**,
o estado da competência (encerrada/em curso), o `correlation_id`, e o **Relatório de
inconsistências** (aluno × dados faltantes). Evidência por screenshot (competência 2020-05 → 0,
dry-run) confirmada.

## Contrato do preview (`POST /api/mec/frequency/preview`)
Request: `{ competencia:"AAAA-MM", school_id?, class_id?, dry_run=true }`.
Response: `{ correlation_id, competencia, tenant, environment, dry_run, competencia_fechada,
batch_size, analyzed, ready_count, pending_count, lotes_previstos, pendencias[], items_preview[],
persisted, batch_ids[] }`.

## Idempotência
`idempotency_key = sha1(tenant|cmde|frequency|competencia|student_id|school_inep|payload_version)`.
Persistência via `$setOnInsert` (upsert) → **re-build NÃO duplica** itens. Correção de dado →
nova `payload_version` gera nova chave (reenvio controlado — a partir da 002.d).

## Validações (testes automatizados — 7 blocos PASS · `tests/test_mig_cmde_002b.py`)
- Consolidação SSoT: A1 com 3 dias/1 falta → 66,7% (bate com a regra ≥50%/dia).
- Prontidão: aluno sem CPF/NIS → pendência "Identificador (CPF/NIS)".
- **Idempotência:** dry-run não persiste; build real cria 1 item; re-build NÃO duplica.
- **Isolamento multi-tenant:** tenant A não enxerga dados do tenant B (e vice-versa).
- **Dados incompletos:** listados no relatório de inconsistências, fora dos "prontos".
- **SSoT imutável:** `attendance` permanece byte-a-byte igual após o build.
- **Competência em curso:** só preview; persistência real bloqueada (`MigConfigError`).

**E2E (preview real):** `POST /api/mec/frequency/preview` competência 2020-05 → 200
(`analyzed=0` sem dados no mês); sem competência → 400; sem auth → 401.
**Regressão:** `test_mig_cmde.py` 15/15 e `test_mig_cmde_002a.py` 12/12 seguem verdes.

## Coleções tocadas (apenas quando `dry_run=false`)
`mig_cmde_frequency_batches` (batch `ready`) e `mig_cmde_send_queue` (itens `pending`). Nenhuma
coleção pedagógica é escrita em nenhum caso.

## Próximo passo (após aprovação)
**002.c — Queue Manager:** implementação real da fila sobre MongoDB (reserva atômica/lease,
requeue de expirados, backpressure por tenant, índices), consumindo os itens já persistidos aqui.
**Aguardando "sim" do owner.**

## Bloqueadores externos (mantidos)
1. Contrato oficial da API CMDE de frequência. 2. Unidade de apuração aceita pelo MEC.
3. Limiares 60%/75% — apenas para relatório.
