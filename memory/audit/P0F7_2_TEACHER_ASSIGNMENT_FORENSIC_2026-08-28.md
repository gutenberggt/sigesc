# P0-F7.2 — Forense read-only do blocker de alocação docente

## Origem

O P0-F7 de produção encontrou exatamente 1 blocker de classe `TEACHER_ASSIGNMENT_SEMANTIC_REVIEW_REQUIRED` no grupo **Geografia**, com classificação `DIVERGENT_ACTIVE_ASSIGNMENT_REQUIRES_REVIEW` e contagem 3.

## Objetivo

Expandir os três casos de `teacher_assignments` em contexto humano e auditável, sem escolher vencedor e sem alterar dados.

A fase:

- valida a cadeia P0-F5 -> P0-F6 selado -> P0-F7 por SHA;
- localiza exatamente o caso de Geografia no pacote P0-F5;
- recupera `source_id` e `target_id` do par de courses sem hardcode;
- exige exatamente um blocker docente P0-F7 para o grupo solicitado;
- consulta somente `teacher_assignments`, `staff`, `classes`, `schools`, `users` e metadados de `audit_logs`;
- replica a chave natural do P0-F3: `staff_id + class_id + academic_year` para registros ativos;
- replica `TA_COMPARE_FIELDS` do P0-F3 para classificar divergência;
- exige que a quantidade viva da classificação coincida com o blocker P0-F7;
- mostra docente, turma, escola, campos divergentes, metadados de cada assignment e resumo de auditoria;
- não inclui dados de estudantes;
- não emite recomendação automática;
- grava relatório privado `0600` e stdout compacto.

## Campos comparados

- `school_id`
- `carga_horaria_semanal`
- `is_substituicao`
- `substituted_staff_id`
- `data_inicio_substituicao`
- `data_fim_substituicao`

## Segurança

- read-only;
- nenhuma chamada MongoDB de escrita;
- nenhum `--apply`;
- sem remapeamento de course;
- sem merge/delete de assignment;
- sem decisão automática;
- `not_authorization_for_executor = true`.

## CLI

```bash
python scripts/audit_p0f7_2_teacher_assignment_forensic.py \
  --packet <p0f5-private-review.json> \
  --sealed <p0f6-human-decisions-sealed.json> \
  --preflight <p0f7-private-preflight.json> \
  --academic-year 2026 \
  --group-name Geografia \
  --json <p0f7-2-teacher-assignment-forensic.json>
```

## Resultado esperado

Para a fotografia observada em produção, a execução deverá documentar exatamente 3 casos `DIVERGENT_ACTIVE_ASSIGNMENT_REQUIRES_REVIEW`. Qualquer mudança de quantidade ou classificação falha fechado.

Uma eventual adjudicação desses três vínculos será etapa posterior e separada; este relatório não autoriza mutações.
