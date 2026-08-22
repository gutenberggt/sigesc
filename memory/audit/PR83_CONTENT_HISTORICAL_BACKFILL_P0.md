# PR #83 — P0 Conteúdo histórico anterior ao cutover DVD

Data: 2026-08-22

## Incidente reproduzido

- Professora: Ivanilde Freire Batista da Silva
- Escola: E M E I E F 22 de Abril
- Turma: 3º/4º/5º ANO
- Componente: Arte
- Data do conteúdo: 01/06/2026
- `teacher_class_assignment`: `77fd25ee-5157-54d0-9806-81dae056d7b3`
- `valid_from`: 18/08/2026
- Erro observado: `DVD_CONTENT_LEGACY_BLOCKED`

## Causa

O frontend resolvia assignments considerando a data pedagógica. Para 01/06 não havia assignment vigente e a requisição caía em `/learning-objects`. O guard legado, por sua vez, verificava a existência do DVD vigente no presente e bloqueava o endpoint legado. O resultado era um vazio de escrita para datas anteriores ao cutover.

## Invariante adotada

Qualquer data pedagógica permitida pelas regras já existentes de ano letivo/bimestre pode ser registrada sem reabrir escrita no legado.

Para datas anteriores ao `valid_from`, o vínculo DVD posterior é usado apenas como prova de propriedade/capability. A validade do vínculo não é retrodatada.

## Implementação

1. `content_assignment_scope` reconhece backfill quando a data é anterior ao `valid_from` e autoriza o professor na data real de início do vínculo.
2. O registro continua sendo gravado em `content_entries` com `assignment_id` e snapshot canônico.
3. O history bridge passa a exibir `content_entries` anteriores ao cutover e deriva `historical_backfill=true` quando `date < valid_from`.
4. Um backfill canônico prevalece na leitura sobre um legado equivalente da mesma turma/componente/professor/data.
5. `contentDvdHistoricalBackfillResolver.js` intercepta check-date, criação e cópia histórica antes que a requisição possa cair em `/learning-objects`.
6. O fluxo normal em datas iguais ou posteriores a `valid_from` permanece inalterado.

## Guardrails preservados

- `learning_objects` continua read-only no contexto DVD.
- Professor, turma, componente, escola, tenant e capability continuam validados pelo autorizador canônico.
- Nenhum `teacher_class_assignment.valid_from` é alterado.
- A autorização histórica não permite transformar uma data posterior a um vínculo expirado em backfill anterior.

## Regressão obrigatória

O teste dedicado cobre exatamente:

`Ivanilde -> 3º/4º/5º ANO -> Arte -> 01/06/2026 -> DVD valid_from 18/08/2026`

Resultado esperado: resolução canônica com o assignment existente, `historical_backfill=True` e `valid_from` preservado em 18/08/2026.
