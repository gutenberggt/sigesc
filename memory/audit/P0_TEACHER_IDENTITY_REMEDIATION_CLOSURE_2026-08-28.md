# Encerramento formal — P0 de identidade docente

Data: 2026-08-28
Status final: **CONCLUÍDO / HOMOLOGADO EM PRODUÇÃO**

## 1. Objetivo

Encerrar formalmente a trilha P0 relacionada à perda/inconsistência de associação entre professores e componentes curriculares, preservando a cadeia forense, a separação semântica entre vínculos operacionais e artefatos de migração e o registro da remediação efetivamente aplicada em produção.

Este documento não autoriza novas mutações. Ele registra o que já foi validado e executado mediante autorização humana explícita.

## 2. Escopo efetivamente remediado

A única mutação realizada em produção foi:

- coleção: `staff`;
- campo: `staff.user_id`;
- quantidade: **6 registros**;
- operação: backfill de identidade canônica `staff.id -> users.id`;
- mecanismo: P0-D2 selado delegando ao executor P0-D1;
- proteção: CAS por `staff.id + mantenedora_id + estado anterior exato de user_id`;
- backup selado obrigatório;
- compensação em falha parcial;
- rollback disponível e não utilizado.

Ficaram explicitamente fora do escopo e não foram alterados:

- `teacher_class_assignments`;
- `teacher_assignments`;
- `teacher_allocations`;
- notas;
- frequência;
- conteúdos;
- AEE;
- artefatos `legacy_migration`.

## 3. Cadeia de evidência

### 3.1 P0-B — auditoria global inicial

Evidência-fonte SHA-256:

`519f078008fae82dc1277975fcf7de141a9231f391da9d1d47666db9e5f781be`

A auditoria inicial revelou mistura semântica entre identidades operacionais e artefatos históricos de migração.

### 3.2 P0-C — separação semântica final

O Semantic V3 formalizou quatro classes:

- `OPERATIONAL_DVD`;
- `LEGACY_MIGRATION_SYNTHETIC`;
- `LEGACY_MIGRATION_SYNTHETIC_UNASSIGNED`;
- `LEGACY_MIGRATION_DRIFT`.

Estado de referência validado antes da remediação:

- `LEGACY_MIGRATION_SYNTHETIC = 1085`;
- `LEGACY_MIGRATION_SYNTHETIC_UNASSIGNED = 97`;
- `LEGACY_MIGRATION_DRIFT = 0`;
- `OPERATIONAL_DVD = 275`;
- `ALREADY_CANONICAL = 33`;
- `READY_SAFE = 6`;
- `USER_NOT_FOUND = 0`;
- `PROPOSALS = 6`.

Manifesto canônico aprovado:

`68165e38d51e58071bd0d9b8d91114872b97841f987e8b630b9b6208b77bda9a`

Método de evidência dos 6 casos:

`EXACT_PAIR_PLUS_EMAIL`

### 3.3 P0-D1 — dry-run e snapshot

O P0-D1 foi executado em produção sem mutação e retornou:

- `mode = DRY_RUN`;
- `status = PASS`;
- `database_mutation = false`;
- `live_state = READY`;
- `ready_count = 6`;
- manifesto vivo idêntico ao aprovado.

Backup bundle selado:

`fac42381eb1d702002334be1e25d06ade594bf6376125a5008d09b995c7cc100`

Hashes físicos registrados no dry-run:

- `backup-metadata.json`: `d04c532d3a27c7bfa729aa04f46e43056d0d72ceb3e8f987f929a8e573f8eeeb`;
- `staff_before.json`: `62a87da7a701652a750c89aa71811f16103636fd3152c47dc85e08be2aae543a`;
- `manifest.json`: `d9fc8cd1191d37ba81d6967d3ed2a25a860342e44bd57e15b3911c746d16c1ba`;
- `BACKUP-SEAL.json`: `9fa9e7c87ecc394aa1ff58935f0f45accdebd0e3b95cd458096d137ee046ddc9`.

### 3.4 P0-D2 — wrapper selado

O P0-D2 foi integrado em `main` pelo merge commit:

`0132407a33d5c10981094f2f485150aa1017afcd`

O deploy de produção foi confirmado nesse mesmo commit.

Hashes físicos dos executores no container de produção:

