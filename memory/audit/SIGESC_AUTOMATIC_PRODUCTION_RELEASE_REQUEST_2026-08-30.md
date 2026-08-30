# SIGESC — Solicitação automática de release de produção

Data: 2026-08-30

## Objetivo

Eliminar a necessidade de o operador entrar manualmente em **GitHub Actions → SIGESC Production Release → Run workflow** depois de uma autorização explícita de produção, preservando o modelo GitHub-only, o Coolify como único mutador do runtime e os gates fail-closed já existentes.

## Modelo operacional

O workflow `SIGESC Production Release` mantém `workflow_dispatch` como fallback manual e passa também a aceitar um evento `issues: opened` estritamente controlado.

Após uma autorização explícita do proprietário para um par exato `production baseline -> main target`, a automação pode criar no GitHub um issue com o título:

`[SIGESC-PROD-RELEASE] <TARGET_SHA>`

E corpo canônico:

```text
SIGESC_PRODUCTION_RELEASE_REQUEST=AUTHORIZED
CONFIRMATION=PROMOTE_SIGESC_MAIN_TO_PRODUCTION
TARGET_SHA=<40-hex>
EXPECTED_PRODUCTION_SHA=<40-hex>
REQUEST_ORIGIN=CHATGPT_EXPLICIT_AUTHORIZATION
```

Esse issue é o gatilho auditável do release. Nenhum merge em `main` continua publicando produção por si só.

## Controles fail-closed

O workflow só aceita a solicitação automática quando:

1. o evento é `issues/opened`;
2. o criador do issue é o `github.repository_owner`;
3. o título corresponde exatamente ao `TARGET_SHA` declarado;
4. `SIGESC_PRODUCTION_RELEASE_REQUEST=AUTHORIZED`;
5. a confirmação é exatamente `PROMOTE_SIGESC_MAIN_TO_PRODUCTION`;
6. `TARGET_SHA` e `EXPECTED_PRODUCTION_SHA` possuem exatamente 40 caracteres hexadecimais minúsculos;
7. `main` continua exatamente no `TARGET_SHA`;
8. `production` continua exatamente no `EXPECTED_PRODUCTION_SHA`;
9. a promoção é fast-forwardable;
10. os workflows de `push` do target estão concluídos e verdes, incluindo `CI - Build & Lint`.

Se `main` ou `production` mudarem depois da autorização, o workflow falha antes da promoção.

## Runtime

Nenhuma mudança foi feita no modelo de execução:

- GitHub altera somente o ponteiro da branch `production`;
- Coolify continua sendo o único mutador do runtime;
- não há `docker compose`, `docker build`, `docker restart`, `mongosh` ou migração explícita de banco no workflow;
- o MongoDB deve permanecer saudável e com continuidade do mesmo volume persistente `/data/db`;
- backend e frontend devem expor a proveniência do `TARGET_SHA`;
- API pública deve responder `healthy` e `database=connected`.

## Rollback

Se o smoke público ou a verificação de runtime falhar depois da promoção, a branch `production` retorna ao SHA anterior e o Coolify executa o rollback nativo. O workflow não se reroda automaticamente em caso de falha.

## Evidência

O artifact de release passa para `SIGESC_PRODUCTION_RELEASE_EVIDENCE_V3` e registra também:

- `REQUEST_MODE`;
- `RELEASE_REQUEST_ISSUE`;
- `TARGET_SHA`;
- `EXPECTED_PRODUCTION_SHA`;
- `PREVIOUS_PRODUCTION_SHA`;
- outcomes de promoção, smoke, runtime e rollback.

Quando a solicitação automática termina em `APPLIED` ou `SAFE_ROLLBACK`, o workflow comenta o resultado no issue e o fecha. Em estado ambíguo/rollback incompleto, registra o resultado e mantém o issue aberto para investigação humana.

## Regra de governança

**Automático não significa sem autorização.** O release continua exigindo autorização explícita para o SHA exato e baseline exato. O que deixa de existir é somente o clique operacional no GitHub Actions após essa autorização.
