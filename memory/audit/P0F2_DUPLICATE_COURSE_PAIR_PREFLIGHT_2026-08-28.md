# P0-F2 — Preflight READ-ONLY de pares duplicados de componentes

Data: 2026-08-28

## Contexto

O P0-F confirmou 3 grupos atuais de `DUPLICATE_COURSE_IDENTITY`, totalizando 6 registros `courses`, todos referenciados em produção. Cada grupo possui histórico de consolidação anterior em que um terceiro ID foi removido e um dos IDs atuais foi mantido.

Grupos confirmados em produção:

- Ciências / `fundamental_anos_finais`
- Geografia / `fundamental_anos_finais`
- História / `fundamental_anos_finais`

O `kept_id` histórico é evidência útil, mas não autoriza automaticamente nova consolidação porque os dois IDs atuais permanecem amplamente referenciados.

## Objetivo

Medir, sem mutação, o risco estrutural de uma futura consolidação entre os IDs atuais de cada grupo.

O auditor P0-F2 deve:

1. reproduzir a identidade nominal do P0-F;
2. recuperar o `kept_id` histórico quando houver candidato único dentro do grupo atual;
3. declarar somente uma direção **hipotética** `source_id -> target_id` para análise;
4. cruzar referências usando `COURSE_REFERENCE_SPECS` como SSoT;
5. medir sobreposição de escopos lógicos por coleção;
6. detectar documentos que já contenham ambos os IDs;
7. preservar evidência completa em manifesto determinístico;
8. nunca declarar consolidação automaticamente segura.

## Semântica dos sinais

`shared_scope_count` indica que os dois IDs aparecem no mesmo escopo estrutural, por exemplo professor+turma+ano ou estudante+turma+período. É apenas sinal de risco de colisão; não prova identidade material dos registros.

`shared_document_count` indica que um mesmo documento referencia os dois IDs. Também é somente evidência forense.

## Classificações

- `NO_UNIQUE_HISTORICAL_KEPT_BLOCKED`
- `HISTORICAL_KEPT_WITH_SCOPE_OVERLAP_REQUIRES_REVIEW`
- `HISTORICAL_KEPT_NO_SCOPE_OVERLAP_REQUIRES_REVIEW`

Nenhuma classificação equivale a `SAFE_TO_MERGE`.

## Invariantes

- READ-ONLY;
- sem `--apply` ou `--rollback`;
- sem mutadores MongoDB;
- sem criação, exclusão, desativação ou alteração de `courses`;
- sem remapeamento de referências;
- sem alteração em writers;
- sem alteração em AEE;
- qualquer futuro executor exigirá PR próprio, manifesto selado, backup, rollback, CAS, pós-check e autorização humana separada para escrita em produção.
