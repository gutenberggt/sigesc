# P0 #250 — F2.7: correção do cutover parcial de Conteúdo

Data: 2026-08-30

## Evidência que motivou a correção

A F2.6.1 confirmou em produção o cenário misto do caso-canário do 5º ANO A:

- 9 componentes ativos em `teacher_assignments`;
- 7 componentes com caminho DVD/canônico de conteúdo;
- Língua Portuguesa e Matemática sem `teacher_class_assignments` DVD correspondentes;
- `GET /learning-objects` class-wide da professora retornando 409 em abril, maio e junho;
- Português e Matemática, quando consultados isoladamente, retornando HTTP 200 com cardinalidade idêntica ao Mongo e ao Super Administrador tenant-scoped.

O defeito funcional não é ausência de dados. É um **cutover parcial**: a existência de qualquer candidato DVD fazia o frontend substituir a leitura class-wide por uma agregação apenas dos vínculos canônicos, omitindo componentes ainda legados.

## Contrato F2.7

A leitura class-wide do professor passa a ser composta em uma SSoT backend:

1. o entitlement nasce dos `teacher_assignments` ativos do professor para turma + ano + tenant, preservando a semântica de `/professor/turmas`;
2. componentes com diário DVD `content_enabled` usam `list_assignment_content_history`, mantendo histórico/cutover/precedência canônica existentes;
3. somente os componentes alocados que **não** possuem cobertura canônica usam `learning_objects` legado;
4. o fallback legado é sempre `course_id in legacy_only_course_ids` + turma + ano + tenant;
5. nenhum componente fora do entitlement do professor entra na projeção;
6. falha ao compor histórico de componente já canônico é fail-closed: não há fallback silencioso para o legado;
7. gestão e consultas component-scoped preservam o comportamento anterior.

## Frontend

`contentPartialCutoverResolver.js` não compõe registros. Ele apenas marca o GET class-wide da página do professor com `__skipContentDvdBridge`, impedindo que os bridges antigos convertam essa leitura em uma agregação exclusivamente canônica. A própria requisição `/learning-objects` é atendida pelo reader misto backend.

Os fluxos com componente explícito, check-date, PDF e writes continuam sob os bridges DVD existentes.

## Regressão obrigatória

O teste F2.7 modela explicitamente:

- 9 componentes autorizados;
- 7 componentes DVD/canônicos;
- Língua Portuguesa legado com 13 registros de junho;
- Matemática legado com 5 registros de junho;
- um 10º componente não alocado que não pode vazar;
- falha do histórico canônico que deve permanecer fail-closed;
- ausência de entitlement que deve produzir lista vazia sem consulta ampla.

Critério principal: a projeção class-wide contém os 9 componentes; Português e Matemática permanecem legados/read-only; os 7 demais permanecem canônicos; o componente não alocado permanece invisível.

## Limites de segurança

- nenhuma migração;
- nenhum backfill;
- nenhuma alteração de conteúdo persistido;
- nenhuma alteração em `teacher_assignments` ou `teacher_class_assignments`;
- nenhuma expansão de RBAC;
- nenhum remapeamento por nome;
- nenhuma escrita MongoDB introduzida pela F2.7.

A issue #250 permanece aberta até validação pós-deploy do caso real.
