# R2.0e — Calibração Semântica no próprio 9º B

Data: 2026-09-05

## Escopo

Caso: Luiz Gomes dos Santos / Matemática / E M E I E F Jose Pereira Barbosa.

Turma usada como fonte de calibração: **9º ANO B**.

Período: `2026-02-01 <= date < 2026-05-01`.

Tracking: #456 → #439 → #438 → #418. Investigação raiz: #357.

## Motivação

A R2.0d demonstrou que expandir os 33 conteúdos legados do 9º B por `number_of_classes` gera 66 slots, enquanto o 9º A possui 38 sessões reais de frequência no período. Isso impede interpretar automaticamente `number_of_classes` como quantidade de registros de conteúdo a serem escritos.

A R2.0e calibra a semântica **no próprio 9º B**, comparando conteúdo e frequência da mesma turma e do mesmo componente.

## Hipóteses

- `ONE_CONTENT_PER_DATE_COVERS_SESSION_DOCUMENTS_SUPPORTED`: um conteúdo por data cobre as sessões/documentos daquele dia e sua carga declarada coincide com a quantidade de sessões.
- `ONE_CONTENT_PER_DATE_COVERS_DECLARED_LOAD_SUPPORTED`: um conteúdo por data cobre a carga de frequência declarada no dia, ainda que a frequência esteja agregada em menos documentos.
- `ONE_CONTENT_PER_SESSION_SUPPORTED`: há um conteúdo unitário por sessão unitária.
- `MIXED_HISTORICAL_GRANULARITY`: coexistem padrões distintos.
- `INSUFFICIENT_OR_CONFLICTING_EVIDENCE`: lacunas ou conflitos impedem regra confiável.

## Regras

1. Não usar a autoria dos conteúdos do 9º B como prova de autoria do Luiz.
2. Considerar todos os conteúdos institucionais de Matemática da turma-fonte.
3. Não bloquear múltiplos conteúdos na mesma data antes da calibração, pois isso pode representar granularidade por sessão.
4. Comparar, por data:
   - quantidade de conteúdos;
   - quantidade de documentos/sessões de frequência;
   - soma de `number_of_classes` dos conteúdos;
   - soma de `number_of_classes` da frequência;
   - presença de `aula_numero` e `period`;
   - colisões de chave de sessão.
5. Lacunas conteúdo↔frequência, colisões ou metadados parciais permanecem fail-closed.
6. Nenhuma regra inferida é aplicada automaticamente à R2.1.

## Boundary

- read-only;
- `attendance.records` não projetado/lido;
- sem estudantes, matrículas, notas ou audit_logs;
- sem escrita acadêmica;
- sem deploy;
- plaintext pedagógico lido apenas para fingerprint privado e nunca emitido;
- sem IDs técnicos brutos no manifesto público;
- resultado determinístico por SHA-256.

## Estado antes da execução

- `main`: `c097d533c6cbf9676f258ba469b79b547ed6b70f`;
- `production`: `ff7c27c75bd5d7dc647a95b879ab1ed3a2c36bf1`;
- 9º A permanece bloqueado para R2.1 até conclusão desta calibração e decisão subsequente.
