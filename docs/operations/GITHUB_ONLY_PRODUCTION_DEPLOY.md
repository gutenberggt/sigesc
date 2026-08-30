# SIGESC — Deploy GitHub-only em produção

## Objetivo

Eliminar dependência de clone local ou `git pull` manual para publicar o SIGESC. O GitHub passa a ser a estação operacional do deploy; o Coolify continua proprietário do runtime Docker/Traefik e do `docker-compose.yaml` gerado.

## Topologia confirmada

Discovery run `33315793314` confirmou, em modo somente leitura:

- Compose project: `bww8wogkcs0sws8sc80s4k4c`;
- working dir: `/data/coolify/applications/bww8wogkcs0sws8sc80s4k4c`;
- Compose efetivo: `/data/coolify/applications/bww8wogkcs0sws8sc80s4k4c/docker-compose.yaml`;
- serviços: `mongo`, `backend`, `frontend`;
- workspace Coolify não é repositório Git;
- Mongo, backend e frontend estavam `running/healthy`;
- API pública `/api/health` retornou `healthy` com banco conectado;
- frontend público respondeu com sucesso.

O artifact da descoberta é `sigesc-production-topology-33315793314`, digest `sha256:ed7efe4267f6ad3efe813092d3be5c8aee2d0a32bb1fd9be36f1a353a8bd0106`.

## Contrato operacional

O workflow `.github/workflows/sigesc-production-deploy.yml` é `workflow_dispatch` e usa o Environment `production`. O disparo exige a confirmação literal `DEPLOY_SIGESC_PRODUCTION_MAIN` e só aceita a branch `main`.

O SHA do evento é o único alvo do deploy. Antes de qualquer acesso remoto, o workflow confirma que:

1. o SHA ainda é o HEAD atual de `main`;
2. `CI - Build & Lint` do push correspondente terminou com sucesso;
3. todos os workflows de `push` encontrados para o SHA terminaram sem conclusão de falha;
4. a topologia descoberta em produção ainda coincide com a topologia selada.

Qualquer drift bloqueia o deploy antes da reconstrução dos containers.

## Estratégia de release

O workspace gerenciado pelo Coolify não é convertido em clone Git e seu `docker-compose.yaml` não é editado.

O Actions cria um tarball do checkout exato, calcula SHA-256, transfere-o por SSH com host key pinada e o extrai em:

```text
/data/coolify/applications/<project>/.github-deploy/releases/<git-sha>-<run-id>/
```

O tarball remoto precisa ter o mesmo SHA-256 calculado pelo runner.

O executor cria um Compose override separado em `.github-deploy/overrides/`. Esse override altera somente o `build.context` de `backend` e `frontend` para o release imutável e injeta `SIGESC_GIT_SHA` como build arg. As variáveis, volumes, networks, labels e demais atributos continuam vindo do Compose produzido pelo Coolify.

## Proveniência

As imagens backend e frontend recebem:

```text
org.opencontainers.image.revision=<40-char-git-sha>
```

O executor exige que o label das imagens recém-construídas e dos containers efetivamente em execução seja exatamente igual ao SHA do workflow.

O frontend também publica:

```text
/version.json
```

com o formato:

```json
{"git_sha":"<40-char-git-sha>"}
```

O smoke público só passa se esse SHA for idêntico ao SHA implantado.

## MongoDB

O deploy de aplicação não executa migração explícita e não contém `mongosh`, `mongoimport` ou writers de banco.

O serviço `mongo` nunca é passado para `docker compose build`, `docker compose up`, restart ou recreate. O executor captura o container ID do Mongo antes do deploy e exige o mesmo ID depois do deploy e depois de qualquer rollback.

Observação: o startup normal do backend continua executando as rotinas idempotentes já existentes na aplicação. Portanto, o contrato é `EXPLICIT_DATABASE_MIGRATION=NO`, e não uma alegação de que o processo Python jamais possa executar seu startup existente.

## Sequência de deploy

1. validar dispatch, SHA e CI;
2. validar SSH pinado;
3. redescobrir topologia e barrar drift;
4. transferir release imutável e validar SHA-256;
5. registrar image IDs antigos;
6. validar Compose base + override;
7. construir apenas backend/frontend;
8. validar labels de proveniência antes da troca;
9. recriar backend e aguardar `healthy`;
10. recriar frontend e aguardar `healthy`;
11. comprovar que o Mongo não mudou;
12. validar labels dos containers em execução;
13. executar smoke público da API, banco, frontend e `/version.json`;
14. finalizar recibo e armazenar evidência por 90 dias.

## Rollback

Os image IDs anteriores de backend e frontend são registrados antes do build.

Se ocorrer falha depois do início da mutação do runtime, o executor retagueia os image IDs anteriores e recria somente backend/frontend. Se o deploy remoto concluir mas o smoke público falhar, o próprio workflow solicita o rollback usando o recibo remoto e revalida a disponibilidade pública.

Classificações principais:

- `APPLIED`: deploy, health, SHA smoke e finalização passaram;
- `SAFE_ROLLBACK`: a versão nova não permaneceu aplicada e o runtime anterior foi restaurado;
- `ROLLBACK_INCOMPLETE` ou estado ambíguo: hard stop; não executar rerun automático.

## Evidência

Cada run envia artifact `sigesc-production-deploy-<run-id>-<sha>` com retenção de 90 dias, incluindo gate de GitHub, topologia pré-deploy, SHA-256 do release, saída do executor, health público, versão pública e classificação final.

## Limites de autorização

Merge de código e autorização de deploy são fronteiras distintas. O workflow pode estar presente em `main` sem executar nada. O primeiro deploy e qualquer deploy futuro continuam exigindo um `workflow_dispatch` explícito no Environment `production`.
