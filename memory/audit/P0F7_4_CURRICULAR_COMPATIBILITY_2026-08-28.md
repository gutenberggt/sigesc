# P0-F7.4 — Compatibilidade Curricular dos 3 casos de Geografia

Data: 2026-08-28

## Objetivo

Eliminar a ambiguidade curricular remanescente da P0-F7.3 antes de qualquer decisão sobre `carga_horaria_semanal` ou consolidação das alocações duplicadas.

A P0-F7.3 demonstrou que a identidade acadêmica favorece o `target` nos três casos, e que o conflito semanal é sempre `source=2` × `target=3`. Entretanto, uma das turmas chama-se `MULTI 3º E 4º ETAPA`, o que pode representar EJA Anos Finais. Como o modelo do SIGESC diferencia `fundamental_anos_finais`, `eja` e `eja_final`, esta subfase verifica o nível explícito da turma antes de considerar qualquer decisão.

## Fontes consultadas

Somente leitura em:

- `classes` — `education_level`, `nivel_ensino`, `grade_level`, `series`, `course_ids`, tenant e metadados seguros;
- `courses` — par source/target e todos os componentes de mesmo nome no mesmo tenant.

O relatório P0-F7.3 é validado por SHA canônico antes da consulta ao banco.

## Classificação

Para cada lado (`source` e `target`):

- `EXACT_LEVEL_MATCH` — nível explícito da turma e nível do componente são iguais;
- `BROAD_EJA_MATCH_REQUIRES_REVIEW` — turma `eja_final`, componente `eja`;
- `SPECIALIZED_EJA_MATCH_REQUIRES_REVIEW` — turma `eja`, componente `eja_final`;
- `LEVEL_MISMATCH` — níveis explicitamente incompatíveis;
- `UNKNOWN_CLASS_LEVEL` — turma sem nível explícito;
- `UNKNOWN_COURSE_LEVEL` — componente sem nível explícito.

O auditor também lista candidatos `Geografia` do mesmo tenant cujo nível coincide exatamente com o nível da turma.

## Invariantes

- READ-ONLY;
- multi-tenant fail-closed;
- nenhum identificador de estudante;
- nenhum valor de nota ou frequência;
- sem `--apply`;
- sem remapeamento automático;
- sem decisão automática de curso;
- sem decisão automática de carga horária;
- não autoriza executor.

## Decisão posterior

A saída desta fase serve apenas para determinar se o `target` de `fundamental_anos_finais` é curricularmente compatível nos três casos ou se o caso de `3º/4º ETAPA` exige tratamento EJA separado.

Nenhuma escrita de produção é autorizada por este documento ou pelo auditor.
