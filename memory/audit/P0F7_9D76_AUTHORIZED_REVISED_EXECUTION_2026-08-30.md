# P0-F7.9D7.6 — Materialização do executor revisado autorizado

Data: 2026-08-30

## Autorização humana específica

O responsável autorizou explicitamente a materialização do executor revisado e a execução em produção vinculada exatamente a:

- manifesto D7.5: `89e0f72d97f7cfa8b2d4b5dd7b5d35a01376a813d69d46f5bce7fa9c11440fcc`;
- plano revisado D7.3.1: `b6cfcfd3fec964fe58ebdcc7aea6e9fe1953207d7178da35b7e1bd4dea8c39fb`;
- preflight/CAS dry-run real D7.4: `b835f5393e035dee0703f1aa0ae0dd52c779b81d5f73b8c05d0adff3fbcedc9e`;
- exatamente 23 operações: 21 `REMAP_COURSE`, 1 `RETIRE_DUPLICATE_ASSIGNMENT` e 1 `CONSOLIDATE_SURVIVOR`;
- estratégia obrigatória `CAS_WITH_COMPENSATING_ROLLBACK_REQUIRED`;
- zero hard delete;
- rollback compensatório reverso em caso de qualquer falha.

A autorização antiga da D7 original permanece inválida e não reutilizável.

## Separação de responsabilidades

A D7.6 introduz duas superfícies distintas:

1. **builder local**: valida a cadeia selada e materializa o JS escritor mais metadados com SHA-256;
2. **executor JS**: somente esse artefato, quando deliberadamente enviado ao `mongosh`, pode escrever em `teacher_assignments`.

O wrapper PowerShell local nunca abre SSH, nunca executa `mongosh`, nunca acessa produção e nunca dispara o JS remotamente.

## Contrato do writer

O executor:

- aceita somente o manifesto exato autorizado;
- embute marcador de autorização específico;
- executa um gate CAS global das 23 fontes antes do primeiro write;
- revalida CAS imediatamente antes de cada write;
- verifica colisão ativa imediatamente antes de cada alteração que resulte em vínculo ativo;
- usa apenas `teacher_assignments.updateOne(..., {$set: ...})`;
- não contém `deleteOne`, `deleteMany`, `insertOne`, `replaceOne`, `bulkWrite` ou hard delete;
- executa na ordem `SEALED_OPERATION_INDEX_ASC`;
- mantém `RETIRE_DUPLICATE_ASSIGNMENT` antes de `CONSOLIDATE_SURVIVOR`;
- verifica pós-condição após cada write;
- verifica unicidade final dos vínculos ativos;
- valida a pós-condição do par: duplicado `inativo`, survivor ativo, curso canônico e 2h semanais.

## Rollback compensatório

A topologia real não oferece transação multi-documento. Assim, qualquer falha após um ou mais writes dispara rollback em ordem reversa.

Cada rollback:

- usa CAS contra o estado pós-write esperado;
- aplica exclusivamente os `rollback_set_fields` selados;
- valida a pós-condição de restauração imediatamente;
- registra falha de rollback sem tentar adivinhar ou sobrescrever drift concorrente.

Classificações possíveis do recibo:

- `APPLIED`: 23 forward writes e zero rollback; remediação aplicada;
- `SAFE_ROLLBACK`: todos os writes já aplicados foram revertidos integralmente; remediação não aplicada;
- `ROLLBACK_INCOMPLETE`: estado inseguro; exige intervenção manual e nenhuma nova execução automática.

## Cadeia criptográfica

O builder gera:

- `EXECUTOR_SHA256`: hash do JS materializado;
- `METADATA_SHA256`: hash canônico dos metadados.

Antes da execução, o operador deve conferir novamente o SHA do arquivo JS contra `EXECUTOR_SHA256`.

## Validação do recibo

`backend/scripts/validate_p0f7_9d76_execution_receipt_offline.py` valida offline:

- manifesto D7.5;
- metadados D7.6;
- SHA real do executor;
- recibo emitido pelo `mongosh`;
- contagens de forward/rollback;
- cadeia das 23 operações em caso de `APPLIED`;
- segurança integral em caso de `SAFE_ROLLBACK`.

O validador não possui cliente de banco ou rede e não escreve em produção.

## Arquivos

- builder: `backend/scripts/build_p0f7_9d76_authorized_revised_executor_js.py`;
- validador: `backend/scripts/validate_p0f7_9d76_execution_receipt_offline.py`;
- wrapper: `scripts/p0f7_9d76_authorized_revised_execution_local.ps1`;
- testes: `backend/tests/test_p0f7_9d76_authorized_revised_executor.py`;
- guard: `.github/workflows/p0f7-9d76-authorized-revised-executor-guard.yml`.

## Segurança operacional

A integração do código na `main` não executa produção. A futura execução operacional deve usar exclusivamente o JS cujo SHA tenha sido materializado localmente e conferido antes de ser enviado ao `mongosh`.
