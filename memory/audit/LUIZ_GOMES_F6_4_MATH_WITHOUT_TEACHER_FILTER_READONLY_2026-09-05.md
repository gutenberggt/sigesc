# LUIZ-GOMES-F6.4 — Matemática sem filtro docente (read-only)

Data: 2026-09-05
Tracking: #357

## Motivação

Após F6.3d.2 terminar em `INCONCLUSIVE / HISTORICAL_SCHEMA_INSUFFICIENT`, surgiu uma hipótese independente e ainda não isolada de forma direta: os registros de Matemática de fevereiro, março e abril de 2026 para 8º ANO A e 9º ANO A podem existir no banco atual, mas sem vínculo correto com Luiz Gomes dos Santos.

A F6.2 não fechou exatamente essa hipótese porque, embora tenha carregado `learning_objects` por turma/data, o conjunto `target_candidates` excluía os registros cujo `course_id/component_id` já correspondia à identidade corrente de Matemática. Portanto, era necessário um probe cuja seleção primária ignorasse completamente professor.

## Pergunta técnica

Existem registros de Matemática para:

- E M E I E F Jose Pereira Barbosa;
- 8º ANO A e 9º ANO A;
- 2026-02-01 <= data < 2026-05-01;

quando a seleção é feita somente por turma + período + todas as identidades de Matemática, sem filtrar `teacher_id`, `recorded_by`, `created_by`, `updated_by`, `staff_id` ou `assignment_id`?

## Fontes

Somente metadados de:

- `schools`
- `classes`
- `courses`
- `users` e `staff` somente após a seleção, para classificar autoria
- `teacher_assignments` e `teacher_class_assignments` somente após a seleção, para classificar assignment
- `learning_objects`
- `content_entries`

Não consultar:

- `students`
- `enrollments`
- `attendance`
- `grades`

Não ler nem emitir conteúdo pedagógico (`content`, `methodology`, `observations`, `resources`).

## Classificações relevantes

Por turma:

- `NO_MATH_RECORDS_FOUND_WITHOUT_TEACHER_FILTER`
- `MATH_RECORDS_FOUND_WITHOUT_TEACHER_FILTER`
- `MATH_RECORDS_WITHOUT_ACTOR_OR_ASSIGNMENT_CONFIRMED`
- `MATH_RECORDS_SOFT_DELETED_PRESENT`
- `MATH_RECORDS_POSTSELECT_ATTRIBUTABLE_TO_LUIZ`
- `MATH_RECORDS_PRESENT_BUT_NOT_POSTSELECT_ATTRIBUTABLE_TO_LUIZ`
- `UNRESOLVED_COMPONENT_ROWS_EXIST_IN_PERIOD`

A autoria é classificada somente depois que os registros de Matemática já foram selecionados sem professor:

- `LUIZ_EXPLICIT_ACTOR`
- `LUIZ_ASSIGNMENT_ONLY`
- `OTHER_EXPLICIT_ACTOR`
- `OTHER_OR_UNKNOWN_ASSIGNMENT_ONLY`
- `FOREIGN_EXPLICIT_ACTOR_WITH_LUIZ_ASSIGNMENT`
- `NO_ACTOR_OR_ASSIGNMENT_METADATA`

## Boundary

- MongoDB read-only.
- Nenhuma chamada HTTP ao produto.
- Nenhuma mutação/backfill/remapeamento.
- Nenhum ID técnico emitido.
- Nenhum dado estudantil.
- Nenhuma frequência/`attendance.records`.
- Nenhuma nota.
- Nenhum plaintext pedagógico lido ou emitido.
- Produção é somente observada.

## Interpretação

Resultado positivo não autoriza correção automática. Se forem encontrados registros sem autoria, soft-deleted ou com ator/assignment divergente, a próxima fase deve adjudicar a proveniência e a correspondência lógica antes de qualquer escrita.
