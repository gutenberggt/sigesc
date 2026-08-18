# Dashboard do Professor — Ações Diretas com Prefill

## Objetivo

Transformar os cards de **Meus Diários** no ponto de entrada operacional do professor, eliminando a necessidade de abrir uma tela genérica e repetir manualmente escola, turma e componente.

## Contrato de navegação

Os atalhos usam os parâmetros:

- `academic_year`
- `school_id`
- `class_id`
- `course_id`
- `assignment_id` somente quando existe Diário por Vínculo ativo

Esses parâmetros são exclusivamente contexto de UX. Eles não concedem autorização. Cada tela só aplica escola/turma/componente quando o valor existe nas listas que ela própria já carregou para o usuário autenticado, e o backend continua revalidando `assignment_id`.

## Fluxo atual

Para cada componente da turma são exibidos atalhos diretos para:

- Frequência
- Notas / Conceitos
- Conteúdos

As telas canônicas existentes são reutilizadas e recebem escola, turma e componente pré-selecionados.

## Diário por Vínculo

- Frequência recebe o contexto completo e continua usando o `AttendanceContext` + bridge DVD existente.
- Notas / Conceitos recebe o contexto completo; um bridge frontend apenas encaminha `assignment_id` ao adaptador de Fase 5, que o revalida no backend.
- Conteúdos permanece bloqueado no card DVD enquanto `LearningObjects.js` ainda não estiver harmonizado com `content_entries`. Não há fallback silencioso para `/learning-objects` em contexto DVD.

## Segurança

- query string nunca é fonte de permissão;
- o hook de prefill só seleciona IDs presentes nas listas autorizadas da tela;
- `assignment_id` explícito não é confiado pelo backend;
- AEE não é alterado;
- nenhum backend foi modificado nesta entrega.
