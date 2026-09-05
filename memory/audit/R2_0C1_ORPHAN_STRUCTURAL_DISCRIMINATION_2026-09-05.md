# R2.0c.1 — Discriminação estrutural dos 2 documentos de frequência — 9º A — 30/04/2026

Data de preparação: 2026-09-05.

## Contexto

A R2.0c (#447) reexecutou o manifesto R2.0b e confirmou que a única data-alvo órfã do 9º A permanece `2026-04-30`. No mesmo escopo foram encontrados **2 documentos de frequência de Matemática atribuíveis a Luiz Gomes dos Santos**, levando à classificação `ORPHAN_ATTENDANCE_DUPLICATE_OR_AMBIGUOUS`.

Isso impede qualquer decisão segura de R2.1 para o 9º A antes de distinguir a natureza dos dois documentos.

## Objetivo da R2.0c.1

Determinar exclusivamente por metadados estruturais se os dois documentos são:

- duas sessões legítimas distintas;
- duplicidade estrutural do mesmo lançamento;
- sobreposição legado/canônico;
- conflito estrutural;
- ou evidência insuficiente.

A fase é read-only. Não corrige, exclui, funde nem reatribui frequência.

## Princípio de discriminação

IDs de documento e timestamps não são discriminadores pedagógicos. Portanto:

- `_id` não é lido;
- `id` pode existir apenas internamente para a própria leitura do documento e nunca é publicado;
- diferença de `id`, `created_at` ou `updated_at` não prova duas sessões;
- presença isolada de `assignment_id` em apenas um documento não prova sobreposição legado/canônico;
- diferença de `aula_numero` ou `period`, com ambos os lados explicitamente preenchidos, é evidência semântica de sessões distintas;
- assimetria parcial de metadados de sessão falha fechado como conflito, em vez de ser interpretada como duas aulas.

## Assinaturas

O discriminador calcula três assinaturas separadas e publica apenas hashes SHA-256:

1. **assinatura de negócio** — turma, componente, data, ano, `number_of_classes`, `period`, `aula_numero` e fingerprint privado de observação;
2. **assinatura de sessão** — `number_of_classes`, `period` e `aula_numero`;
3. **assinatura de proveniência** — vetor de autoria, `assignment_id`, modo/finalidade de frequência e presença de marcadores de migração/backfill.

Plaintext de `observations` nunca é emitido.

## Taxonomia

- `ORPHAN_TWO_DISTINCT_SESSIONS_SUPPORTED`
- `ORPHAN_DUPLICATE_ATTENDANCE_SUPPORTED`
- `ORPHAN_LEGACY_CANONICAL_OVERLAP_SUPPORTED`
- `ORPHAN_STRUCTURAL_CONFLICT`
- `ORPHAN_STRUCTURAL_DISCRIMINATION_INCONCLUSIVE`
- `ORPHAN_STATE_CHANGED_REVIEW_REQUIRED`

### Duas sessões legítimas

Só é sustentado quando existe discriminador semântico explícito de sessão, especialmente `aula_numero` ou `period`, preenchido em ambos e com valores diferentes. Diferença apenas técnica não é suficiente.

### Duplicidade

Exige equivalência integral das assinaturas de negócio, sessão e proveniência, igualdade de autoria/assignment e ausência de discriminador legítimo de sessão. A classificação é evidência para revisão; não autoriza exclusão automática.

### Sobreposição legado/canônico

Exige simultaneamente:

- mesma identidade acadêmica;
- assinatura de negócio equivalente;
- autoria compatível;
- assimetria de presença de `assignment_id`;
- assimetria adicional de marcador explícito de legado/migração/backfill.

A presença/ausência de `assignment_id` sozinha é insuficiente.

## Boundary

- Mongo somente leitura;
- nenhuma escrita em produção;
- `attendance.records` não projetado nem lido;
- estudantes não lidos;
- matrículas não lidas;
- notas não lidas;
- `audit_logs` não lido;
- nenhuma alteração em `attendance`;
- nenhuma alteração em conteúdo;
- nenhum ID técnico bruto emitido;
- nenhum plaintext de observação emitido;
- timestamps brutos não emitidos; apenas dia e relações/gaps sanitizados quando disponíveis;
- nenhum deploy;
- **nenhum saneamento automático** faz parte da R2.0c.1.

Qualquer exclusão, fusão ou saneamento de frequência deverá ser uma microfase própria, com prova de estado, rollback, idempotência, auditoria e nova autorização humana explícita.

## Gate futuro

A execução em produção só poderá ocorrer após merge explícitamente autorizado do PR da R2.0c.1 e abertura de gate owner-only/exact-SHA. O gate deverá fixar simultaneamente o SHA de `main` e o SHA esperado de `production`.

Baseline de preparação:
- `main`: `4b142c5cd222f6e0fc6fd5a8bb5016c829d4b27a`
- `production`: `ff7c27c75bd5d7dc647a95b879ab1ed3a2c36bf1`
- tracking: #450 → #439 → #438 → #418.
