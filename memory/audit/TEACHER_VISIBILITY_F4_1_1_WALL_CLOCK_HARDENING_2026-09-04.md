# TEACHER VISIBILITY F4.1.1 — Wall-clock hardening do probe browser

Data: 2026-09-04  
Tracking: #357  
Gate anterior: #374  
Run anterior: `33891900305`  
Job anterior: `101085319601`

## 1. Estado causal antes da F4.1.1

A investigação do caso Luiz Gomes já havia produzido evidência favorável para:

- identidade/vínculo docente: sem split ou drift demonstrado;
- dados Mongo: presentes;
- projeção HTTP/professor-management: alcançando a tela estruturalmente;
- assets públicos: atuais e contendo as bridges esperadas.

O ponto ainda não provado era o trecho **React público → DOM real**.

A F4 original terminou por timeout global e foi corretamente classificada como inconclusiva.

A F4.1 tentou endurecer timeouts internos, separar páginas por par e emitir checkpoints. O run `33891900305` confirmou que isso ainda não era suficiente.

## 2. Evidência do run F4.1

No run `33891900305`:

- exact-SHA owner gate: PASS;
- checkout de `main` exato: PASS;
- instalação Chromium: PASS;
- início do browser audit: PASS;
- único checkpoint emitido:
  - `6º ANO A / content / start / RUNNING`;
- nenhum checkpoint posterior de navegação, probe ou conclusão;
- o job foi cancelado pelo teto de 15 minutos;
- `Validate no-production-data boundary and result taxonomy`: skipped;
- `Comment diagnosis and close gate`: skipped;
- o artifact `always()` preservou somente o log parcial;
- não houve JSON estruturado final.

Classificação metodológica:

`INCONCLUSIVE / GLOBAL_TIMEOUT`

Isto **não** constitui `PUBLIC_BROWSER_RENDER_GAP`.

## 3. Falha do instrumento observada

O travamento ocorreu após o checkpoint imediatamente anterior ao `page.goto(...)` do primeiro probe de conteúdo.

A F4.1 configurava `page.goto(..., timeout=15000)`, mas o controle não retornou dentro desse orçamento. Portanto, timeout interno do Playwright não pode ser tratado como mecanismo de contenção suficiente.

A causa interna específica do bloqueio Playwright/CDP/routing não está demonstrada e não precisa ser presumida para corrigir o instrumento. A propriedade necessária é mais simples:

> qualquer chamada Playwright pode, em princípio, bloquear além do timeout lógico e deve ficar subordinada a um supervisor de processo externo.

## 4. Decisão F4.1.1

A F4.1.1 preserva F4 e F4.1 como histórico e adiciona um coletor novo:

`backend/scripts/teacher_visibility_f4_1_1_browser_render.py`

Estratégia:

1. o processo supervisor valida o SHA público esperado;
2. cada par/tela é executado em **processo de sistema operacional independente**;
3. cada superfície recebe wall-clock externo de 40 segundos;
4. o worker usa timeouts internos menores:
   - navegação: 10 s;
   - ação: 5 s;
   - polling: 4 s;
5. se o worker não retornar:
   - SIGTERM no grupo de processos;
   - pequena janela de grace;
   - SIGKILL no grupo se necessário;
   - classificação da superfície como `PROBE_ERROR`;
6. o supervisor continua para a próxima superfície;
7. timeout/crash/JSON ausente do worker jamais vira `PRODUCT_GAP`.

O grupo de processos é iniciado com `start_new_session=True`, permitindo eliminar Chromium e subprocessos descendentes sem cancelar o job inteiro.

## 5. Orçamento de execução

Escopo:

- 6 turmas;
- 2 superfícies por turma;
- 12 workers.

Wall-clock máximo nominal dos workers:

`12 × 40 s = 480 s`

Reserva para verificação pública e overhead:

aproximadamente 35 s + criação/encerramento de processos.

O orçamento nominal permanece abaixo do teto de 15 minutos do job.

## 6. Taxonomia preservada

### PASS

`PASS / PUBLIC_BROWSER_RENDER_CURRENT`

Somente quando os 6 pares completarem conteúdo e frequência sem probe error ou mismatch.

### FAIL

`FAIL / PUBLIC_BROWSER_RENDER_GAP`

Somente quando o probe completar tecnicamente e houver mismatch determinístico no DOM.

### INCONCLUSIVE

`INCONCLUSIVE / PUBLIC_BROWSER_RENDER_PROBE_ERROR`

Inclui:

- wall timeout;
- crash do worker;
- exit code anormal;
- JSON estruturado ausente/inválido;
- falha de navegação/selector/browser;
- falha catastrófica do runner.

Regra invariável:

`TIMEOUT_IS_PRODUCT_GAP = NO`

## 7. Boundary read-only

Permanece igual à F4/F4.1:

- produção acessível somente por GET de recursos públicos;
- Service Worker bloqueado;
- toda URL `/api/` respondida localmente por fixtures sintéticas;
- métodos não-GET abortados;
- fetch/XHR não-API limitado à allowlist pública;
- WebSocket fechado sem conexão ao servidor;
- nenhuma autenticação real;
- nenhum Mongo;
- nenhum estudante;
- nenhum `attendance.records`;
- nenhum texto pedagógico;
- nenhuma escrita de produção.

A F4.1.1 não altera React, backend funcional, dados, bindings, PWA ou produção.

## 8. Hardening do workflow

Novo workflow:

`.github/workflows/teacher-visibility-f4-1-1-browser-render.yml`

Além do process isolation, corrige a fragilidade residual do F4.1:

- `Ensure structured fallback evidence` roda com `if: always()`;
- `Validate ...` roda com `if: always()`;
- artifact metadata-only roda com `if: always()`;
- finalizador roda com:
  - `if: always() && steps.context.outcome == 'success'`;
- se `browser.json` não existir, o workflow sintetiza:
  - `INCONCLUSIVE / PUBLIC_BROWSER_RENDER_PROBE_ERROR`;
- o gate deve ser comentado e fechado mesmo depois de falha do probe, desde que o owner/exact-SHA gate tenha sido validado.

## 9. Contrato de gate após merge

Título:

`[TEACHER-VISIBILITY-F4.1.1-BROWSER] <TARGET_SHA>`

Body:

```text
TEACHER_VISIBILITY_F4_1_1=AUTHORIZED
CONFIRMATION=AUDIT_PUBLIC_BROWSER_RENDER_READ_ONLY
TRACKING_ISSUE=357
TARGET_SHA=<exact main SHA>
EXPECTED_PRODUCTION_SHA=<exact production SHA>
```

O gate é fail-closed para:

- autor diferente do owner;
- campos ausentes/duplicados;
- título divergente;
- `main` movido;
- `production` movida;
- tracking #357 fechado.

## 10. Governança

Esta etapa corrige **somente o probe**.

Não autorizado por esta etapa:

- alteração de React;
- correção de dados;
- backfill/remapeamento;
- deploy;
- merge automático.

A implementação deve passar por PR separado, CI e revisão. Merge em `main` continua exigindo autorização humana explícita.
