# P0-F7.9A — Auditoria Forense de Compatibilidade Curricular das Alocações

**Data:** 2026-08-29  
**Modo:** investigação READ-ONLY  
**Escopo inicial:** turma `MULTI 3º E 4º ETAPA`, E M E I E F Bom Jesus, ano 2026  
**Produção:** snapshot mínimo via `mongosh`; análise integral no Windows  
**Mutação:** proibida

## 1. Gatilho

Documento institucional da turma revelou professoras vinculadas simultaneamente a componentes regulares e a campos de experiência característicos da Educação Infantil, embora a turma esteja registrada como EJA — Anos Finais.

A P0-F7.9 de adjudicação de Geografia fica pausada até explicar a extensão e a origem dessa incompatibilidade.

## 2. Achado estático já confirmado no código

O endpoint `POST /teacher-assignments` atualmente valida:

- existência do servidor;
- cargo de professor;
- existência da turma;
- existência do componente;
- duplicidade da mesma combinação professor + turma + componente + ano.

Ele não executa a compatibilidade curricular `turma ⇄ nível ⇄ série/etapa ⇄ componente` antes de persistir o vínculo.

A SSoT de compatibilidade já existe em `backend/utils/curriculum_resolver.py` através de `_curricular_fit`, que classifica diferença explícita de nível como `LEVEL_MISMATCH` (rank 1). Portanto, a regra existe para resolução/leitura, mas não protege hoje a fronteira de escrita de `teacher_assignments`.

O modelo `TeacherAssignmentUpdate` não expõe `class_id` ou `course_id`, logo o endpoint normal de atualização não troca a turma ou o componente de uma alocação existente. Um vínculo incompatível em `teacher_assignments` pode ter sido criado já incompatível, inserido/migrado por outro caminho, ou afetado por processo histórico sobre referências de componente. Esta etapa não presume qual hipótese ocorreu.

Também não existe, no fluxo atual de criação mostrado em `create_teacher_assignment`, registro explícito de `audit_service.log` antes do retorno do documento criado. Por isso, ausência de evento de criação em `audit_logs` não será tratada como prova de inserção externa.

## 3. Perguntas da investigação

1. Quantas alocações existem na turma e quantas continuam ativas?
2. Quais vínculos são `COMPATIBLE`, `REQUIRES_REVIEW`, `LEVEL_MISMATCH` ou `INCOMPATIBLE`?
3. Quantos vínculos ativos ligam `educacao_infantil` a `eja_final`?
4. Quais professores são afetados e quais `course_id` reais estão envolvidos?
5. Os componentes incompatíveis também constam em `classes.course_ids`?
6. O mesmo vínculo aparece em `teacher_allocations`?
7. O mesmo vínculo aparece em `teacher_class_assignments` (DVD)?
8. O componente aparece em `class_schedules`?
9. Há evento de auditoria associado ao `teacher_assignment.id`?
10. Os timestamps indicam criação em lote ou períodos distintos?

## 4. Snapshot mínimo

O coletor gerado localmente executa exatamente **8 consultas**:

1. `classes` — turma exata;
2. `teacher_assignments` — vínculos da turma/ano;
3. `courses` — somente IDs referenciados pelos vínculos;
4. `staff` — somente professores referenciados, tenant-scoped;
5. `teacher_allocations` — mesma turma/ano;
6. `teacher_class_assignments` — mesma turma;
7. `class_schedules` — mesma turma;
8. `audit_logs` — somente IDs dos `teacher_assignments` coletados.

Limites rígidos são aplicados em todas as listas. O tenant é derivado da turma; ausência de `mantenedora_id` interrompe a coleta fail-closed.

## 5. Coleções proibidas

A etapa não lê:

- `students`;
- `enrollments`;
- `grades`;
- `attendance`.

Nenhuma informação acadêmica individual de estudante é necessária.

## 6. Saída offline

O relatório local registra para cada alocação:

- professor;
- componente e nível;
- classificação/rank curricular;
- presença na matriz explícita da turma;
- presença nas fontes concorrentes de vínculo;
- presença no horário;
- timestamps da alocação;
- existência de eventos de auditoria;
- sinal de origem, sem transformar indício em conclusão causal.

O relatório possui hash SHA-256, `database_mutation=false` e `executor_authorized=false`.

## 7. Critério de conclusão

A P0-F7.9A termina quando conseguirmos separar, com evidência:

- erro localizado somente em `teacher_assignments`;
- erro também propagado a outras fontes de vínculo;
- erro já presente na matriz curricular da turma;
- evidência temporal/auditável de criação ou propagação;
- casos sem trilha suficiente, que permanecerão explicitamente como origem indeterminada.

Somente depois disso será desenhada contenção para impedir novas alocações incompatíveis e, separadamente, um plano de correção dos dados existentes com dry-run, rollback e autorização humana explícita antes de qualquer escrita em produção.
