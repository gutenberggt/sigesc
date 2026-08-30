# SIGESC — Release GitHub-only em produção

## Objetivo

O GitHub é a estação de governança do release e o Coolify é o único proprietário da mutação do runtime Docker/Traefik.

A arquitetura separa deliberadamente integração de código e publicação:

```text
feature branch -> PR -> CI -> main
                         |
                         +-- não publica produção

workflow_dispatch protegido
        |
        +-- promove o SHA exato de main para production
                         |
                         +-- Coolify Auto Deploy observa production
                                      |
                                      +-- build/deploy nativo
                                      +-- health/proveniência
```

## Motivo da arquitetura

O primeiro workflow GitHub-only, instalado no PR #241, tentou operar `docker compose` diretamente no workspace gerado pelo Coolify. O run `33316921122` falhou porque o Compose gerado depende do contexto de runtime do próprio Coolify (`COOLIFY_RESOURCE_UUID`). O post-failure forensic run `33317644401` também confirmou que o Coolify estava auto-publicando pushes da `main` e que os três containers do stack foram recriados pelo deploy nativo.

Conclusão: GitHub não deve competir com o Coolify executando Compose por SSH. O deploy direto por SSH foi descontinuado.

## Branches

### `main`

Fonte integrada e revisada. Merge em `main` não deve publicar produção.

### `production`

Ponteiro de release. Só deve avançar por meio do workflow protegido `SIGESC Production Release`.

A branch `production` foi inicializada no SHA:

```text
2241e9740195098d21426018f4b9973d668c2df0
```

O workflow só permite avanço fast-forward de `production` para o SHA exato que ainda seja o HEAD atual de `main`.

## Configuração necessária no Coolify

O recurso SIGESC deve usar:

- Git branch: `production`;
- Auto Deploy: habilitado somente depois da troca de branch;
- Include Source Commit in Build: habilitado;
- Docker Compose: `docker-compose.coolify.yml`.

Enquanto o recurso observar `main`, Auto Deploy deve permanecer desligado.

## Proveniência

O Coolify fornece `SOURCE_COMMIT` ao build quando `Include Source Commit in Build` está habilitado. O Compose converte esse valor em `SIGESC_GIT_SHA` para backend e frontend.

Os Dockerfiles registram:

```text
org.opencontainers.image.revision=<40-char-git-sha>
```

O frontend também publica:

```text
/version.json
```

com:

```json
{"git_sha":"<40-char-git-sha>"}
```

Um release só é classificado `APPLIED` se o SHA público e os labels das imagens em execução coincidirem exatamente com o SHA promovido.

## Workflow de release

`.github/workflows/sigesc-production-deploy.yml` possui o nome visível `SIGESC Production Release` e é exclusivamente `workflow_dispatch`.

O disparo exige:

```text
PROMOTE_SIGESC_MAIN_TO_PRODUCTION
```

O job usa o Environment `production` e executa, em ordem:

1. valida confirmação, branch e SHA;
2. exige que o SHA continue sendo HEAD de `main`;
3. exige `CI - Build & Lint` e demais workflows de push verdes;
4. lê o SHA atual de `production`;
5. exige relação fast-forward entre `production` e o target;
6. captura, somente leitura, o volume persistente Mongo `/data/db`;
7. move `production` para o SHA target pela API do GitHub;
8. aguarda o Coolify publicar `/version.json` com o SHA exato;
9. exige `/api/health` saudável e `database=connected`;
10. inspeciona o runtime por SSH somente leitura;
11. exige labels de backend/frontend iguais ao SHA target;
12. exige continuidade do mesmo volume persistente Mongo;
13. em sucesso, classifica `APPLIED`;
14. em falha após a promoção, retorna `production` ao SHA anterior e aguarda o Coolify restaurar a versão anterior;
15. classifica `SAFE_ROLLBACK` ou hard stop se o rollback não puder ser comprovado.

## MongoDB

O workflow de release não executa comandos Mongo e não faz migração explícita.

Como o SIGESC atual é uma aplicação Docker Compose única, o deploy nativo do Coolify pode recriar o container Mongo junto com o stack. Portanto, o contrato correto é:

```text
EXPLICIT_DATABASE_MIGRATION=NO
MONGO_PERSISTENT_VOLUME_REQUIRED=YES
MONGO_VOLUME_CONTINUITY=PASS
PUBLIC_DATABASE=connected
```

Não se usa mais a identidade do container Mongo como invariante. A invariante de dados é o volume persistente montado em `/data/db`, além do health e conectividade do banco.

Uma futura separação do Mongo para um recurso stateful independente pode eliminar também a recriação do container, mas isso é uma mudança arquitetural distinta e não faz parte deste fluxo de release.

## Rollback

O rollback ocorre no nível da fonte, não no nível de image IDs locais:

```text
production -> SHA anterior
            |
            +-- Coolify Auto Deploy
            +-- /version.json = SHA anterior
            +-- API healthy
            +-- database connected
```

A volta de `production` é restrita ao SHA capturado imediatamente antes da promoção do mesmo run.

Classificações:

- `APPLIED`: SHA target publicado e runtime verificado;
- `SAFE_ROLLBACK`: branch e runtime anterior restaurados e comprovados;
- `AMBIGUOUS_OR_ROLLBACK_INCOMPLETE`: hard stop, sem rerun automático.

## Evidência

Cada execução produz artifact:

```text
sigesc-production-release-<run-id>-<sha>
```

com retenção de 90 dias e evidências de gate, promoção, smoke público, runtime, rollback quando aplicável e classificação final.

## Fronteira de autorização

Merge de código, promoção da branch `production` e mutação do runtime são fronteiras distintas.

A existência do workflow não autoriza release. Cada execução de produção exige autorização explícita para o SHA e o comportamento de rollback correspondente.
