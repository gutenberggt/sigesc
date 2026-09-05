# LUIZ-GOMES-F6 — proveniência temporal de conteúdos históricos

**Data:** 5 de setembro de 2026  
**Tracking:** #357  
**Escopo:** Luiz Gomes dos Santos — E M E I E F Jose Pereira Barbosa — Matemática — 8º ANO A e 9º ANO A — fevereiro a abril de 2026.

## Gatilho

Verificação manual no cliente real confirmou que os conteúdos registrados de fevereiro, março e abril de 2026 não aparecem nos diários de Matemática do 8º ANO A e 9º ANO A.

A releitura da F2 (`run 33803590364`) mostrou que, na identidade consultada pelo endpoint legado:

- 8º ANO A: fev=0, mar=0, abr=0; primeiro `learning_object` em 04/05/2026;
- 9º ANO A: fev=0, mar=0, abr=0; primeiro `learning_object` em 04/05/2026;
- professor e gestão devolvem as mesmas cardinalidades;
- frequência existe para ambos desde fevereiro.

A releitura da F1 (`run 33802279915`) mostrou ainda que as três outras identidades catalogadas de mesmo nome `Matemática` no tenant têm zero conteúdo nesses dois pares. Assim, a hipótese simples de outro `course_id` catalogado não explica o período ausente.

## Pergunta F6

Há metadados de conteúdo de fevereiro–abril/2026:

1. sob outra identidade de turma com o mesmo nome na mesma escola/tenant;
2. na turma atual, mas com `course_id/component_id` alternativo, ausente, não catalogado ou divergente;
3. em `content_entries` em vez de `learning_objects`;
4. atribuíveis ao Luiz, porém apontando para uma identidade de turma já não resolvível pelo catálogo atual;
5. ou os registros não estão presentes nos stores vivos auditados?

## Boundary

A F6:

- lê somente metadados de `learning_objects` e `content_entries`;
- não projeta campos pedagógicos;
- não lê `attendance.records`;
- não lê estudantes, matrículas, notas ou PII;
- não usa HTTP;
- não emite IDs técnicos brutos: apenas fingerprints;
- não executa insert, update, delete, backfill, remapeamento ou migração;
- não altera MT-1, Transferência Institucional ou AEE.

## Taxonomia

- `CURRENT_PATH_HAS_HISTORICAL_CONTENT`: há registros fev–abr no caminho corrente; investigar divergência de query/data.
- `HISTORICAL_CONTENT_COURSE_BINDING_ANOMALY_CONFIRMED`: turma atual contém registros com referência de componente divergente/ausente/não catalogada.
- `HISTORICAL_CONTENT_CLASS_IDENTITY_SPLIT_CONFIRMED`: registros estão sob outra identidade de turma de mesmo nome.
- `HISTORICAL_CONTENT_IN_CANONICAL_STORE_CONFIRMED`: o período está em `content_entries`.
- `HISTORICAL_CONTENT_POSSIBLE_UNRESOLVED_CLASS_BINDING`: registros atribuíveis ao professor apontam para turma não resolvível no catálogo atual.
- `HISTORICAL_CONTENT_NOT_FOUND_LIVE_STORES`: nenhum metadado do período foi encontrado nos stores vivos e será necessária investigação de histórico/auditoria/backup, ainda read-only.

## Governança

O runtime em produção exige issue owner-only, SHA exato de `main`, SHA esperado de `production` e tracking #357 aberto. Mesmo uma classificação conclusiva de identidade **não autoriza remapeamento**: qualquer saneamento posterior deve nascer como plano cirúrgico separado, com pré-check, idempotência/CAS, pós-check e rollback quando aplicável.
