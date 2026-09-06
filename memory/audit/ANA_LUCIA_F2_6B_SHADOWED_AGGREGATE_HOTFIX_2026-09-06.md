# ANA-LUCIA-F2.6B — adjudicação de agregado *shadowed*

Data: 06/09/2026
Tracking principal: #480
Origem: primeira execução F2.6 via #490

## Motivo da fase

A primeira execução F2.6 abortou em `_validate_prewrite` com `ANA_LUCIA_F2_6_AGGREGATE_NOT_PRESERVABLE`, antes do primeiro `update_one`. Portanto, essa tentativa não realizou qualquer mutação em produção.

A F2.5B canônica foi então reexecutada no mesmo estado de produção e confirmou novamente o baseline 198/392, os 74 tenants ausentes deterministicamente adjudicáveis e quatro frequências de 6º ANO A sem `aula_numero`. A classificação detalhada é:

- 19/02/2026 — agregado isolado preservável;
- 05/03/2026 — agregado isolado preservável;
- 12/02/2026 — agregado + duas sessões numeradas no mesmo dia;
- 09/04/2026 — agregado + duas sessões numeradas no mesmo dia.

Os dois últimos casos eram bloqueados pela regra F2.5B anterior à política canônica #480.

## Regra F2.6B

O agregado misto não é convertido, dividido, excluído nem recebe `aula_numero`. Ele só pode acompanhar o remapeamento de `course_id` como evidência histórica *shadowed* se, antes de qualquer escrita:

1. houver exatamente um agregado na origem;
2. não houver agregado nem sessão concorrente na identidade de destino;
3. `class_schedules.schedule_slots` provar os slots da disciplina no dia da semana correspondente;
4. o conjunto de `aula_numero` das sessões existentes for exatamente igual ao conjunto de slots previstos;
5. `number_of_classes` do agregado for exatamente igual ao número de slots previstos.

Se qualquer uma dessas condições falhar, a execução continua fail-closed e nenhum remapeamento começa.

Essa regra é a mesma semântica já introduzida em `diary_canonical_evidence_policy.shadowed_legacy_attendance_ids`: o agregado permanece fisicamente preservado, mas, quando todas as sessões exatas existem, não representa uma terceira aula nem um falso órfão.

## Correção da métrica de linhagem

A inspeção também isolou uma diferença de definição entre fases:

- 141 documentos candidatos possuem `copied_from_id` (arestas de cópia);
- esses 141 documentos apontam para 74 pais distintos;
- 140 arestas apontam para pai dentro do conjunto candidato;
- 1 aresta aponta para pai já ausente antes do saneamento;
- não há ciclos e o remapeamento conjunto não cria nova quebra cross-identity.

A F2.4 havia exposto 74 como `copied_candidates` porque contava pais distintos. O F2.6 validava documentos-filhos e, portanto, precisava comparar 141/140/1. A F2.6B corrige a comparação, sem alterar `copied_from_id`.

## Boundary

A F2.6B não contém mutadores MongoDB. Ela apenas substitui a validação pré-escrita do F2.6. A superfície de escrita permanece exclusivamente no executor F2.6:

- aplicação: `update_one` com `$set: {course_id: current_id}`;
- rollback compensatório: `update_one` com `$set: {course_id: legacy_id}`.

Continuam proibidos: backfill de tenant, inferência/backfill de `aula_numero`, alteração de `copied_from_id`, autoria, `attendance.records`, conteúdo pedagógico, notas, exclusões, inserts ou update_many.
