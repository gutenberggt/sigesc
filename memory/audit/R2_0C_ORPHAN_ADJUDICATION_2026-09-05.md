# R2.0c — Adjudicação da Data Órfã — 9º A — 30/04/2026

Tracking: #447 → #439 → #438 → #418. Trilha investigativa: #357.

## Baseline

- R2.0b manifest: `87b012a4bcd63b1072425dead3690d117c1975bceaec7cb8ce41fac7986688c4`.
- 9º B: 33 conteúdos-fonte em fevereiro–abril/2026.
- 9º A: 34 datas de frequência atribuíveis a Luiz no mesmo período.
- 33 itens pareados por ordinal global.
- única data-alvo sem par: `2026-04-30`.

## Objetivo

Adjudicar read-only a natureza da data órfã, sem inventar conteúdo e sem usar ausência de lançamento como prova.

Hipóteses testadas:
1. duplicidade/ambiguidade objetiva de frequência;
2. sessão adicional sustentada por metadados de carga/sessão;
3. deslocamento de fronteira do período, via próximo conteúdo-fonte cronológico do 9º B em janela curta de maio.

## Boundary

- nenhuma escrita em produção;
- `attendance.records` não lido;
- sem estudantes/matrículas/notas;
- plaintext pedagógico nunca publicado;
- IDs técnicos nunca publicados;
- lookahead de maio apenas diagnóstico;
- nenhuma extensão automática do período de apply;
- sem deploy.

## Taxonomia

- `ORPHAN_STATE_CHANGED_REVIEW_REQUIRED`
- `ORPHAN_ATTENDANCE_DUPLICATE_OR_AMBIGUOUS`
- `ORPHAN_BOUNDARY_SHIFT_NEXT_SOURCE_AVAILABLE`
- `ORPHAN_EXTRA_SESSION_METADATA_SUPPORTED`
- `ORPHAN_ADJUDICATION_INCONCLUSIVE`

O resultado da execução owner-gated será anexado às issues; nenhuma escrita acadêmica faz parte desta microfase.