- P0-D1: `ac4eb06d679b2b9d11779097e17683f59fb0edc42d2171fa90cbe2282a31d622`;
- P0-D2: `1b59315c2c73d302373a52fd6fb2bcc2967c911111874cf9f8e0f3d361b38326`.

O `VERIFY_ONLY` imediatamente anterior ao apply retornou:

- `status = PASS`;
- `database_mutation = false`;
- `live_state = READY`;
- `ready_count = 6`;
- manifesto vivo igual ao aprovado;
- backup bundle igual ao selado.

## 4. Autorização humana para escrita

A execução do `P0-D2 APPLY` foi realizada somente após autorização humana explícita para:

- exatamente 6 `staff.user_id`;
- exclusivamente o backup bundle `fac42381eb1d702002334be1e25d06ade594bf6376125a5008d09b995c7cc100`.

Nenhuma autorização de merge anterior foi tratada como autorização para mutação de dados.

## 5. Resultado do APPLY em produção

Resultado operacional:

- `mode = APPLY`;
- `status = PASS`;
- `database_mutation = true`;
- `modified_count = 6`;
- `state_before = READY`;
- `state_after = ALREADY_APPLIED`;
- verificação direta: `DIRECT_STAFF_USER_ID_VERIFIED = 6`.

SHA-256 físico do recibo de APPLY:

`f30424f9d6e05e68e96ffbf70f5e6c18e4c64e0265a3c70e93b924c3208d7b19`

Não houve falha parcial, compensação nem rollback.

## 6. Pós-check P0-D2

O `VERIFY_ONLY` executado após a mutação retornou:

- `status = PASS`;
- `database_mutation = false`;
- `live_state = ALREADY_APPLIED`;
- backup selado íntegro;
- manifesto original preservado como referência histórica.

## 7. Pós-check Semantic V3 final

O novo Semantic V3, executado após o backfill, retornou:

- `status = PASS`;
- `remediation_gate = PASS`;
- `LEGACY_MIGRATION_SYNTHETIC = 1085`;
- `LEGACY_MIGRATION_SYNTHETIC_UNASSIGNED = 97`;
- `LEGACY_MIGRATION_DRIFT = 0`;
- `OPERATIONAL_DVD = 275`;
- `ALREADY_CANONICAL = 39`;
- `READY_SAFE = 0`;
- `PROPOSALS = 0`;
- `EXACT_PAIR_UNANIMOUS = 39`;
- blockers = 0.

Manifesto canônico pós-apply:

`058ad69b466159fb9c197c5a0b3821970c5b1cd8a027a16009fd867e2e8a8407`

Conclusão: os 6 casos anteriormente `READY_SAFE` foram absorvidos pelo estado canônico, sem introdução de drift e sem alterar a população semântica de artefatos históricos/operacionais.

## 8. Estado final homologado

O P0 de identidade docente está encerrado com as seguintes invariantes confirmadas:

1. os 39 professores operacionais identificados pelo preflight estão canônicos;
2. não restam propostas de backfill `staff.user_id` nessa trilha;
3. `LEGACY_MIGRATION_DRIFT = 0`;
4. os 1085 artefatos sintéticos com professor permanecem preservados;
5. os 97 artefatos sintéticos sem professor permanecem preservados e corretamente classificados;
6. nenhuma coleção de vínculo pedagógico foi reescrita para acomodar a identidade;
7. o backup selado deve ser preservado para eventual rollback controlado;
8. o APPLY não deve ser repetido.

## 9. Passivos deliberadamente não incluídos neste P0

Permanecem como trilhas independentes de qualidade/integridade:

- `COURSE_MISSING = 2`;
- `DUPLICATE_COURSE_IDENTITY = 3`;
- `DUPLICATE_BINDING_LEGACY = 1`.

Esses itens não devem ser tratados como continuação automática do backfill de identidade docente. Cada um exige diagnóstico próprio, plano, dry-run e gate de produção correspondente.

## 10. Decisão de encerramento

**P0-C / P0-D — IDENTIDADE DOCENTE: ENCERRADO E HOMOLOGADO EM PRODUÇÃO.**

Qualquer nova alteração relacionada a identidade docente deve partir deste estado como nova baseline e não reutilizar o manifesto pré-apply como se ainda representasse o estado vivo atual.
