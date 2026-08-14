# Fase B.6 — Dry-run / Preview operacional Student + Enrollment

Data-base: 2026-08-14  
Status: implementação em branch, **sem envio real ao MEC**.

## 1. Objetivo

Fechar a sequência B.1–B.6 com um ponto operacional read-only capaz de mostrar, antes de qualquer provider real:

- quais matrículas ativas selecionadas estão prontas para um tipo de lote;
- quais estão bloqueadas;
- os motivos de bloqueio por campo/código;
- os IDs externos SGP já conciliados pela B.5;
- o registro de payload que seria produzido para cada item pronto;
- o payload da página somente quando todos os registros daquela página estiverem prontos.

A B.6 **não envia**, não enfileira, não cria lote, não chama HTTP e não persiste resultado de preview.

## 2. Contrato oficial de referência

Contrato CMDEB v2.0.0 verificado em 2026-08-14.

Alvo inicial já implementado nas B.3/B.4:

```text
POST /api/v2/estudantes/sem-turma/cadastro/lote
```

Envelope:

```json
{
  "estudantes": [
    { "...": "..." }
  ]
}
```

O processamento oficial é assíncrono. A B.6 para deliberadamente antes de autenticação/provider/HTTP.

## 3. Endpoint interno SIGESC

```text
POST /mec/students/preview
```

Proteção: mesmo guard administrativo do módulo MEC (`super_admin`).

Exemplo de request:

```json
{
  "dry_run": true,
  "lot_type": "student_without_class_create",
  "tenant_id": "<mantenedora>",
  "school_id": null,
  "class_id": null,
  "student_id": null,
  "enrollment_id": null,
  "page": 1,
  "page_size": 100
}
```

`dry_run` é `Literal[true]`. Não existe modo `false` neste endpoint.

## 4. Escopo de seleção

A seleção parte de `enrollments` e exige:

- `mantenedora_id` explícita;
- matrícula ativa (`active`/legado `Ativo`);
- filtros opcionais por escola, turma, estudante e matrícula;
- paginação de 1 a 200 registros por resposta.

Se o usuário autenticado já estiver escopado a uma mantenedora, o body não pode sobrescrever esse tenant. Em contexto cross-tenant, `tenant_id` é obrigatório.

Não há fallback cross-tenant implícito.

## 5. Pipeline B.1 → B.6

Para cada matrícula selecionada:

1. lê `Enrollment`, `Student`, `School` e, quando existir, `Class`;
2. constrói `CanonicalStudentEnrollmentDTO` pela B.1;
3. resolve `id_sgp_estudante`/`id_sgp_matricula` somente pela coleção B.5 `mig_sgp_external_ids`;
4. hidrata os slots externos do DTO canônico, substituindo inclusive eventual valor legado por `None` quando não houver vínculo B.5;
5. executa o validador B.4 para o `lot_type` solicitado;
6. aplica guardas operacionais B.6 de aplicabilidade do tipo de lote;
7. somente se o registro continuar pronto, executa o mapper B.3 e produz `candidate_payload_record`;
8. agrega bloqueios/avisos sem chamar provider.

## 6. B.5 como SSoT de identidade externa

O preview **não usa** `Enrollment.sgp_enrollment_id` legado como fonte de verdade.

A fonte canônica operacional é:

```text
mig_sgp_external_ids
```

Resposta por registro:

```json
{
  "external_ids": {
    "source": "mig_sgp_external_ids",
    "student_external_id": "123456",
    "enrollment_external_id": "987654"
  }
}
```

No cadastro inicial sem turma, os IDs externos não são serializados no payload quando o contrato daquele lote não os utiliza.

### 6.1 Guarda contra recadastro de identidade conciliada

A B.6 adiciona uma guarda operacional além da prontidão estrutural B.4:

```text
external_identity_already_exists
```

Para lotes de **cadastro novo**, se a B.5 já conhece `id_sgp_estudante` ou `id_sgp_matricula`, o registro não pode ser classificado como pronto para novo cadastro.

Exemplo:

