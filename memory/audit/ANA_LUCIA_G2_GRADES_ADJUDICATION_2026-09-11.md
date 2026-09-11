# ANA-LUCIA-G2 — Adjudicação read-only das notas

Data: 11/09/2026
Tracking: #694

## Baseline G1
- 201 documentos legados;
- 54 documentos canônicos;
- 149 `LEGACY_ONLY`;
- 47 `BOTH_COMPLEMENTARY`;
- 5 `BOTH_IDENTICAL`;
- 2 `CANONICAL_ONLY`;
- 2 `NO_GRADE`;
- zero conflito de valor detectado;
- 255 documentos sem `grade_ownership`.

## Objetivo G2
Provar se é possível executar uma reconciliação determinística em que:
1. `LEGACY_ONLY` seja remapeado preservando o próprio documento;
2. `BOTH_COMPLEMENTARY` tenha somente campos ausentes materializados no canônico e a origem legada retirada após verificação;
3. `BOTH_IDENTICAL` preserve o canônico e retire a duplicata legada após prova de igualdade;
4. `CANONICAL_ONLY` permaneça intocado;
5. `NO_GRADE` permaneça sem criação artificial de nota.

A adjudicação inventaria também `migrated_from_class_id`, `rectified_fields`, `assignment_id`, `dependency_id`, tenant e sobreposições iguais para impedir perda de proveniência.

## Boundary
Somente leitura. Nenhuma PII ou valor acadêmico é emitido.

## Gate
Título: `[ANA-LUCIA-G2-RUNTIME] <SHA-de-main>`

```
ANA_LUCIA_G2_RUNTIME=AUTHORIZED
CONFIRMATION=READ_ONLY_GRADES_ADJUDICATION
ACADEMIC_YEAR=2026
TRACKING_ISSUE=694
TARGET_SHA=<SHA exato de main>
```
