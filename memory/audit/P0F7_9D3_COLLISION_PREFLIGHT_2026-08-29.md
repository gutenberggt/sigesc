# P0-F7.9D3 — Collision Preflight

Data: 2026-08-29

## Objetivo

Validar, antes de qualquer plano de remediação, se os `UNIQUE_SAFE_TARGET` da
P0-F7.9D2 poderiam produzir duplicidade lógica em `teacher_assignments`.

A regra vigente no writer considera duplicidade ativa a combinação:
`staff_id + class_id + course_id + academic_year + status=ativo`.

## Escopo

Somente os casos `UNIQUE_SAFE_TARGET` do relatório D2. Os casos
`NO_SAFE_TARGET` não são consultados nem alterados nesta fase.

## Coleta de produção

O coletor é gerado localmente a partir do relatório D2 selado e executa somente:

1. `countDocuments` sobre o subconjunto estrutural necessário;
2. `find` com projeção mínima de `id`, `staff_id`, escola, turma, componente,
   ano, status e tenant.

Limites:

- no máximo 50 propostas de origem;
- no máximo 200 registros correspondentes;
- orçamento exato de 2 consultas;
- sem nomes, CPF, e-mail ou dados de estudantes;
- sem insert/update/delete/bulkWrite.

## Análise offline

Para cada proposta, o analisador:

- confirma que o vínculo fonte ainda existe e não sofreu drift estrutural;
- exige `staff_id` presente;
- exige fonte ainda ativa;
- procura vínculo ativo já existente para o mesmo
  `staff_id + school_id + class_id + target_course_id + academic_year`;
- classifica em:
  - `CLEAR_FOR_REMEDIATION_PLANNING`;
  - `ACTIVE_TARGET_ALREADY_EXISTS`;
  - `SOURCE_DRIFT_REVIEW_REQUIRED`.

## Invariantes

- esta fase não executa remediação;
- nenhuma escrita em produção;
- nenhuma identidade nominal de professor;
- nenhum dado de estudante, matrícula, nota ou frequência;
- qualquer drift bloqueia planejamento automático;
- colisão ativa bloqueia a troca direta de `course_id`.
