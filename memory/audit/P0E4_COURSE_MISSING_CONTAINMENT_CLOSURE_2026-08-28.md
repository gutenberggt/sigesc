# P0-E4 — Contenção e encerramento do órfão histórico COURSE_MISSING

Data: 2026-08-28

## Escopo

Encerrar o achado `COURSE_MISSING` sem remapeamento especulativo e sem mutação dos documentos históricos existentes.

## Cadeia forense

### P0-E — auditoria global READ-ONLY

- `course_references_audited = 137967`
- `course_missing_references = 2`
- `distinct_missing_course_ids = 1`
- `missing_course_id = c2d05a04-b735-494d-bc7b-53ce34081488`
- `origin_state = NO_COURSE_AUDIT_HISTORY`
- manifesto canônico: `5902d2b4a771b7cfa9362fd07038bcbe1ba5e4cc26b10f9d3dfd382e9fc92932`
- hash físico: `7f396c7a1485a7f252a9a8e2c40fae1d3e89f4383ce30aba78262fb099f4bd66`
- evidência: `/root/sigesc-p0-audits/p0e_course_missing_20260828T033529Z`

Referências sobreviventes:

1. `teacher_assignments.id = e8e00fd0-b09c-4bd1-9812-6d3fc4753d85`
   - turma: `Ed. Infantil Unificada`
   - escola: `E M E I E F 22 de Abril`
2. `learning_objects.id = ef24b1e9-f2ce-4d1d-9ef5-984834faef3b`
   - turma: `Berçario II A`
   - escola: `C M E I Professora Nivalda Maria de Godoy`

### P0-E2 — reconstrução estrutural READ-ONLY

- resultado: identidade não recuperada
- o ID ausente não existe atualmente em `courses`
- evidências do ID ausente somente em `learning_objects`, `teacher_assignments` e no contexto legado do mesmo professor
- sem correspondência operacional inequívoca em DVD, notas ou outros componentes atuais
- evidência: `/root/sigesc-p0-audits/p0e2_identity_20260828T033847Z`
- hash físico: `8df0f375343bd87bd3795b73ce5c61ae066ce2c3f7c9e0d49a10d5756b4dacf3`

### P0-E3 — reconstrução temporal READ-ONLY

- `classification = NO_EXACT_TEMPORAL_IDENTITY`
- `exact_candidate_count = 0`
- `semantic_payload_sha256 = d5018fb7eff7216bd33798f9e40febb2b8b5a57fc057595ad4b7c3dd45da9f45`
- `same_day_records = 5`
- `creation_neighbors_10s = 5`
- `teacher_assignment_batch_120s = 6`
- `DATABASE_WRITES_EXECUTED = NO`
- evidência: `/root/sigesc-p0-audits/p0e3_temporal_20260828T094521Z`

## Decisão final

Classificação forense:

- `IDENTITY_RECOVERED = NO`
- `SAFE_REMAP_CANDIDATE = NO`
- `AUTO_CREATE_COURSE = NO`
- `DELETE_ORPHAN_REFERENCES = NO`
- `FINAL_STATE = UNRESOLVED_FAIL_CLOSED`

Não existe base probatória suficiente para determinar qual componente atual, se algum, corresponde ao UUID ausente. O SIGESC não deve escolher candidato por similaridade curricular, proximidade temporal, mesmo professor ou coexistência na turma.

## Contenção implementada

A contenção é genérica e não codifica o UUID do caso na aplicação.

Em respostas de leitura dos readers legados afetados:

- o `course_id` persistido é preservado integralmente;
- se `courses.id` existir, o comportamento segue normal;
- se `courses.id` não existir:
  - `course_name = "Componente histórico indisponível"`;
  - `course_reference_state = "HISTORICAL_COURSE_MISSING"`;
  - `course_reference_integrity.remap_applied = false`;
  - `course_reference_integrity.automatic_course_creation = false`;
  - `course_reference_integrity.source_preserved = true`.

Readers cobertos nesta etapa:

- `GET /learning-objects`
- `GET /learning-objects/{object_id}`
- `GET /teacher-assignments`

## Invariantes

- nenhuma alteração em `courses`;
- nenhuma alteração em `teacher_assignments`;
- nenhuma alteração em `learning_objects`;
- nenhum remapeamento;
- nenhuma exclusão;
- nenhuma criação automática;
- nenhum writer relaxado;
- nenhum UUID órfão codificado no runtime;
- nenhuma alteração em AEE;
- SSoT de referências a componente permanece em `course_reference_integrity.py` para auditoria estrutural.

## Encerramento

Após deploy e validação READ-ONLY do comportamento de resposta, o sinal `COURSE_MISSING = 2` pode ser encerrado como passivo histórico conhecido e contido, com estado `UNRESOLVED_FAIL_CLOSED`. O dado histórico permanece preservado até que surja evidência externa ou documental suficiente para uma futura decisão humana explícita.