```json
{
  "ready": false,
  "issues": [
    {
      "code": "external_identity_already_exists",
      "field": "external_ids",
      "severity": "error"
    }
  ],
  "candidate_payload_record": null
}
```

A existência do ID externo não é interpretada automaticamente como autorização para editar, enturmar ou movimentar. Esses fluxos permanecem bloqueados até seus respectivos `lot_type` + readiness + serializer serem implementados.

Essa guarda evita que um Student/Enrollment já conciliado seja sugerido como candidato a recadastro apenas porque seus dados cadastrais passam nas validações B.4.

## 7. Fail-closed de página mista

Regra obrigatória:

```text
99 prontos + 1 bloqueado != lote parcial pronto
```

Cada registro pronto pode exibir seu `candidate_payload_record`, porém:

```json
{
  "page_ready": false,
  "page_payload": null
}
```

O payload de lote é montado somente se **todos** os registros da página forem prontos.

Isso impede a omissão silenciosa de registros bloqueados.

## 8. Registros inconsistentes não desaparecem

Se a matrícula não tiver `student_id`, `id`, ou referenciar Student inexistente no tenant, o item continua na resposta como bloqueado:

```text
canonical_projection_failed
```

O preview não exclui silenciosamente inconsistências de integridade referencial.

## 9. Estrutura de resposta

Campos principais:

```text
mode = dry_run
preview_version
canonical_contract_version
readiness_version
serializer_version
lot_type
endpoint
tenant_id
page / page_size
total_matching / total_pages
page_records
ready_records
blocked_records
warning_records
blocker_counts
warning_counts
page_ready
page_payload
records[]
provider_called = false
write_attempted = false
queue_touched = false
```

Cada `records[]` contém IDs internos técnicos, IDs externos B.5, relatório de prontidão e, quando pronto, o candidato individual de payload.

## 10. Ausência de efeitos colaterais

A implementação B.6 não executa:

- `insert_one`;
- `update_one`;
- `delete_one`;
- `create_index`;
- criação de `mig_audit_events`;
- criação de fila;
- criação de lote;
- geração de idempotency key de envio;
- `CmdeClient`;
- token/API key;
- HTTP externo.

A B.5 é utilizada apenas com `find_one` via `resolve_pair()`.

## 11. Tipos de lote ainda não implementados

A B.4 conhece outros endpoints oficiais. A B.6 aceita o `lot_type`, mas mantém a política fail-closed:

- tipo oficial conhecido sem readiness/serializer próprio → `unsupported_lot_type`;
- tipo desconhecido → `unknown_lot_type`;
- nenhum payload é produzido.

Na B.6 inicial, somente `student_without_class_create` pode chegar a `ready=true` e produzir payload — e apenas quando não houver identidade externa B.5 já conciliada.

## 12. Segurança e minimização

- endpoint restrito a super_admin;
- tenant explícito;
- paginação máxima de 200;
- diagnósticos de bloqueio não copiam valores pessoais;
- PII aparece somente no candidato de payload, pois essa é a finalidade do preview técnico;
- nenhum payload é persistido em log/auditoria pela B.6.

## 13. Critérios de aceite

- B.1–B.5 integradas sem alterar suas invariantes;
- `dry_run=false` rejeitado;
- nenhum provider chamado;
- nenhuma escrita no banco;
- nenhuma fila tocada;
- IDs externos vêm exclusivamente da B.5;
- ID externo legado não substitui a SSoT B.5;
- identidade já conciliada bloqueia lote de cadastro novo;
- registro bloqueado exibe motivo por campo;
- registro pronto exibe candidato de payload;
- página mista nunca gera lote parcial;
- Student ausente é bloqueio visível, não omissão;
- tenant cross-network não é inferido;
- tipos de lote não implementados falham fechados.

## 14. Fora de escopo

- provider oficial CMDE;
- autenticação Bearer/token;
- envio HTTP;
- criação/polling/reconciliação de lote real;
- habilitação de scheduler/worker/queue para Student;
- ativação de feature flag de envio;
- completar tabelas B.2 ainda sem legenda oficial inequívoca;
- migração automática de IDs externos legados;
- UI específica de preview (o endpoint fica pronto para consumo pela Operação Técnica MIG).
