# P0 GLOBAL — Integridade Professor ⇄ Turma ⇄ Componente

**Abertura:** 2026-08-27  
**Severidade:** P0 — integridade referencial / risco pedagógico  
**Escopo:** frequência, notas/conceitos, registro de conteúdos, horários e vínculos docentes  
**Modo inicial:** contenção + auditoria READ-ONLY  
**AEE:** fora do escopo; nenhuma alteração

## 1. Incidente

Foram observados professores aparentemente desvinculados de componentes curriculares de forma silenciosa ou após atualizações. A investigação no código confirmou duas classes estruturais de risco:

1. múltiplas representações mutáveis de `Professor ⇄ Turma ⇄ Componente` (`teacher_assignments`, `teacher_allocations`, `teacher_class_assignments` e `class_schedules`);
2. exclusão/consolidação física de `courses.id` sem migração atômica de todas as referências dependentes.

Há evidência histórica de gaps reais entre alocação legada e DVD e de IDs divergentes de componentes mascarados por fallback por nome na UI.

## 2. Invariantes do P0

1. Nenhuma correção por professor específico.
2. Nenhum remapeamento por nome de componente.
3. Nenhum backfill automático enquanto a auditoria global não estiver preservada.
4. Nenhuma mutação do auditor P0.
5. Nenhum hard delete de componente referenciado.
6. Nenhuma consolidação física de componente pela rotina legada.
7. Nenhum hard delete de `teacher_assignments` durante a contenção.
8. Tenant permanece fail-closed; duplicidade de componente nunca é avaliada atravessando mantenedoras.
9. Casos ambíguos ficam em `needs_review`/classificação de risco, nunca são inferidos.
10. `main` só recebe a mudança após CI e autorização humana explícita.

## 3. P0-A — Contenção implementada nesta branch

### 3.1 `DELETE /courses/{course_id}`

A exclusão física passa a consultar um registro central de referências de `courses.id`.

Coleções protegidas inicialmente:

- `teacher_assignments.course_id`;
- `teacher_allocations.course_id`;
- `teacher_class_assignments.component_id`;
- `class_schedules.schedule_slots[].course_id`;
- `grades.course_id`;
- `attendance.course_id`;
- `content_entries.component_id`;
- `learning_objects.course_id`;
- `student_dependencies.course_id`.

Se qualquer contagem for maior que zero, a operação falha com `409 COURSE_IN_USE_P0` e informa as coleções bloqueadoras.

### 3.2 `/maintenance/consolidate-courses`

- `dry_run=true`: permanece disponível apenas como diagnóstico;
- `dry_run=false`: retorna `409 COURSE_CONSOLIDATION_DISABLED_P0`;
- nenhuma exclusão ou atualização de `courses` é executada pela rotina enquanto o P0 estiver ativo.

A listagem de duplicados agora é tenant-scoped e agrupa por `mantenedora_id + name + nivel_ensino`.

### 3.3 Hard delete de `teacher_assignments`

O endpoint legado `DELETE /teacher-assignments/{assignment_id}` retorna `409 TEACHER_ASSIGNMENT_HARD_DELETE_DISABLED_P0`.

O cleanup de órfãos também preserva `teacher_assignments`, registrando quantos documentos foram protegidos.

## 4. P0-B — Auditor forense global READ-ONLY

Novo script:

```text
backend/scripts/audit_teacher_binding_integrity_p0.py
```

O script possui guard estático contra chamadas Mongo mutadoras e cruza a rede inteira, sem exigir ID de professor.

### 4.1 Fontes comparadas

Vínculo docente:

- `teacher_assignments` → fonte legada;
- `teacher_allocations` → fonte operacional concorrente;
- `teacher_class_assignments` → vínculo temporal/DVD.

Referências curriculares:

- vínculos acima;
- horários;
- frequência;
- notas/conceitos;
- conteúdo canônico;
- conteúdo legado;
- dependências de estudos.

Identidade:

- `users.id`;
- `staff.user_id` como primeira evidência;
- e-mail exato case-insensitive somente como fallback legado quando único.

### 4.2 Estados de vínculo

O auditor classifica cada chave lógica `staff_id + class_id + course_id` em:

- `ALL_THREE_OK`;
- `LEGACY_AND_ALLOCATION_MISSING_DVD`;
- `LEGACY_AND_DVD_MISSING_ALLOCATION`;
- `ALLOCATION_AND_DVD_MISSING_LEGACY`;
- `LEGACY_ONLY`;
- `ALLOCATION_ONLY`;
- `DVD_ONLY`.

Também sinaliza duplicidades dentro de cada fonte.

### 4.3 Integridade do componente

Classificações iniciais:

- `COURSE_MISSING`;
- `COURSE_MISSING_WITH_MERGE_PROVENANCE`;
- `COURSE_TENANT_MISMATCH`;
- `DUPLICATE_COURSE_IDENTITY`.

O auditor lê `audit_logs` antigos da consolidação e, quando existe evidência explícita, informa:

```text
removed_course_id → canonical_candidate_id
```

Isso é apenas evidência. O P0-B não atualiza nenhuma referência.

### 4.4 Identidade docente

Classificações:

- `USER_ID`;
- `EMAIL_FALLBACK`;
- `AMBIGUOUS_USER_ID`;
- `AMBIGUOUS_EMAIL`;
- `UNRESOLVED`;
- `DVD_TEACHER_IDENTITY_UNRESOLVED`.

Nenhuma correspondência é feita por nome do professor.

## 5. Execução prevista em produção

Primeiro preservar a evidência global, sem tenant específico:

```bash
cd /app/backend
python scripts/audit_teacher_binding_integrity_p0.py \
  --academic-year 2026 \
  --reference-date 2026-08-27 \
  --json /app/memory/audit/p0_teacher_binding_integrity_2026-08-27.json
```

Opcionalmente, repetir por mantenedora para validação cruzada:

```bash
python scripts/audit_teacher_binding_integrity_p0.py \
  --academic-year 2026 \
  --reference-date 2026-08-27 \
  --mantenedora-id <ID> \
  --json /app/memory/audit/p0_teacher_binding_integrity_<ID>_2026-08-27.json
```

## 6. Gate para P0-C — Remediação

Nenhuma escrita de correção será preparada antes de termos:

1. contagem total de referências de componente órfãs;
2. mapa de gaps por fonte de vínculo;
3. casos de identidade não resolvida/ambígua;
4. duplicidades de componentes por tenant;
5. mapa determinístico proveniente de auditoria para IDs removidos em consolidações anteriores;
6. separação entre reparo automático seguro e `needs_review`;
7. manifesto/hash do conjunto de mudanças proposto;
8. dry-run reproduzível;
9. pós-check que exija zero regressões;
10. rollback definido antes do apply.

## 7. Testes/CI

Foram adicionados guards para:

- auditor P0 permanecer READ-ONLY;
- registro central cobrir as superfícies pedagógicas críticas;
- extração de `course_id` aninhado em horários;
- matriz explícita de drift entre as três fontes;
- resolução users↔staff fail-closed;
- consolidação legada não conter mutações em `courses`;
- hard delete de `teacher_assignments` permanecer bloqueado;
- exclusão de componente exigir verificação global de referências.

Os testes passam a integrar o job existente **Backend - Diário por Vínculo guards**.

## 8. Próxima etapa

Após o PR ficar verde e ser autorizado para merge:

1. publicar a contenção;
2. executar o auditor global em produção;
3. preservar o JSON bruto;
4. analisar os buckets reais;
5. desenhar P0-C com remediação determinística, sem tratamento individual por professor.
