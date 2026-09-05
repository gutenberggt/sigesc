# R2.0d — Pareamento Ordinal por Sessão — Luiz 9º B → 9º A

Data: 2026-09-05

## Contexto

A R2.0c.1 classificou os dois documentos de frequência de Matemática do 9º A em 30/04/2026 como `ORPHAN_TWO_DISTINCT_SESSIONS_SUPPORTED`. A diferença não é duplicidade nem sobreposição legado/canônico: os documentos têm `aula_numero` distintos e representam sessões legítimas.

Por isso, o manifesto R2.0b do 9º A, baseado em datas distintas, não pode ser usado diretamente no apply.

## Objetivo

Construir um preflight read-only do período fevereiro–abril/2026 em que:

- cada conteúdo-fonte do 9º B permanece um registro pedagógico único;
- `number_of_classes` da fonte define apenas sua capacidade de slots na análise por sessão;
- cada documento de frequência atribuível a Luiz no 9º A é uma sessão-alvo;
- a chave lógica usa `data + period + aula_numero`;
- `attendance.records` é proibido;
- `number_of_classes` do attendance é apenas diagnóstico e não gera sessões adicionais automaticamente.

## Regras fail-closed

A fase bloqueia quando houver:

- mudança da conclusão R2.0c.1;
- capacidade-fonte inválida;
- colisão de chave de sessão;
- metadados de sessão parcialmente preenchidos entre múltiplos documentos do mesmo dia;
- conteúdo já existente nas datas-alvo;
- binding de destino não resolvido;
- diferença entre total de slots-fonte e total de sessões-alvo.

O pareamento ordinal diagnóstico pode mostrar o prefixo comum quando houver apenas diferença de cardinalidade, mas isso não autoriza escrita parcial.

## Boundary

- Mongo somente leitura;
- nenhuma escrita de frequência/conteúdo;
- sem estudantes, matrículas, notas ou audit_logs;
- sem `attendance.records`;
- sem plaintext pedagógico publicado;
- sem IDs técnicos brutos publicados;
- sem deploy;
- futura R2.1 permanece uma etapa separada, com manifesto congelado, idempotência, rollback e autorização humana explícita.

Tracking: #453 → #439 → #438 → #418. R2.0c.1: #450. Investigação raiz: #357.
