# TEACHER VISIBILITY F4.1.2 — Streaming de checkpoints do worker

## Escopo

Investigação read-only do issue #357 para Luiz Gomes dos Santos, E M E I E F Jose Pereira Barbosa, 2026, nos seis pares de Matemática já fixados pela F4/F4.1/F4.1.1.

Esta etapa altera **somente o instrumento de diagnóstico**. Não altera React, backend funcional, banco, dados, autenticação, deploy ou produção.

## Evidência de entrada — F4.1.1

Gate #376, run `33901292880`, audit code `e820858147e7589c6220ac917ba0bf4a212f23d4`, produção `4982421378139ce823005ae374e4b970183c6333`.

Resultado estruturado:

- `INCONCLUSIVE / PUBLIC_BROWSER_RENDER_PROBE_ERROR`;
- 12/12 workers atingiram wall-clock de 40 s;
- `product_failures=[]`;
- API real de produção: 0 requests;
- boundary read-only validada;
- finalizador e artifact executados com sucesso;
- nenhum deploy ou mutação de produção.

A F4.1.1 cumpriu seu objetivo de contenção: o job não foi consumido por um único Playwright travado e terminou com evidência estruturada. Porém, o supervisor usava `proc.communicate(timeout=...)`, de modo que o stdout do filho só era encaminhado depois da saída/timeout. O checkpoint F4.1 `stage=start`, emitido antes de `page.goto`, apareceu nos logs somente no momento em que o worker foi encerrado.

## Problema metodológico restante

Não é possível concluir, a partir da F4.1.1, **quando** o worker atingiu o último estágio. A classificação de produto continua proibida.

A F4.1.2 não aumenta timeouts. Ela torna os checkpoints já existentes observáveis enquanto o processo está vivo.

## Solução F4.1.2

- reutiliza o worker F4.1.1 sem modificá-lo;
- executa o worker com `python -u` e `PYTHONUNBUFFERED=1`;
- supervisor usa `selectors.DefaultSelector` para leitura incremental do pipe;
- apenas checkpoints metadata-only são encaminhados em tempo real;
- o último estágio observado é persistido como `last_checkpoint_stage`;
- timeout é codificado como `WALL_TIMEOUT_AFTER_<stage>`;
- SIGTERM/SIGKILL do grupo e wall-clock de 40 s permanecem;
- orçamento nominal permanece abaixo do teto global de 15 min;
- timeout/crash/ausência de JSON continua `PUBLIC_BROWSER_RENDER_PROBE_ERROR`, nunca `PUBLIC_BROWSER_RENDER_GAP`.

## Interpretação esperada

Se o checkpoint `start` for observado imediatamente e permanecer como último estágio até o wall-timeout, a evidência localiza o travamento dentro da chamada de superfície iniciada pela F4.1, cujo próximo passo é `page.goto(...)` com `wait_until=domcontentloaded`.

Se `start` não for observado, a falha está antes da navegação (bootstrap Playwright/browser/context/page) e será tratada como probe/infrastructure error.

Se o worker concluir e produzir JSON, aplica-se a taxonomia canônica:

- `PUBLIC_BROWSER_RENDER_CURRENT` → avançar para estado específico do cliente;
- `PUBLIC_BROWSER_RENDER_GAP` → investigação cirúrgica React/DOM;
- `PUBLIC_BROWSER_RENDER_PROBE_ERROR` → corrigir somente o probe conforme o último estágio comprovado.

## Boundary

Preservada integralmente pela reutilização do worker F4.1.1:

- produção: recursos públicos GET apenas;
- Service Worker bloqueado;
- `/api/` sintética/local;
- métodos não-GET abortados;
- fetch/XHR não-API sob allowlist;
- WebSockets sem conexão ao servidor;
- sem autenticação real;
- sem Mongo, estudantes, `attendance.records` ou texto pedagógico;
- `production_writes=false`.

## Governança

- branch e PR separados;
- CI obrigatório;
- nenhum deploy nesta etapa;
- produção deve permanecer no SHA observado até a conclusão do gate F4.1.2.
