# LUIZ-GOMES-F6.3d.1.1 — localização sanitizada do erro do probe histórico

Data: 2026-09-05
Tracking: #357
Origem: F6.3d.1 / gate #405 / run 33970647876
Status: instrumentação preparada; runtime somente após PR/CI/merge e gate owner-only exact-SHA.

## Evidência herdada

A F6.3d.1 comprovou estruturalmente um único grupo coerente de 26 arquivos BSON, snapshot físico de 18/08/2026, fingerprint `d59c7569d33c7ffa`, spread de mtime 0s e proveniência deliberadamente limitada a `structural_only_ad_hoc_bson_dump`.

No Mongo temporário isolado foram restauradas apenas `users`, `schools`, `classes`, `courses`, `learning_objects`, `staff`, `teacher_assignments` e `audit_logs`. O restore ocorreu com `--network none`, zero portas e source mount read-only. Produção não foi tocada.

A fase terminou `INCONCLUSIVE / BSON_DUMP_PROBE_ERROR` porque o probe não emitiu `LUIZ_GOMES_F6_3C_POINT_JSON`. O marcador terminal preservado foi `F63D1_POINT_PROBE_NO_JSON`. Logo, não existe conclusão negativa sobre conteúdo no snapshot de 18/08.

## Objetivo F6.3d.1.1

Localizar somente em qual validação metadata-only o probe histórico falhou, sem expor stderr/stdout bruto, IDs, caminhos, nomes de documentos, texto pedagógico ou dados estudantis.

A seleção do dump, a allowlist de coleções e o restore isolado permanecem idênticos à F6.3d.1.

## Contrato de erro sanitizado

O stdout/stderr integral do `mongosh` é redirecionado para um arquivo temporário no host. Esse arquivo nunca é enviado ao GitHub e é apagado antes da saída.

Somente os seguintes marcadores podem atravessar a fronteira:

- `TEACHER_USER_MATCHES:<n>`;
- `TEACHER_USER_ID_MISSING`;
- `SCHOOL_MATCHES:<n>`;
- `SCHOOL_ID_MISSING`;
- `CLASS_MATCHES_8A:<n>`;
- `CLASS_MATCHES_9A:<n>`;
- `CLASS_MATCHES_TARGET:<n>`;
- `UNCLASSIFIED_RUNTIME_ERROR`.

Também é emitido apenas o exit code numérico do probe.

Antes de sair por erro, o runner:

1. apaga o arquivo bruto do probe;
2. remove explicitamente o Mongo temporário;
3. marca `PRODUCTION_DATABASE_TOUCHED=NO`;
4. marca `TEMP_RESTORE_NETWORK=none` e `TEMP_RESTORE_PORTS=none`;
5. marca `SOURCE_MOUNT=read_only`;
6. marca `TEMP_CONTAINERS_CLEANED=YES`;
7. marca `PEDAGOGICAL_PLAINTEXT_EMITTED=NO`;
8. marca `RAW_PROBE_OUTPUT_EMITTED=NO`.

O `trap` continua como defesa adicional.

## Taxonomia

Esta fase não altera a taxonomia substantiva:

- falha do probe continua `INCONCLUSIVE / BSON_DUMP_PROBE_ERROR`;
- o novo campo `probe_error_marker` serve somente para orientar o próximo probe de compatibilidade histórica;
- somente um `LUIZ_GOMES_F6_3C_POINT_JSON` tecnicamente válido pode produzir classificação substantiva sobre presença/ausência de conteúdos.

Nenhum resultado desta fase autoriza escrita, restore, backfill, remapeamento ou deploy em produção.