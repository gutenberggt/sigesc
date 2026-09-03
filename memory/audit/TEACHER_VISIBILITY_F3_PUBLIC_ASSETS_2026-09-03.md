# TEACHER-VISIBILITY-F3 — Assets públicos do frontend

Data: 2026-09-03  
Tracking: #357

## Objetivo

Encerrar a hipótese de que o navegador esteja recebendo de produção um frontend anterior ao release vigente, depois que a F2 do caso Luiz Gomes comprovou paridade `Mongo → HTTP → tela` nos seis pares de Matemática.

A F3 não consulta dados pedagógicos. Ela observa somente recursos públicos que qualquer navegador recebe antes de autenticar:

- `/version.json`;
- `/sw.js`;
- `/` (`index.html`);
- arquivos JavaScript referenciados pelo `index.html`.

## Provas

A coleta confirma:

1. `version.json.git_sha` igual ao SHA de produção esperado;
2. `sw.js` contém esse SHA e não contém o placeholder `__SIGESC_GIT_SHA__`;
3. o Service Worker preserva `skipWaiting()`, `clients.claim()` e cache versionado pelo SHA;
4. os bundles públicos contêm assinaturas do bridge atual de Conteúdo;
5. os bundles públicos contêm assinaturas do bridge atual de Frequência;
6. headers públicos relevantes são registrados apenas para diagnóstico de política de cache.

## Boundary

- HTTP **GET** público somente;
- sem autenticação, token de usuário ou impersonação;
- sem MongoDB;
- sem estudantes, matrículas, notas, frequência ou texto pedagógico;
- sem escrita, backfill, migração ou remapeamento;
- AEE, Transferência Institucional e MT-1 intocados.

## Classificação

`PUBLIC_FRONTEND_ASSETS_CURRENT` significa que o servidor público entrega a release esperada, Service Worker versionado e bundles contendo os bridges atuais. Nesse cenário, eventual ausência visual residual não deve ser tratada com saneamento de banco nem correção de endpoint; o próximo discriminador passa a ser o estado do cliente/navegador (Service Worker efetivamente controlador, caches locais e contexto de filtros/seleção da tela).

`PUBLIC_FRONTEND_ASSET_DRIFT` identifica divergência objetiva entre o release esperado e os bytes públicos e deve ser resolvido na camada de publicação/cache antes de qualquer investigação de dados.

## Gate de produção

A execução exige issue owner-only com título:

```text
[TEACHER-VISIBILITY-F3-ASSETS] <sha-exato-da-main>
```

E corpo:

```text
TEACHER_VISIBILITY_F3=AUTHORIZED
CONFIRMATION=AUDIT_PUBLIC_FRONTEND_ASSETS_READ_ONLY
TRACKING_ISSUE=357
TARGET_SHA=<sha-exato-da-main>
EXPECTED_PRODUCTION_SHA=<sha-exato-publicado>
```
