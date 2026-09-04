# F4.1.5 — browser→DOM com WebSocket roteado localmente

Data: 2026-09-04  
Tracking: #357

## Evidência de entrada

A F4.1.3 provou `GOTO_ROUTE_DECOMPOSITION_HEALTHY`.

A F4.1.4 então localizou, em conteúdo e frequência, o mesmo bloqueio instrumental:

- `page.goto` retornou;
- `route.fulfill()` para fixtures sintéticas retornou;
- `selects.count()` retornou nas primeiras iterações;
- o callback WebSocket foi acionado;
- o último checkpoint em ambos os casos foi `websocket_close_before`;
- não houve `websocket_close_after`;
- ambos os workers foram encerrados pelo wall-clock externo.

Portanto o uso de `WebSocketRoute.close()` no probe é a causa reproduzível do deadlock do instrumento. Não há evidência correspondente de falha do produto.

## Base técnica

A documentação oficial do Playwright para `WebSocketRoute` informa que um WebSocket roteado não se conecta ao servidor por padrão. Assim, um handler local que retorna sem `connect_to_server()` já mantém a conexão fora da produção e permite mock completo.

A F4.1.5 remove somente do novo probe a chamada de fechamento do WebSocket. Os scripts históricos F4/F4.1/F4.1.1/F4.1.2/F4.1.3/F4.1.4 permanecem inalterados para preservar a trilha de auditoria.

## Método

A F4.1.5 volta ao escopo completo dos seis pares de Luiz Gomes, com duas superfícies por par:

- Objetos de Conhecimento;
- Frequência / aba Registros.

São reutilizadas diretamente as funções F4.1:

- `_probe_content()`;
- `_probe_attendance()`;
- `evaluate_pairs()`.

Logo, a taxonomia de produto permanece exatamente:

- `PASS / PUBLIC_BROWSER_RENDER_CURRENT`;
- `FAIL / PUBLIC_BROWSER_RENDER_GAP`;
- `INCONCLUSIVE / PUBLIC_BROWSER_RENDER_PROBE_ERROR`.

Timeout ou erro de infraestrutura nunca é convertido em GAP.

Cada uma das 12 superfícies roda em processo isolado, com stdout em streaming, wall-clock externo e SIGTERM/SIGKILL de contenção.

## Política WebSocket corrigida

O novo handler:

1. registra apenas a URL do WebSocket para metadados;
2. não chama `WebSocketRoute.close()`;
3. não chama `connect_to_server()`;
4. retorna imediatamente.

Metadados obrigatórios:

- `websocket_policy=ROUTED_LOCAL_NO_SERVER_CONNECTION`;
- `websocket_server_connections=0`;
- `websocket_close_calls=0`.

## Boundary

- produção: somente GET público;
- `/api/`: sempre fixture sintética/local;
- métodos não-GET: abortados;
- fetch/XHR dinâmico fora da allowlist: abortado;
- WebSocket: roteado localmente, sem conexão ao servidor;
- Service Worker: bloqueado;
- sem autenticação real;
- sem Mongo;
- sem estudante/matrícula;
- sem `attendance.records`;
- sem texto pedagógico;
- sem escrita.

## Governança

- branch e PR separados;
- CI completo antes do merge;
- runtime somente após merge + owner gate + SHA exato;
- #357 deve permanecer aberto até a classificação browser→DOM válida;
- produção deve permanecer no SHA observado;
- nenhum deploy durante esta prova.

Depois da classificação válida:

- `PUBLIC_BROWSER_RENDER_CURRENT` → avançar para diagnóstico de estado específico do cliente (cache/PWA/Service Worker/localStorage/session);
- `PUBLIC_BROWSER_RENDER_GAP` → investigação React/DOM read-only antes de qualquer correção;
- `PUBLIC_BROWSER_RENDER_PROBE_ERROR` → corrigir somente o instrumento.
