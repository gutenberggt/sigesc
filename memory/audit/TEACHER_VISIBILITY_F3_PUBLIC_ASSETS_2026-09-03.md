# TEACHER-VISIBILITY-F3/F3.1 — Assets públicos do frontend

Data: 2026-09-03  
Tracking: #357

## Objetivo

Encerrar a hipótese de que o navegador esteja recebendo de produção um frontend anterior ao release vigente, depois que a F2 do caso Luiz Gomes comprovou paridade `Mongo → HTTP → tela` nos seis pares de Matemática.

A auditoria não consulta dados pedagógicos. Ela observa somente recursos públicos que qualquer navegador recebe antes de autenticar:

- `/version.json`;
- `/sw.js`;
- `/` (`index.html`);
- `/asset-manifest.json`;
- todos os arquivos JavaScript inventariados pelo build, inclusive chunks lazy.

## Correção metodológica F3.1

A F3 v1 examinava apenas os `<script src>` presentes no `index.html`. Isso é insuficiente no SIGESC porque `App.js` carrega páginas como `Attendance` e `LearningObjects` por `React.lazy()`/`import()` dinâmico. Os bridges de DVD podem, portanto, residir em chunks secundários que não aparecem diretamente no HTML inicial.

O próprio `sw.js` reconhece essa arquitetura: durante a instalação, lê `asset-manifest.json` e pré-cacheia todos os chunks JS/CSS para garantir navegação offline nas rotas lazy.

Por isso a F3.1 passa a considerar o `asset-manifest.json` como inventário canônico dos assets do build, unido aos scripts iniciais do `index.html`. Uma ausência de assinatura só é classificada como drift se persistir após a varredura de todos os chunks JS publicados.

A classificação `PUBLIC_FRONTEND_ASSET_DRIFT` emitida pela F3 v1 no run `33805700901` deve ser tratada como **provisória**, pois sua cobertura não incluía chunks lazy.

## Provas

A coleta F3.1 confirma:

1. `version.json.git_sha` igual ao SHA de produção esperado;
2. `sw.js` contém esse SHA e não contém o placeholder `__SIGESC_GIT_SHA__`;
3. o Service Worker preserva `skipWaiting()`, `clients.claim()` e cache versionado pelo SHA;
4. `asset-manifest.json` está disponível e contém inventário JS;
5. todos os chunks JS listados no manifest são obtidos por HTTP GET público;
6. pelo menos um chunk público contém assinatura do bridge atual de Conteúdo;
7. pelo menos um chunk público contém assinatura do bridge atual de Frequência;
8. headers públicos relevantes são registrados apenas para diagnóstico de política de cache.

## Boundary

- HTTP **GET** público somente;
- sem autenticação, token de usuário ou impersonação;
- sem MongoDB;
- sem estudantes, matrículas, notas, frequência ou texto pedagógico;
- sem escrita, backfill, migração ou remapeamento;
- AEE, Transferência Institucional e MT-1 intocados.

## Classificação

`PUBLIC_FRONTEND_ASSETS_CURRENT` significa que o servidor público entrega a release esperada, Service Worker versionado e, considerando **todos os chunks do build**, os bridges atuais. Nesse cenário, eventual ausência visual residual não deve ser tratada com saneamento de banco nem correção de endpoint; o próximo discriminador passa a ser o estado do cliente/navegador e da própria tela.

`PUBLIC_FRONTEND_ASSET_DRIFT` só identifica divergência objetiva quando persiste após a cobertura completa do `asset-manifest.json`; nesse caso a investigação deve permanecer na camada de publicação/build/cache antes de qualquer alteração de dados.

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
