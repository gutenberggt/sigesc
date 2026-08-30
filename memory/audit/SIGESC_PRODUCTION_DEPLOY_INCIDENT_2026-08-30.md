# SIGESC — Incidente do primeiro deploy GitHub-only e correção arquitetural

Data: 2026-08-30

## 1. Contexto

O primeiro workflow `SIGESC Production Deploy`, introduzido pelo PR #241, foi criado para publicar o SHA exato de `main` operando backend/frontend diretamente por SSH no workspace gerado pelo Coolify.

Target autorizado:

```text
4e6ff49f89e79d3ae09678c0a2b0094c006abe07
```

Run:

```text
33316921122
```

Conclusão do run:

```text
failure
SIGESC_PRODUCTION_DEPLOY=REMOTE_EXECUTOR_FAILED
```

## 2. Falha primária

Os gates de confirmação, SHA, CI, SSH, topologia e staging passaram. A falha ocorreu dentro do executor remoto antes do smoke público.

O Compose efetivo gerado pelo Coolify depende do contexto de ambiente do próprio Coolify para resolver a rede externa. Fora desse contexto, `COOLIFY_RESOURCE_UUID` não estava definido e o Compose não conseguiu resolver a rede.

Conclusão: o workspace e o Compose gerados pelo Coolify não devem ser operados como um runtime Compose independente por um executor GitHub/SSH concorrente.

## 3. Falha secundária de rollback

O executor havia capturado image IDs anteriores, mas o processo de build reutilizou referências mutáveis `latest`. Quando a falha ocorreu, o rollback não conseguiu retaggear um dos image IDs anteriores e registrou rollback incompleto.

Esse desenho foi considerado inválido para continuidade operacional.

## 4. Evidência do run falho

Artifact:

```text
sigesc-production-deploy-33316921122-4e6ff49f89e79d3ae09678c0a2b0094c006abe07
```

Artifact ID:

```text
9733765668
```

Digest:

```text
sha256:84e8f376a395079281b04b1421ac8397d62ff897e716e4789de49a92100864f5
```

Nenhuma migração explícita de banco foi executada.

## 5. Forense pós-falha

Foi criado o PR #242 com workflow estritamente read-only e executado o run:

```text
33317644401
```

Conclusão:

```text
success
SIGESC_POSTFAILURE_RUNTIME_FORENSIC=PASS
```

Artifact:

```text
sigesc-postfailure-forensic-33317644401
```

Artifact ID:

```text
9733941167
```

Digest:

```text
sha256:c3ec943e9bdbc34e4608236faf25ad8abc87cc20a7b908544fcb6d5b70449453
```

## 6. Estado confirmado pelo forense

No momento do forense:

- Mongo: `running/healthy`;
- backend: `running/healthy`;
- frontend: `running/healthy`;
- API pública: acessível;
- banco: conectado;
- frontend público: acessível;
- rede compartilhada: `bww8wogkcs0sws8sc80s4k4c`.

O forense também mostrou que os três containers foram criados às `2026-08-30T14:40:42Z`, poucos segundos após o merge do PR #242. Isso comprovou que o Coolify estava com Auto Deploy ligado para a branch `main` e recriava o stack em pushes da `main`.

Os labels de proveniência e `/version.json` estavam em `unknown`, porque `SOURCE_COMMIT` ainda não era propagado ao build.

## 7. Causa arquitetural

Havia dois orquestradores tentando controlar o mesmo runtime:

1. Coolify Auto Deploy ligado a `main`;
2. GitHub Actions tentando operar `docker compose` diretamente por SSH.

Esse modelo viola o princípio de single-writer para infraestrutura.

## 8. Decisão definitiva

O Coolify passa a ser o único mutador do runtime.

O GitHub controla apenas a promoção da fonte:

```text
main -> production -> Coolify native deploy
```

Regras:

- merge em `main` não publica produção;
- `production` é o ponteiro de release;
- workflow protegido move `production` para o SHA exato de `main`;
- Coolify observa apenas `production`;
- proveniência usa `SOURCE_COMMIT` -> `SIGESC_GIT_SHA`;
- rollback move `production` para o SHA anterior;
- SSH no workflow é somente leitura para comprovação do runtime;
- o executor direto `scripts/ops/sigesc_github_only_deploy.sh` é removido.

## 9. MongoDB

O forense mostrou que o deploy nativo do stack pode recriar o container Mongo. A identidade do container, portanto, não é uma invariante válida para esta topologia.

A proteção stateful passa a exigir:

- nenhuma migração explícita no workflow;
- `mongo:7` saudável;
- mesmo volume persistente montado em `/data/db` antes e depois;
- API confirmando `database=connected`.

Separar o Mongo em um recurso stateful independente é possível, mas constitui uma mudança arquitetural futura distinta.

## 10. Estado de segurança durante a correção

Antes da implementação da arquitetura de promoção, o Auto Deploy do Coolify foi desativado manualmente. Portanto, os merges necessários para instalar a nova arquitetura não devem publicar produção.

A branch `production` foi criada no SHA:

```text
2241e9740195098d21426018f4b9973d668c2df0
```

Nenhum novo release de produção é autorizado por este documento.
