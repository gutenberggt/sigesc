# F4.1.4 — decomposição pós-`page.goto`

Data: 2026-09-04  
Tracking: #357

## Evidência de entrada

A F4.1.3 concluiu `PASS / NAVIGATION_ROUTE_DECOMPOSITION_COMPLETE`, com diagnóstico `GOTO_ROUTE_DECOMPOSITION_HEALTHY`.

Todos os cinco casos chegaram a `goto_after`:

- `STATIC_DIRECT`;
- `STATIC_ROUTED_CONTINUE`;
- `APP_DOCUMENT_ONLY_CONTENT`;
- `APP_FULL_CONTENT`;
- `APP_FULL_ATTENDANCE`.

Logo, o `page.goto`, `route.continue_`, documento principal e carregamento inicial de scripts/styles foram demonstrados funcionais no runner. A F4.1.2, entretanto, continuava atingindo wall-timeout após o seu checkpoint genérico `start`, que engloba todo o restante do probe.

## Objetivo

Localizar o primeiro bloqueio **depois** de `page.goto`, reproduzindo a semântica F4.1 com checkpoints antes/depois de cada chamada síncrona do Playwright.

A F4.1.4 usa apenas o par representativo `6º ANO A / Matemática`, pois a F4.1.2 apresentou comportamento uniforme em 12/12 superfícies.

Casos:

1. `CONTENT_POST_GOTO`;
2. `ATTENDANCE_POST_GOTO`.

## Escada instrumentada

Comum:

- `page.goto`;
- criação de `locator("select")`;
- polling de `selects.count()`;
- `evaluate_all()` das opções selecionadas;
- route events e antes/depois de `route.fulfill/continue/abort`.

Conteúdo:

- heading `Objetos de Conhecimento`;
- `heading.count()`;
- locator `div.bg-green-100`;
- `evaluate_all()` das datas.

Frequência:

- botão `Registros`;
- `count()`;
- `click()`;
- espera por `[data-testid="attendance-registros-tab"]`;
- contagem de `[title="Frequência registrada"]`.

O polling preserva a mesma cadência da F4.1: timeout lógico de 4 s e intervalo de 200 ms. O processo de cada superfície continua protegido por wall-clock externo.

## Boundary

- produção apenas GET público;
- `/api/` sempre respondida localmente com fixtures sintéticas F4;
- métodos não-GET abortados;
- fetch/XHR não allowlisted abortados;
- Service Worker bloqueado;
- WebSocket fechado localmente;
- sem autenticação real;
- sem Mongo;
- sem estudante/matrícula;
- sem `attendance.records`;
- sem texto pedagógico;
- sem escrita.

## Semântica

F4.1.4 diagnostica exclusivamente o instrumento browser após a navegação. Ela **não pode declarar `PUBLIC_BROWSER_RENDER_GAP` nem qualquer `PRODUCT_GAP`**.

Se ambos os ladders concluírem, a investigação deve comparar a diferença residual com o worker F4.1.2 (repetição/encadeamento/fechamento). Se um ladder atingir wall-timeout, o último checkpoint identifica a chamada específica.

## Governança

- branch/PR separado;
- CI completo antes do merge;
- execução somente após merge e owner gate exact-SHA;
- #357 permanece aberto;
- produção preservada no SHA observado;
- nenhum deploy nesta etapa.
