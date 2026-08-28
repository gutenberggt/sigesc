# P0-F7.5 — Aplicabilidade por Série (READ-ONLY)

## Objetivo

Refinar os três casos divergentes de Geografia depois da P0-F7.4, verificando a cobertura das séries/etapas da turma por `grade_levels` e `carga_horaria_por_serie`.

## Entrada canônica

Relatório privado P0-F7.4 com `status=PASS`, cadeia SHA válida, 3 casos e nenhuma decisão automática.

## Regras

- `LEVEL_MISMATCH_PRECEDES_SERIES`: incompatibilidade de nível impede inferência por série.
- `EXPLICIT_SERIES_FULL_MATCH`: `grade_levels` cobre todas as séries da turma.
- `MATRIX_FULL_BUT_EXPLICIT_SCOPE_CONFLICT_REQUIRES_REVIEW`: a matriz por série cobre a turma, mas `grade_levels` declara escopo incompatível/parcial.
- `PER_SERIES_MATRIX_FULL_MATCH`: matriz cobre todas as séries e não há escopo explícito conflitante.
- `PARTIAL_SERIES_MATCH_REQUIRES_REVIEW`: cobertura apenas parcial.
- `NO_SERIES_MATCH`: nenhuma série da turma é coberta.
- `LEVEL_ONLY_NO_SERIES_SCOPE`: nível é compatível, mas não há restrição explícita por série.

## Segurança

- execução offline;
- nenhum acesso MongoDB;
- nenhuma escrita;
- nenhum estudante, nota ou frequência;
- nenhuma recomendação automática;
- nenhuma decisão automática de componente;
- nenhuma decisão automática de carga horária;
- nenhuma autorização de executor.

## Resultado esperado

A fase não escolhe qual registro manter. Ela apenas transforma a divergência de metadados em classificações reproduzíveis para a etapa de decisão/política seguinte.
