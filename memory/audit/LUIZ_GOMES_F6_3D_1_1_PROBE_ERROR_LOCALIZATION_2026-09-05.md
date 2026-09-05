# LUIZ-GOMES-F6.3d.1.1 → F6.3d.2 — resolução do ator histórico

Data: 2026-09-05  
Tracking: #357

## Evidência herdada

A F6.3d.1 selecionou um único grupo coerente de 26 arquivos BSON de 18/08/2026, fingerprint `d59c7569d33c7ffa`, com proveniência limitada a `structural_only_ad_hoc_bson_dump`. O restore foi feito exclusivamente em Mongo temporário isolado (`--network none`, zero portas, source read-only), sem tocar produção.

A F6.3d.1.1 localizou o bloqueio do probe anterior como `TEACHER_USER_MATCHES:0`: a fotografia histórica não oferece a identidade do Luiz pelo mesmo lookup nominal usado no estado atual. Esse resultado é operacional, não uma conclusão de ausência de conteúdo.

## Objetivo F6.3d.2

Resolver a identidade histórica do ator **sem consultar `users`** e testar 8º ANO A / 9º ANO A no mesmo dump de 18/08.

As quatro turmas-controle são:

- 6º ANO A / Matemática;
- 6º ANO B / Matemática;
- 7º ANO A / Matemática;
- 7º ANO B / Matemática.

Esses pares funcionam como assinatura estrutural porque a investigação viva anterior já demonstrou registros de Matemática do Luiz no período fevereiro–abril de 2026 nessas quatro turmas.

## Inferência do ator

A F6.3d.2 usa duas camadas, nesta ordem:

1. **`TEACHER_ASSIGNMENTS_EXACT_CONTROL_UNANIMOUS`** — para cada turma-controle, considera apenas os `course_id` de Matemática efetivamente presentes nos `learning_objects` de fevereiro–abril. Se cada uma das quatro turmas aponta para exatamente um `staff_id` e o mesmo `staff_id` é unânime nas quatro, essa é a identidade histórica estrutural.
2. **`LEARNING_OBJECT_METADATA_FOUR_CLASS_DOMINANT`** — fallback caso os vínculos legados não sejam suficientes. Resolve `recorded_by`, `created_by`, `updated_by`, `teacher_id`, `staff_id` e `assignment_id` para um principal interno; exige suporte nas quatro turmas, cobertura mínima de 80% e ausência de empate no topo.

Nenhum valor bruto da identidade inferida é emitido. O resultado expõe somente tipo da identidade, fonte da inferência, cobertura e contagens.

## Teste dos alvos

Após uma identidade histórica única ser demonstrada, o mesmo principal é usado somente como filtro de leitura em:

- 8º ANO A;
- 9º ANO A;
- período 2026-02-01 até 2026-05-01 exclusivo.

A taxonomia distingue:

- `BSON_20260818_RECOVERY_SOURCE_CONFIRMED` — há conteúdo de Matemática com payload atribuível à identidade histórica;
- `BSON_20260818_LUIZ_ROWS_UNDER_NONMATH_COMPONENT` — há payload do mesmo ator sob outro componente;
- `BSON_20260818_LUIZ_ROWS_WITHOUT_PAYLOAD` — há linhas do ator, mas sem payload recuperável;
- `BSON_20260818_UNATTRIBUTED_MATH_CANDIDATES` — há Matemática com payload sem identidade estrutural atribuível;
- `BSON_20260818_BINDING_PRESENT_CONTENT_ABSENT` — vínculo histórico do mesmo `staff_id` com Matemática existe no alvo, mas conteúdo correspondente não existe;
- `HISTORICAL_ACTOR_ABSENT_FROM_BOTH_TARGETS_20260818` — a identidade foi provada nas quatro turmas-controle, mas não aparece nos dois alvos e não há outra evidência candidata;
- `HISTORICAL_ACTOR_NOT_UNIQUELY_INFERRED` — evidência insuficiente/ambígua; nenhuma conclusão substantiva.

## Boundary

- somente dump BSON de 18/08 já identificado estruturalmente;
- restore em Mongo temporário isolado;
- source mount read-only;
- nenhuma escrita em produção;
- nenhum deploy;
- nenhum ID técnico emitido;
- nenhum texto pedagógico emitido;
- nenhum estudante, matrícula, nota ou `attendance.records` lido;
- o payload pedagógico é reduzido somente a `payload_present` booleano.

Nenhum resultado desta fase autoriza restauração, backfill, remapeamento ou qualquer outra escrita em produção.