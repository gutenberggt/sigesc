# R2.0g.4 — Visibilidade canônica no fluxo legado

## Sintoma

Após uma cópia administrativa R2.0g para uma turma/componente ainda operando no fluxo legado, o registro é persistido em `content_entries`, mas a tela `LearningObjects.js` do professor pode abrir a data como `Novo Registro`.

## Causa

`contentDvdBridge` só redireciona a listagem `/learning-objects` para `/content-entries` quando `/professor/diarios` resolve um vínculo DVD com conteúdo habilitado. Sem candidato DVD, a requisição permanece no endpoint legado, cuja listagem lê apenas `learning_objects`. Assim, um `content_entry` canônico sem `assignment_id` fica invisível na tela histórica.

## Correção

Foi adicionada uma camada de compatibilidade de leitura no frontend:

- atua somente na página de conteúdo do professor;
- marca apenas listagens com turma e componente específicos;
- deixa os bridges DVD anteriores terem precedência;
- se a URL final continuar em `/learning-objects`, consulta `content_entries` para a mesma turma/componente;
- considera somente registros canônicos sem `assignment_id` no fallback legado;
- reaplica os filtros de ano/mês da tela histórica;
- mescla os canônicos aos registros legados sem converter ou regravar os legados;
- mantém cache local dos canônicos para que o GET individual permaneça canônico;
- aplica compatibilidade equivalente ao `check-date`.

A composição automática de listagem/check-date é estritamente read-only. Se, depois de enxergar um registro canônico já existente, o professor executar explicitamente uma edição ou exclusão pela tela histórica, a operação é mantida nos endpoints de `content_entries`; ela nunca volta a gravar em `learning_objects`.

## Limites

- nenhuma migração;
- nenhuma escrita automática decorrente da mera visualização;
- nenhuma nova escrita em `learning_objects`;
- nenhuma mutação de dados de produção durante a preparação desta PR;
- nenhuma alteração de RBAC do R2.0g;
- `content_entries` permanece SSoT;
- qualquer edição/exclusão futura depende de ação explícita do usuário e continua canônica;
- deploy depende de gate humano separado.
