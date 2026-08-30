# P0-F7.9D7.6.4 — GitHub-only production pipeline

Data: 2026-08-30

## Objetivo

Eliminar a cópia local `C:\SIGESC` do fluxo operacional normal. GitHub passa a ser a estação principal para código, PR, CI, materialização do executor, gate de produção, captura de recibo, validação e retenção de evidências.

## Escopo exato

A D7.6.4 continua vinculada à cadeia já autorizada:

- código D7.6.3: `a627189a5cd2b38297260a0d4360b64e17441221`;
- manifesto D7.5: `89e0f72d97f7cfa8b2d4b5dd7b5d35a01376a813d69d46f5bce7fa9c11440fcc`;
- plano D7.3.1: `b6cfcfd3fec964fe58ebdcc7aea6e9fe1953207d7178da35b7e1bd4dea8c39fb`;
- preflight D7.4: `b835f5393e035dee0703f1aa0ae0dd52c779b81d5f73b8c05d0adff3fbcedc9e`;
- executor D7.6.3 materializado e verificado: `aa61676f8e3841436b34d8f345d235304380eda866984319b815ceec638e4e5b`;
- operações: exatamente 23;
- estratégia: `CAS_WITH_COMPENSATING_ROLLBACK_REQUIRED`;
- hard delete: proibido.

## Arquitetura operacional

O workflow `P0-F7.9D7.6.4 GitHub-only Production Execution` é acionado apenas manualmente por `workflow_dispatch` e utiliza o GitHub Environment `production`.

O job:

1. exige confirmação textual exata;
2. faz checkout do commit D7.6.3 fixado;
3. restaura o manifesto selado a partir de secret GitHub;
4. valida a cadeia de SHAs e as 23 operações;
5. materializa novamente o executor pelo builder D7.6.3;
6. exige SHA do executor exatamente igual a `aa61676...e4e5b`;
7. configura SSH com chave e `known_hosts` fixados em secrets;
8. executa o writer contra o container Mongo de produção;
9. sempre grava stdout/stderr em arquivo novo antes de interpretar o resultado;
10. exige marcador exato `P0F79D76_EXECUTION_RECEIPT=`;
11. valida o recibo offline;
12. publica evidências como GitHub Actions artifact por 90 dias.

Não existe trigger automático por `push`, PR ou agenda para a execução de produção.

## Secrets necessários — configuração única

No Environment GitHub `production` devem existir:

- `P0F79D75_MANIFEST_B64`
- `SIGESC_PROD_HOST`
- `SIGESC_PROD_USER`
- `SIGESC_PROD_SSH_PRIVATE_KEY`
- `SIGESC_PROD_SSH_KNOWN_HOSTS`
- `SIGESC_PROD_MONGO_CONTAINER`

É recomendado configurar `production` com aprovação humana obrigatória.

## Estado da cópia local

Depois da configuração inicial dos secrets, a cópia local deixa de ser requisito para as próximas fases. O servidor de produção também não precisa manter clone Git para a execução da remediação; GitHub Actions transmite apenas o executor verificado ao `mongosh` via SSH.

## Política de falha

- ausência do recibo: parar e não reexecutar automaticamente;
- `SAFE_ROLLBACK`: evidência preservada, remediação não aplicada;
- `ROLLBACK_INCOMPLETE`: incidente crítico, sem nova execução;
- `APPLIED`: somente válido com 23 forward writes, zero rollback e validação offline PASS.
