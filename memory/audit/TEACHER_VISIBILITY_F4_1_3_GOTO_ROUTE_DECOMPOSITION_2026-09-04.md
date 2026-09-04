# F4.1.3 — decomposição de `page.goto` / route handling

Data: 2026-09-04
Tracking: #357

## Evidência de entrada

A F4.1.2 (`run 33903106410`) concluiu operacionalmente com sucesso, mas a classificação foi `INCONCLUSIVE / PUBLIC_BROWSER_RENDER_PROBE_ERROR`.

Achado uniforme em 12/12 superfícies:

- último checkpoint observado enquanto o worker ainda estava vivo: `start`;
- timeout externo: ~42 s por superfície;
- `product_failures=[]`;
- API real de produção: 0;
- boundary read-only validada;
- nenhum deploy ou mutação de produção.

O checkpoint `start` é emitido imediatamente antes de `page.goto(...)`. Portanto a investigação deve decompor a navegação e o route handler antes de qualquer hipótese React/produto.

## Objetivo F4.1.3

Distinguir, com uma matriz curta e process-isolated:

1. `STATIC_DIRECT` — `page.goto(version.json)` sem `context.route`;
2. `STATIC_ROUTED_CONTINUE` — o mesmo recurso público com `context.route` e `route.continue_()`;
3. `APP_DOCUMENT_ONLY_CONTENT` — rota de conteúdo, permitindo apenas o documento principal e abortando todo subrecurso;
4. `APP_FULL_CONTENT` — rota de conteúdo com a policy F4 completa;
5. `APP_FULL_ATTENDANCE` — rota de frequência com a policy F4 completa.

Cada caso emite checkpoints antes/depois de:

- `sync_playwright()`;
- lançamento do Chromium;
- criação do contexto;
- instalação do route handler;
- criação da página;
- `page.goto`;
- entrada no route handler;
- `route.continue_`, `route.abort` e `route.fulfill`.

Assim, um wall-timeout é localizado pelo último checkpoint observado em tempo real.

## Boundary

- produção: apenas GET público;
- `STATIC_DIRECT` acessa somente `version.json`, que não executa aplicação;
- em qualquer caso com aplicação, `/api/` nunca chega à produção;
- `APP_DOCUMENT_ONLY_CONTENT` aborta todo subrecurso, inclusive qualquer API;
- full-app reutiliza fixtures sintéticas F4 para `/api/`;
- métodos não-GET são abortados;
- Service Worker bloqueado;
- WebSocket fechado localmente;
- sem autenticação real;
- sem Mongo;
- sem estudante/matrícula;
- sem `attendance.records`;
- sem texto pedagógico;
- sem escrita.

## Semântica

F4.1.3 é uma fase de diagnóstico do instrumento. Ela **não pode declarar `PUBLIC_BROWSER_RENDER_GAP` ou qualquer `PRODUCT_GAP`**.

Resultados possíveis:

- `NAVIGATION_ROUTE_DECOMPOSITION_COMPLETE`: a matriz foi executada e produziu um `diagnosis_code` localizado;
- `NAVIGATION_ROUTE_DECOMPOSITION_PROBE_ERROR`: o próprio supervisor não conseguiu produzir a matriz.

## Governança

- branch/PR separado;
- CI antes do merge;
- execução real somente após merge, owner gate e SHA exato;
- tracking #357 deve permanecer aberto;
- produção permanece no SHA observado durante toda a prova;
- nenhum deploy nesta etapa.
