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
- revalida localmente, em defesa em profundidade, **turma + componente + data/ano/mês + ausência de assignment** antes de compor qualquer item;
- mescla os canônicos aos registros legados sem converter ou regravar os legados;
- mantém cache local dos canônicos para que o GET individual permaneça canônico;
- aplica compatibilidade equivalente ao `check-date`.

A composição automática de listagem/check-date é estritamente read-only. Se, depois de enxergar um registro canônico já existente, o professor executar explicitamente uma edição ou exclusão pela tela histórica, a operação é mantida nos endpoints de `content_entries`; ela nunca volta a gravar em `learning_objects`.

## Gate anti-falso-positivo antes do merge

Após questionamento do owner, a PR passou a exigir regressão comportamental explícita para provar que o hotfix não reinterpretará o conjunto histórico investigado anteriormente.

O gate deve comprovar:

1. um `content_entry` administrativo sem `assignment_id`, da **mesma turma + mesmo componente**, é elegível para a composição;
2. registros da mesma turma em **outros componentes** são rejeitados, inclusive fixtures que reproduzem os volumes históricos 111 (8º A) e 98 (9º A) encontrados fora de Matemática;
3. um registro legado normal de maio permanece inalterado quando não há fallback canônico elegível;
4. se um bridge DVD anterior já reescreveu a consulta para `/content-entries`, o fallback R2.0g.4 não compõe novamente e não duplica;
5. `check-date` aceita somente a data exata;
6. `legacy_id` continua impedindo duplicação quando um legado já possui representação canônica.

Essas provas são sintéticas/determinísticas. Elas não afirmam que os 111/98 registros históricos eram Matemática; ao contrário, selam que **não podem ser projetados como Matemática apenas por esta ponte**.

## Limites

- nenhuma migração;
- nenhuma escrita automática decorrente da mera visualização;
- nenhuma nova escrita em `learning_objects`;
- nenhuma mutação de dados de produção durante a preparação desta PR;
- nenhuma alteração de RBAC do R2.0g;
- `content_entries` permanece SSoT;
- qualquer edição/exclusão futura depende de ação explícita do usuário e continua canônica;
- deploy depende de gate humano separado.
