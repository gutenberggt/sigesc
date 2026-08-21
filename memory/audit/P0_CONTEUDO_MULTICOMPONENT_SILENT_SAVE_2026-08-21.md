# P0 — falha silenciosa ao salvar conteúdo multicomponente

Data: 2026-08-21
Caso sentinela: professora Karina Soares de Oliveira — Escola 22 de Abril — turma 1º e 2º Ano.

## Sintoma

A professora informa que o registro de conteúdo simplesmente não é salvo. O fluxo afetado é o de Educação Infantil/Anos Iniciais, que sincroniza vários componentes no mesmo dia.

## Defeito confirmado no frontend

`LearningObjects.handleSave()` executava `create`, `update` e `delete` de cada componente com `.catch(() => null)`. Qualquer 403/409/422/500, erro de resolução de `assignment_id` ou falha de rede era descartado. Em seguida, a interface calculava a mensagem de sucesso pela quantidade de operações planejadas, e não pelas operações efetivamente persistidas.

Isso permitia falso sucesso e impedia conhecer a causa real do caso da professora.

## Correção

- substitui descartes silenciosos por `Promise.allSettled`;
- contabiliza somente operações realmente concluídas;
- associa cada falha ao componente e à ação (`criar`, `atualizar` ou `excluir`);
- preserva `detail.message` e `detail.code` quando o backend retorna erro estruturado;
- em falha parcial, recarrega os registros persistidos antes de permitir nova tentativa;
- mantém o formulário aberto e informa claramente que houve falha/resultado parcial;
- somente fecha o formulário e limpa o rascunho quando todas as operações terminam com sucesso.

## Invariantes

1. A correção não altera `content_entries`, `learning_objects` ou vínculos no banco.
2. Não relaxa RBAC nem a autorização do Diário por Vínculo.
3. Não reutiliza `assignment_id` de um componente para outro.
4. Não transforma histórico legado em gravável.
5. A causa específica do caso Karina deve ser obtida pela nova mensagem real do backend após deploy/teste operacional, caso a persistência continue sendo rejeitada.

## Regressão permanente

`backend/tests/test_professor_content_parity_p0.py` passa a exigir que o bloco multicomponente de `handleSave()`:

- não contenha `.catch(() => null)`;
- use `Promise.allSettled`;
- conte somente operações concluídas;
- preserve erro técnico estruturado;
- recarregue o estado persistido quando houver falha parcial.

## Critério de aceite

No teste de Karina, ao salvar conteúdo da turma 1º e 2º Ano:

- se todos os vínculos estiverem corretos, o conteúdo deve persistir normalmente;
- se houver inconsistência de vínculo, componente ou data, o SIGESC deve informar o componente e o erro técnico estruturado, sem exibir falso sucesso.
