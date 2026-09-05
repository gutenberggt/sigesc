# LUIZ-GOMES-F6.2 — Linhagem histórica conclusiva (read-only)

Data: 2026-09-05
Tracking: #357

## Contexto

A F6 confirmou 111 `learning_objects` no 8º ANO A e 98 no 9º ANO A em fevereiro–abril/2026, todos fora da identidade atual de Matemática. A F6.1 mostrou que esses registros se distribuem entre componentes hoje chamados Língua Portuguesa, História, Arte etc. e que não há vínculo histórico direto do Luiz nesses componentes.

Isso ainda não prova que os 209 registros são Matemática. Eles podem ser conteúdos legítimos de outros professores, enquanto os registros de Matemática do Luiz foram deslocados para outra turma/componente, tiveram a identidade alterada ou deixaram de existir no store vivo.

## Objetivo da F6.2

Tentar uma adjudicação conclusiva por evidência estrutural, sem qualquer mutação:

1. procurar `learning_objects` atribuídos diretamente ao Luiz em fev–abr/2026 **sem filtro prévio de turma/componente**;
2. particionar os 209 candidatos em `LUIZ`, `FOREIGN_ACTOR_PRESENT` e `NO_ACTOR_METADATA`;
3. seguir `copied_from_id` nos dois sentidos;
4. comparar SHA-256 determinístico do payload pedagógico com registros de Matemática atribuídos ao Luiz no 6º A/B e 7º A/B;
5. ler `audit_logs` somente para mudanças de `course_id/class_id` de `learning_objects` e nome/nível de `courses`;
6. reconstruir, quando houver trilha suficiente, o nome histórico do componente na data do registro;
7. confrontar os registros adjudicados com as datas de frequência de Matemática do Luiz no 8º A e 9º A.

## Critério forte de conclusão

`CONCLUSIVE_HISTORICAL_MATH_SET_IDENTIFIED` exige que os registros confirmados cubram **exatamente** todas as datas de frequência de Matemática do período, com **um único registro confirmado por data**.

Um registro individual pode ser confirmado somente por pelo menos uma evidência forte:

- autoria direta do Luiz;
- `copied_from_id` conectando ao conjunto conhecido de Matemática;
- `audit_logs` mostrando transição direta entre o `course_id` candidato e Matemática;
- reconstrução auditável do nome histórico do `course_id` como Matemática naquela data;
- digest pedagógico exato encontrado em pelo menos duas turmas de referência de Matemática do Luiz, sem colisão externa incompatível.

Coincidência de data, sozinha, continua não sendo prova de autoria ou disciplina.

## Boundary

- MongoDB somente leitura;
- nenhum HTTP/login;
- nenhuma leitura de `attendance.records`;
- nenhuma leitura de estudantes, matrículas ou notas;
- `content/observations/methodology/resources` são acessados exclusivamente em memória para cálculo de SHA-256;
- plaintext pedagógico nunca é emitido, persistido no artifact ou comentado no GitHub;
- nenhum ID técnico bruto é emitido; somente fingerprints/digests truncados;
- nenhuma mutação, backfill, remapeamento, merge de identidade, exclusão ou deploy.

## Gate owner-only após merge

Título:

`[LUIZ-GOMES-F6.2-LINEAGE] <TARGET_SHA>`

Body:

```text
LUIZ_GOMES_F6_2_LINEAGE=AUTHORIZED
CONFIRMATION=TRACE_HISTORICAL_MATH_LINEAGE_READ_ONLY
ACADEMIC_YEAR=2026
TRACKING_ISSUE=357
TARGET_SHA=<exact main SHA>
EXPECTED_PRODUCTION_SHA=<exact production SHA>
```

O gate falha fechado se `main`, `production`, owner ou tracking issue divergirem.
