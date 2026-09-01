# ANA-LUCIA-F2 — dry-run de saneamento canônico dos 17 pares

## Contexto

A ANA-LUCIA-F1 confirmou em produção, sem mutação, que os 17 pares de Ana Lucia
Faria Pinto/2026 existem de forma unívoca no legado, mas não possuem diário
canônico atual autorizado. Em parte deles há `learning_objects` e/ou frequência
legada sem `assignment_id`; em outros não há registros pedagógicos persistidos.

A F2 é a etapa intermediária obrigatória antes de qualquer saneamento: ela não
corrige dados. Ela transforma o diagnóstico em um plano determinístico e
fail-closed.

## SSoT da decisão canônica

A F2 **não cria uma segunda regra de reconciliação DVD**. Ela executa o planner
homologado `p0_250_f2_9a_global_dvd_reconciliation_plan.py` e captura sua decisão
interna para as 17 chaves legadas exatas da professora.

Assim, `PLAN_CREATE_CANONICAL_ASSIGNMENT` só é aceito quando a F2.9A já provar:
identidade unívoca, papel professor, tenant/escola compatíveis, componente exato,
ausência de drift/duplicidade e um envelope canônico único derivado de vínculos
DVD irmãos válidos. `NO_CANONICAL_TEMPLATE`, ambiguidade ou qualquer drift
continua em `REQUIRES_REVIEW`.

O blob do planner é pinado. Qualquer alteração da SSoT exige nova revisão da F2.

## Planejamento dos registros legados

O manifesto privado da F2 identifica registros por ID somente para tornar uma
fase futura auditável. Nenhum ID é publicado no relatório público.

### Conteúdo (`learning_objects`)

Sem vínculo canônico derivável, o registro fica `BLOCKED_BY_CANONICAL_BINDING`.
Com vínculo derivável:

- data `<= valid_from`: `KEEP_LEGACY_READ_ONLY_BRIDGE`; o history bridge atual já
  preserva o legado como leitura histórica e uma cópia automática seria
  desnecessária/arriscaria duplicação;
- data `> valid_from`: `PLAN_CONTENT_CANONICAL_BACKFILL`; é candidato a futura
  cópia para `content_entries`, porque o bridge não projeta legado posterior ao
  cutover;
- se já existir conteúdo canônico na mesma data: `REVIEW_CANONICAL_CONTENT_OVERLAP`.

A F2 não lê o texto pedagógico. Portanto ela só sela a identidade estrutural do
candidato; um apply futuro deverá reler/validar o payload sob autorização própria.

### Frequência legada sem `assignment_id`

A F2 preserva o contrato vigente do DVD histórico:

- data `< valid_from`: `KEEP_LEGACY_HISTORICAL_ACCESS`; o documento legado deve
  permanecer sem `assignment_id`, usando o vínculo DVD apenas como prova de
  autorização histórica;
- data `>= valid_from`: `REVIEW_POST_CUTOVER_UNASSIGNED_ATTENDANCE`; a F2 não
  retroatribui um assignment a um documento já persistido, pois isso alteraria
  proveniência e snapshots canônicos.

Não há leitura de `attendance.records` nesta fase.

## Manifesto privado e seal

O artifact privado contém, para cada par:

- chave legada exata;
- decisão F2.9A e motivos de revisão;
- target `teacher_class_assignment` quando derivável;
- IDs/datas dos registros legados de conteúdo e frequência e sua classificação;
- contagem de conteúdo canônico já existente.

O bundle recebe SHA-256 determinístico. O snapshot público emite apenas o hash,
contagens, nomes de turma/componente/escola, envelope canônico não sensível e
classificações.

## Boundary de produção

O workflow somente executa com issue criada pelo owner, SHA exato de `main` e
confirmação literal. Ele usa MongoDB apenas para leitura e não chama HTTP da
aplicação.

A F2 declara e valida:

- `database_mutation=false`;
- `production_writes=false`;
- `mongo_reads_only=true`;
- `attendance_records_read=false`;
- `pedagogical_text_read=false`;
- `student_data_read=false`;
- `automatic_apply_authorized=false`.

## O que a F2 não faz

A F2 não cria `teacher_class_assignments`, não copia `learning_objects`, não
altera frequência, não adiciona `assignment_id` retroativamente, não muda
`valid_from`, não corrige dados e não toca Transferência Institucional ou MT-1.

Uma eventual ANA-LUCIA-F3 deverá partir do manifesto F2, separar operações
realmente seguras dos itens em revisão e exigir autorização explícita nova antes
de qualquer escrita, com preflight de drift, seal, CAS/idempotência, pós-check e
rollback compensatório quando tecnicamente possível.
