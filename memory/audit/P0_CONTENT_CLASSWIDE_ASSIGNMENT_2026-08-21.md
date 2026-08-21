# P0 raiz — divergência de assignment class-wide no conteúdo DVD

Data: 2026-08-21

## Caso sentinela

Professora Karina Soares de Oliveira — Escola 22 de Abril — turma 1º e 2º Ano.

Erro revelado após remoção da falha silenciosa e do crash React #31:

`Arte (criar): Este vínculo já utiliza o Diário por Vínculo Docente. Conteúdos devem ser acessados pelo motor canônico content_entries. [DVD_CONTENT_LEGACY_BLOCKED]`

## Causa raiz

O contrato canônico do backend considera um assignment com `component_id = null` como vínculo **class-wide**, compatível com qualquer componente da turma. Isso é expresso por `_component_matches()` em `content_assignment_scope.py`.

O bridge histórico do frontend, porém, filtrava candidatos por igualdade estrita quando havia componente: `diary.component_id === componentId`. Assim, um vínculo class-wide válido era descartado para Arte, Matemática, Língua Portuguesa etc. A requisição então permanecia no endpoint legado `/learning-objects`, onde o guard de cutover corretamente devolvia `DVD_CONTENT_LEGACY_BLOCKED`.

## Correção P0

Foi adicionada uma camada de compatibilidade estreita, registrada depois do `contentDvdBridge`, para atuar apenas quando o bridge original não encontra vínculo específico e existe exatamente um vínculo class-wide autorizado:

1. vínculo específico continua tendo precedência;
2. se não houver específico, `component_id = null` pode ser usado para o componente solicitado;
3. múltiplos vínculos class-wide permanecem fail-closed com `DVD_CONTENT_ASSIGNMENT_AMBIGUOUS`;
4. criação é encaminhada para `/content-entries` com `assignment_id` explícito;
5. check-date e listagem por componente usam o mesmo assignment canônico;
6. cópia para turma com vínculo class-wide usa `target_assignment_id` canônico e preserva o vínculo de origem;
7. o fluxo legado permanece intacto quando realmente não existe contexto DVD compatível.

## Segurança arquitetural

- nenhum RBAC foi relaxado;
- nenhum assignment é criado, alterado ou migrado;
- nenhum conteúdo é reatribuído no banco;
- o frontend só usa vínculos retornados por `/professor/diarios`, que já são autorizados para o professor autenticado;
- o backend canônico continua sendo a autoridade final de autorização e persistência;
- vínculo específico tem precedência sobre class-wide;
- ambiguidade permanece bloqueante.

## Regressão

`backend/tests/test_content_classwide_assignment_p0.py` protege:

- paridade com o contrato `_component_matches()` do backend;
- precedência de vínculo específico;
- fallback class-wide único;
- fail-closed em ambiguidade;
- criação e cópia roteadas para `content_entries`;
- ordem de registro do resolver após o bridge original.

Workflow permanente: `Content Class-wide Assignment P0 Guard`.

## Critério de aceite em produção

Na turma 1º e 2º Ano da Escola 22 de Abril:

- salvar Arte e demais componentes deve persistir em `content_entries` sem `DVD_CONTENT_LEGACY_BLOCKED`;
- a operação não pode cair em `/learning-objects` quando existir vínculo class-wide autorizado;
- copiar conteúdo para outra turma com vínculo class-wide deve usar o motor canônico e não produzir React #31;
- se houver inconsistência real de vínculo, a mensagem estruturada deve continuar legível e fail-closed.
