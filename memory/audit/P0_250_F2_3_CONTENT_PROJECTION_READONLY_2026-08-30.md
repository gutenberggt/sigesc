# P0 #250 — F2.3 Paridade read-only de Objetos de Conhecimento

Data: 30/08/2026

## Contexto

Após a correção do Livro de Promoção, o smoke visual revelou uma segunda divergência no mesmo caso-canário: a tela **Objetos de Conhecimento** apresenta uma lista diferente entre o Super Administrador e a professora Abadia Alves Martins para a turma **5º ANO A**, escola **E M E I E F Jose Pereira Barbosa**, ano letivo 2026.

A leitura estática confirmou duas projeções distintas:

- gestão, na rota normal, consulta o reader legado `GET /learning-objects`, baseado em `learning_objects`;
- professor, na rota `/professor/objetos-conhecimento`, é interceptado pelo `contentDvdBridge` e lê `content_entries` + histórico `learning_objects` autorizado por `teacher_class_assignments`.

Em Anos Iniciais, a própria `LearningObjects.js` busca o mês por turma sem exigir `course_id`, então a diferença visual não deve ser atribuída apenas ao estado do seletor de componente.

## Objetivo da F2.3

Determinar, sem qualquer escrita, por que os registros do mês de **junho/2026** divergem entre as duas visões.

A unidade estrutural de comparação é:

`data + componente`

Nenhum texto pedagógico é necessário para o diagnóstico.

## Fontes comparadas

1. `learning_objects` — projeção legada usada pela gestão.
2. `teacher_class_assignments` — escopo DVD vigente do professor.
3. `content_entries` + histórico legado — composição produzida por `list_assignment_content_history`, a mesma SSoT usada pelo bridge do professor.
4. `teacher_assignments` — apenas para conferir a cardinalidade dos componentes legados já conhecida no caso-canário.
5. `courses` — somente para rotular os componentes nos resultados estruturais.

## Classificação dos slots existentes apenas na gestão

Cada `data + componente` que aparece em `learning_objects` e não aparece na projeção do professor recebe uma causa estrutural:

- `OUTSIDE_PROFESSOR_COMPONENT_SCOPE`: o componente não pertence aos vínculos de conteúdo do professor;
- `LEGACY_AFTER_COMPONENT_CUTOVER`: o registro legado é posterior ao `valid_from` do vínculo, quando o histórico DVD já deve ser exclusivamente canônico;
- `ASSIGNMENT_VALID_FROM_MISSING`: o vínculo não fornece uma data de corte válida;
- `EXPECTED_IN_PROFESSOR_HISTORY`: o componente pertence ao professor e a data está dentro do fallback histórico, mas o registro não chegou à projeção do professor. Este é o caso que caracteriza gap real de projeção.

`recorded_by` é consultado somente para classificar proveniência como "professor alvo" ou "outro/desconhecido". O valor do ID nunca é emitido. A própria SSoT de histórico estabelece que `recorded_by` não restringe a visibilidade histórica quando o assignment já autoriza turma/componente.

## Classificações finais

- `CONTENT_PROJECTION_PARITY`
- `PROFESSOR_CONTENT_ENTITLEMENT_DRIFT`
- `CONTENT_PROJECTION_GAP_WITHIN_AUTHORIZED_SCOPE`
- `CONTENT_VIEW_DIFFERENCE_EXPLAINED_BY_SCOPE_OR_CUTOVER`
- `CONTENT_CANONICAL_ONLY_ROWS_PRESENT`

## Limites de segurança

A F2.3 é estritamente diagnóstica:

- MongoDB: somente `find`/`find_one`;
- nenhuma chamada HTTP é necessária;
- nenhuma criação, alteração, exclusão ou backfill;
- nenhum deploy/restart;
- nenhum texto de conteúdo pedagógico é emitido;
- nenhum ID de registro, professor ou estudante é emitido;
- nenhum token de autenticação é criado ou utilizado;
- o artefato retido contém apenas metadados estruturais: data, componente, origem, contagens e classificação.

O workflow possui gate AST que falha se o coletor contiver primitivas de mutação MongoDB.

## Execução protegida

A coleta real em produção só pode ocorrer após o código estar em `main` e mediante issue criada pelo proprietário no formato:

Título:

`[P0-250-F2.3-CONTENT-AUDIT] <TARGET_SHA>`

Body:

```text
P0_250_F2_3_AUDIT=AUTHORIZED
CONFIRMATION=VERIFY_P0_250_F2_3_CONTENT_PROJECTION_READ_ONLY
TARGET_SHA=<TARGET_SHA>
```

O workflow confirma fail-closed que `main` ainda aponta exatamente para o SHA autorizado antes de acessar o servidor.

## Fora de escopo

Esta fase não:

- altera a SSoT de conteúdo;
- remapeia componentes;
- altera vínculos docentes;
- modifica registros pedagógicos;
- consolida `learning_objects` e `content_entries`;
- fecha a #250 automaticamente;
- autoriza qualquer correção funcional posterior.

A correção, se necessária, será decidida somente após a evidência read-only da F2.3.
