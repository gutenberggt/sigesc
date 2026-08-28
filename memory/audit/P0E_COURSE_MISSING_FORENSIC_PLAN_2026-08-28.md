# P0-E — COURSE_MISSING — Plano forense READ-ONLY

Data: 2026-08-28

## Contexto

O P0 de identidade docente foi encerrado com `ALREADY_CANONICAL=39`, `READY_SAFE=0`, `PROPOSALS=0` e `LEGACY_MIGRATION_DRIFT=0`.

Permanece, como trilha independente, o sinal histórico `COURSE_MISSING=2` identificado pela auditoria global P0. Esse contador representa **referências persistentes** a `courses.id` inexistente; não implica necessariamente dois IDs distintos.

## Objetivo desta etapa

Identificar, sem mutação:

- o(s) `missing_course_id`;
- quantidade de referências por ID ausente;
- coleção/campo/documento que mantém cada referência;
- escola, turma, tenant e ano associados quando resolvíveis;
- origem histórica explícita em `audit_logs`;
- proveniência de consolidação antiga (`removed_id -> kept_id`) quando existir;
- snapshot histórico do componente quando o próprio audit log o preservar;
- candidatos atuais apenas quando houver identidade exata `(mantenedora_id, name, nivel_ensino)` sustentada por snapshot histórico.

## SSoT

O auditor `backend/scripts/audit_course_missing_p0e.py` consome exclusivamente `COURSE_REFERENCE_SPECS` de `backend/services/course_reference_integrity.py` como registry das referências persistentes a `courses.id`.

## Invariantes

- READ-ONLY;
- sem `--apply`;
- sem criação de componente;
- sem remapeamento de referência;
- sem exclusão;
- sem inferência por nome isolado;
- candidato de merge/identidade é somente evidência forense;
- qualquer futura escrita em produção exigirá etapa própria, manifesto, backup/rollback e autorização humana explícita.

## Saída esperada em produção

JSON versionado com:

- `course_references_audited`;
- `course_missing_references`;
- `distinct_missing_course_ids`;
- `origin_state_counts`;
- `cases[]` detalhados;
- `manifest_sha256`;
- `database_mutation=false`.

A expectativa histórica é `course_missing_references=2`, mas isso será validado novamente em produção e não é hardcoded no auditor.
