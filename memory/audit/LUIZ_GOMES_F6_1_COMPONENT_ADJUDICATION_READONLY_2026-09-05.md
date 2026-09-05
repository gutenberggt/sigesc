# LUIZ-GOMES-F6.1 — adjudicação do componente histórico

**Data:** 5 de setembro de 2026  
**Tracking:** #357  
**Escopo:** Luiz Gomes dos Santos — Matemática — 8º ANO A e 9º ANO A — fevereiro a abril de 2026.

## Evidência precedente

A F6 confirmou que os conteúdos históricos não foram simplesmente perdidos:

- 8º ANO A: 111 `learning_objects` em fev–abr (23/47/41);
- 9º ANO A: 98 `learning_objects` em fev–abr (23/40/35);
- estão nas identidades atuais das turmas;
- porém usam componentes catalogados diferentes das quatro identidades hoje chamadas `Matemática`;
- `content_entries` permanece vazio no período;
- os registros são legados sem atribuição direta ao Luiz (`UNATTRIBUTED`).

Classificação F6 para os dois pares: `HISTORICAL_CONTENT_COURSE_BINDING_ANOMALY_CONFIRMED`.

## Objetivo

Identificar, sem ler conteúdo pedagógico, qual componente ou conjunto de componentes recebeu os registros de fev–abr e avaliar se existe suporte estrutural para vinculá-los ao histórico docente do Luiz.

A adjudicação cruza:

1. nome atual e fingerprint do componente catalogado de cada grupo;
2. contagem e datas por mês;
3. `teacher_assignments` de Luiz em 2026, inclusive inativos;
4. `teacher_class_assignments` históricos/atuais, incluindo validade e flag de exclusão;
5. coincidência entre datas dos conteúdos candidatos e datas de frequência de Matemática atribuíveis ao Luiz.

Coincidência temporal é apenas evidência de priorização, nunca prova isolada de autoria.

## Boundary

- MongoDB somente leitura;
- sem HTTP;
- frequência consultada somente por metadados; `attendance.records` nunca projetado;
- sem texto pedagógico;
- sem estudantes, matrículas, notas ou PII;
- IDs técnicos apenas como fingerprints;
- nenhuma mutação, backfill, remapeamento, migração ou deploy;
- MT-1, Transferência Institucional e AEE intocados.

## Taxonomia

- `UNIQUE_OTHER_COMPONENT_WITH_LUIZ_ASSIGNMENT_HISTORY`: há exatamente um componente candidato com vínculo histórico do Luiz.
- `MULTIPLE_OTHER_COMPONENTS_WITH_LUIZ_ASSIGNMENT_HISTORY`: mais de um candidato possui vínculo histórico; requer nova adjudicação.
- `LEGACY_TEACHER_ASSIGNMENT_TO_OTHER_COMPONENT_CONFIRMED`: candidato aparece em `teacher_assignments` do Luiz.
- `DVD_ASSIGNMENT_TO_OTHER_COMPONENT_CONFIRMED`: candidato aparece em `teacher_class_assignments` do Luiz.
- `UNIQUE_MAX_DATE_OVERLAP_CANDIDATE`: um candidato possui maior interseção de datas com a frequência de Matemática.
- `TIED_DATE_OVERLAP_CANDIDATES`: maior interseção temporal empatada.
- `NO_DIRECT_LUIZ_ASSIGNMENT_HISTORY_ON_CANDIDATES`: nenhum candidato tem vínculo docente histórico direto; não autoriza remapeamento.

## Regra de decisão

Nenhum remapeamento é autorizado por esta etapa. Uma futura correção somente poderá ser planejada se a combinação de vínculo histórico e temporalidade produzir um alvo inequívoco. O plano posterior deverá ser cirúrgico, idempotente, com preflight, pós-check e rollback quando aplicável.
