# SIGESC — Fundação do deploy GitHub-only

Data: 2026-08-30

## Objetivo

Eliminar a dependência de estação local também no deploy do SIGESC e estabelecer uma cadeia operacional auditável:

`main verde -> workflow manual protegido -> deploy exato -> prova de revisão/SHA -> health/smoke -> evidência`.

## Estado confirmado antes desta etapa

- repositório: `gutenberggt/sigesc`;
- produção: Coolify v4 com `docker-compose.coolify.yml`;
- serviços declarados: `mongo`, `backend`, `frontend`;
- backend público: `https://api.sigesc.aprenderdigital.top`;
- frontend público: `https://sigesc.aprenderdigital.top`;
- health backend: `/api/health`, que testa inclusive `db.command('ping')`;
- Environment GitHub `production` já possui SSH pinado e o nome real do container Mongo usado nos fluxos D7.6/D7.7.

## Decisão arquitetural

Não codificar no workflow de deploy UUID Coolify, working directory, compose project ou nomes de containers derivados por suposição.

O container Mongo conhecido é usado apenas como âncora para uma descoberta read-only via labels padrão do Docker Compose:

- `com.docker.compose.project`;
- `com.docker.compose.project.working_dir`;
- `com.docker.compose.project.config_files`;
- `com.docker.compose.service`.

A descoberta também identifica backend/frontend do mesmo compose project e registra estado/health/image IDs, sem ler `.Config.Env` ou qualquer valor de variável de ambiente.

## Fase 0 — Production Topology Discovery

Workflow: `.github/workflows/sigesc-production-topology-discovery.yml`.

Características:

- apenas `workflow_dispatch`;
- exige `DISCOVER_SIGESC_PRODUCTION_TOPOLOGY`;
- somente `main`;
- Environment `production`;
- SSH com `StrictHostKeyChecking=yes` e known_hosts pinado;
- não executa `git pull/fetch/checkout/reset`;
- não executa `docker compose up/down/build`;
- não executa restart/stop/start/rm/exec;
- não lê environment dos containers;
- nenhuma consulta ou mutação no MongoDB;
- publica evidência por 90 dias.

O discovery verifica também os endpoints públicos:

- API `/api/health` precisa responder `status=healthy` e `database=connected`;
- frontend precisa responder HTTP com sucesso.

## Gate para a próxima fase

O deploy write-capable só será implementado depois de observar a topologia real produzida pelo discovery.

A próxima fase deverá, no mínimo:

1. fixar o target SHA da `main`;
2. validar que o workspace remoto corresponde ao repositório SIGESC e está em topologia suportada;
3. impedir drift/local changes antes de substituir source;
4. preservar volumes Mongo/DVD/schedule e environment atual;
5. atualizar somente `backend` e `frontend`, salvo necessidade comprovada;
6. adicionar proveniência do SHA aos artefatos/containers;
7. aguardar healthchecks dos containers;
8. verificar `https://api.sigesc.aprenderdigital.top/api/health`;
9. verificar frontend público;
10. confirmar o SHA efetivamente implantado;
11. produzir recibo/auditoria GitHub Actions;
12. falhar fechado diante de topologia inesperada.

## Segurança

Esta fase é exclusivamente de descoberta. Não constitui autorização para deploy nem para mutação de banco de dados.

`DATABASE_MUTATION=NO`

`PRODUCTION_WRITES=NO`
