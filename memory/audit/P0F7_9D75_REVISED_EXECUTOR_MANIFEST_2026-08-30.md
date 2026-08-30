# P0-F7.9D7.5 — Selagem do manifesto revisado de execução

Data: 2026-08-30

## Objetivo

Selar uma especificação imutável das 23 operações revisadas após a D7.4 real ter retornado todos os gates claros.

Esta etapa **não cria nem executa writer**. Ela existe para separar:

1. o plano revisado e validado;
2. o manifesto exato que poderá ser autorizado;
3. a futura materialização do executor;
4. a futura execução em produção.

## Entradas imutáveis

Plano revisado D7.3.1:

`b6cfcfd3fec964fe58ebdcc7aea6e9fe1953207d7178da35b7e1bd4dea8c39fb`

Relatório real D7.4:

`b835f5393e035dee0703f1aa0ae0dd52c779b81d5f73b8c05d0adff3fbcedc9e`

A D7.5 falha fechada se qualquer SHA divergir.

## Gates exigidos da D7.4

- `operations = 23`;
- `cas_dry_run_clear = 23`;
- `cas_dry_run_blocked = 0`;
- `curricular_checks_passed = 22`;
- `forward_simulation_clear = true`;
- `pair_postconditions_clear = true`;
- `rollback_simulation_clear = true`;
- `clear_for_executor_sealing = true`;
- `production_write_authorized = false`;
- `executor_authorized = false`;
- `database_mutation = false`;
- `production_writes = false`;
- `remediation_executed = false`.

## Topologia e estratégia

A D7.4 real classificou o ambiente como:

`STANDALONE_OR_TRANSACTION_UNAVAILABLE`

Portanto a estratégia obrigatória continua:

`CAS_WITH_COMPENSATING_ROLLBACK_REQUIRED`

A D7.5 rejeita qualquer drift de topologia/estratégia.

## Operações seladas

O manifesto contém exatamente:

- 21 `REMAP_COURSE`;
- 1 `RETIRE_DUPLICATE_ASSIGNMENT`;
- 1 `CONSOLIDATE_SURVIVOR`.

A ordem final do par é invariável:

`RETIRE_DUPLICATE_ASSIGNMENT -> CONSOLIDATE_SURVIVOR`

Rollback futuro: `REVERSE_OPERATION_ORDER`.

Hard delete permanece proibido.

## Contrato de autorização

O manifesto gerado permanece:

- `executable = false`;
- `writer_implementation_present = false`;
- `executor_materialized = false`;
- `production_write_authorized = false`;
- `executor_authorized = false`.

Uma autorização futura deve citar explicitamente:

1. `manifest_sha256` da D7.5;
2. SHA do plano revisado D7.3.1;
3. SHA do relatório D7.4;
4. estratégia `CAS_WITH_COMPENSATING_ROLLBACK_REQUIRED`;
5. exatamente 23 operações.

A autorização antiga da execução D7 original continua inválida e não reutilizável.

## Implementação

Sealer offline:

`backend/scripts/seal_p0f7_9d75_revised_executor_manifest.py`

Wrapper local:

`scripts/p0f7_9d75_revised_executor_manifest_local.ps1`

Guard CI:

`.github/workflows/p0f7-9d75-revised-executor-manifest-guard.yml`

Regressões:

`backend/tests/test_p0f7_9d75_revised_executor_manifest.py`

## Segurança

- `PRODUCTION_ACCESS=NO`;
- `DATABASE_MUTATION=NO`;
- `PRODUCTION_WRITES=NO`;
- `EXECUTOR_AUTHORIZED=NO`;
- `EXECUTOR_MATERIALIZED=NO`;
- `WRITER_IMPLEMENTATION_PRESENT=NO`;
- `REMEDIATION_EXECUTED=NO`;
- zero dado de estudante;
- zero nome de docente;
- zero credencial;
- zero cliente MongoDB/HTTP/rede;
- zero primitiva de escrita.

## Próximo gate

Somente após a D7.5 real gerar um `MANIFEST_SHA256` válido poderá ser apresentada ao responsável humano a autorização específica de produção.

A futura etapa de materialização do executor deverá consumir exatamente esse manifesto e somente aceitar autorização que cite os SHAs selados. Nenhuma autorização genérica ou antiga será aceita.
