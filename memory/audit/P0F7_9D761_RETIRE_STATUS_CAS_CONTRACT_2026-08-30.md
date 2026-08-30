# P0-F7.9D7.6.1 — Retire Status CAS Contract Hotfix

Data: 2026-08-30

## Incidente

A materialização local do executor D7.6 falhou de forma segura com:

`P0F7_9D76_RETIRE_STATUS_CAS_INVALID`

Nenhum arquivo executor foi criado e nenhuma escrita em produção ocorreu.

## Causa raiz

O plano revisado D7.3 e o manifesto D7.5 preservam o valor exato observado de `status` no `cas_expected` da operação `RETIRE_DUPLICATE_ASSIGNMENT` (`active` ou `ativo`).

O validador inicial D7.6, porém, exigia exclusivamente o token sintético `ativo_or_active`, usado em fixtures e em algumas operações históricas. Isso criou uma incompatibilidade entre o contrato real selado e o validador de materialização.

## Correção

A D7.6.1 adiciona uma camada mínima de compatibilidade sobre o builder D7.6:

- aceita somente `active` ou `ativo` como status exato da operação de aposentadoria, além do alias legado já suportado;
- exige que `rollback_set_fields.status` seja exatamente o mesmo status ativo quando o manifesto usa valor exato;
- preserva o valor exato no `cas_expected` materializado;
- delega todos os demais invariantes e toda a geração do writer ao builder D7.6 já revisado;
- não altera o manifesto D7.5, o SHA autorizado, a contagem de 23 operações ou a estratégia de execução;
- não adiciona acesso a rede ou banco ao builder local;
- não executa produção.

## Cadeia autorizada preservada

- D7.5 manifesto: `89e0f72d97f7cfa8b2d4b5dd7b5d35a01376a813d69d46f5bce7fa9c11440fcc`
- D7.3.1 plano revisado: `b6cfcfd3fec964fe58ebdcc7aea6e9fe1953207d7178da35b7e1bd4dea8c39fb`
- D7.4 preflight: `b835f5393e035dee0703f1aa0ae0dd52c779b81d5f73b8c05d0adff3fbcedc9e`
- operações: 23
- estratégia: `CAS_WITH_COMPENSATING_ROLLBACK_REQUIRED`
- hard delete: proibido

## Segurança

O hotfix torna o CAS de aposentadoria mais fiel ao snapshot selado: quando o manifesto diz `active`, o writer exige `active`; quando diz `ativo`, exige `ativo`. Não há ampliação silenciosa para ambos os valores nesses casos.

Qualquer status não ativo continua fail-closed. Qualquer divergência entre status esperado e status de rollback também falha antes da materialização do executor.

## Observação operacional

Uma verificação PowerShell do SHA só pode ser considerada válida depois de confirmar explicitamente que os arquivos `Executor` e `Metadata` existem. Comparar duas variáveis vazias pode produzir um falso positivo; por isso a execução operacional posterior deve usar guards `Test-Path` antes de calcular ou comparar hashes.
