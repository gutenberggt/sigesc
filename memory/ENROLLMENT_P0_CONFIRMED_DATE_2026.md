# Reconciliação P0 — data administrativa confirmada (2026)

## Contexto

Após a reconciliação segura de 102 matrículas canônicas ausentes, restaram 7 estudantes com vínculo acadêmico comprovado na turma atual de 2026, mas sem `students.enrollment_date` e sem evento de matrícula/remanejamento no `student_history`.

A forense temporal mostrou que `students.created_at` é posterior à primeira frequência desses estudantes e, portanto, representa cadastro/importação no SIGESC, não a data administrativa da matrícula.

A data administrativa original foi confirmada como **2026-01-15**. Esta data não será inferida de frequência, nota ou `created_at`.

## Estratégia

O script `backend/scripts/reconcile_enrollment_p0_confirmed_date_2026.py` trata apenas esse tipo de reconstrução e opera em modo READ-ONLY por padrão.

Proteções:

- data confirmada obrigatória em ISO e restrita a 2026;
- manifesto explícito com `ready`/`quarantine`;
- estudante ainda ativo e na mesma turma do manifesto;
- turma regular de 2026, mesma escola e mesma mantenedora;
- número de matrícula preservado e sem conflito;
- primeira frequência na própria turma atual obrigatória;
- data confirmada não pode ser posterior à primeira frequência;
- matrícula preexistente divergente bloqueia o caso;
- execução já concluída com mesmo `source`, número, turma e data é reconhecida como `ALREADY_CANONICAL`;
- escrita somente via `create_active_enrollment`;
- `source=repair:p0-enrollment-confirmed-date-2026`;
- `observations` registra que a data foi confirmada administrativamente e não inferida;
- notas e frequências não são alteradas;
- aplicação exige token e contagem explícitos.

## Fora do escopo

Não trata os 2 casos com histórico `relocated/cancelled`, o caso exclusivamente AEE, matrículas órfãs, turmas inexistentes ou status legados.
