# SIGESC - Product Requirements Document

## ⛔ MÓDULOS BLOQUEADOS (NÃO ALTERAR SEM PERMISSÃO EXPLÍCITA DO USUÁRIO)

> **AVISO PARA AGENTES E DESENVOLVEDORES**: Os módulos abaixo foram travados pelo
> usuário (proprietário do produto). Qualquer alteração — visual, funcional,
> refatoração, "melhoria" estética, mudança de campos, props, modelos Pydantic,
> rotas, validações, fluxos de salvamento, modais, etc. — **EXIGE autorização
> explícita do usuário ANTES de qualquer edição**. Não pergunte "posso refatorar?"
> de forma genérica; descreva o que pretende mudar e aguarde o "sim" literal.
>
> | Módulo | Caminhos protegidos |
> |---|---|
> | **Diário AEE** | `/app/frontend/src/pages/DiarioAEE.js`, `/app/frontend/src/components/PlanoAEEModal.js`, `/app/frontend/src/pages/tutorials/TutorialDiarioAEE.jsx`, `/app/backend/routers/aee.py`, models `PlanoAEE*` em `/app/backend/models.py` (linhas ~1184-1305), tests em `/app/backend/tests/test_aee*.py` |
>
> Se um bug surgir nesses arquivos, o ÚNICO procedimento permitido é:
> 1. Reproduzir, identificar a causa raiz e descrever o fix proposto (sem aplicar).
> 2. Pedir confirmação ao usuário antes de tocar no código.
> 3. Após o "sim" do usuário, fazer somente o fix mínimo necessário — nada além.

## Original Problem Statement
Sistema Integrado de Gestão Escolar multi-tenant (SaaS) para prefeituras, com isolamento de dados entre mantenedoras, gestão de escolas, turmas, alunos, servidores e folha de pagamento.

## User's preferred language: Portuguese

## AUDITORIA (Jun/2026) — Movimentação de Alunos (sem implementação): `memory/AUDITORIA_MOVIMENTACAO_ALUNOS.md`
Evidência real (código + execução em banco isolado `scripts/_audit_student_movement.py`). Conclusões:
- Mecanismo canônico **EXISTE**: `copy-data` (copia notas+frequência origem→destino) + `build_consolidated_history` (Histórico Escolar; notas agregadas por student+ano+curso, independente da turma atual; escola via `school_history[]`).
- **Remanejamento/Progressão/Reclassificação** = mesmo caminho (`PUT /students/{id}` + `copy-data` frontend). Origem preservada; notas/frequência duplicadas (idempotente no retorno); AEE e Bolsa Família intactos (ancorados em student_id).
- **Transferência entre escolas** = motor próprio (class-anchored), mais íntegro, inclui `content_entries`, sem duplicação, com rollback.
- **LACUNAS/RISCOS:** (1) `content_entries` NÃO copiado em remanej/progr/reclass; (2) Histórico **duplica o ano/série** (1 linha por turma cursada no ano) → risco legal; (3) `copy-data` é frontend-triggered e **fail-silent** (perda silenciosa se falhar); (4) nova matrícula usa `now().year` em vez do ano da turma; (5) risco de dupla contagem de frequência em agregações por aluno×ano.
- **Decisão recomendada:** corrigir fluxos (P0: consolidação no backend, incluir conteúdo, dedup do histórico, herdar ano da turma) + criar ferramenta P1 "Reconstrução de Histórico Pedagógico" para dados legados. **Aguardando aprovação do usuário antes de implementar.**


## CHANGELOG — GATE de regressão em CI (gate duro automático + gate humano final) (Jun/2026)
**Arquitetura aprovada:** `cycle` = gate DURO automático (detecta regressão, bloqueia merge/deploy) · homologação assistida = gate HUMANO final (7 gates + aprovação formal) · produção só libera com os dois. CI **não** substitui os gates humanos.
- **`make regression`** (Makefile): GATE DURO em **2 camadas formais, fail-fast global**. Camada 1 = smoke E2E (`cycle`, sandbox isolado, 8 verificações). Camada 2 = **suíte de 27 testes** (`test_school_transfer.py` 6 + `test_school_resolution.py` 10 + `test_school_transfer_rollback.py` 11) com `pytest -x` (falha imediata). Se qualquer camada falhar, o gate aborta com exit 1 (bloqueia merge/deploy). Banner reforça "NÃO certifica o sistema".
- **Isolamento de estado da Camada 2** (`backend/tests/conftest.py`, ativo só com `CI_SEED_TRANSFER=1`): semeia mantenedora + 3 escolas ativas + calendário 2025 (atende `_pick_two_schools`/`_dest_with_calendar`) e **reseta o estado antes de cada teste** (reativa escolas, purga turmas residuais) evitando cascata; tudo `ci_fixture:true`, removido ao final. Credenciais das suítes agora via env (`TRANSFER_TEST_EMAIL/PASSWORD`, fallback gutenberg). Verificado: 27/27 PASS exercitando o conftest, **zero resíduo**.
- **Workflow bloqueante** `.github/workflows/transfer-regression.yml`: roda em `pull_request`→main e `push`→main. Sobe MongoDB efêmero + backend (uvicorn) + bootstrap de super_admin de CI, executa `make regression`. Em PASS emite `::warning` "PASS (NÃO é certificação de liberação)". Para ser efetivo, marcar como **Required status check** na proteção da branch `main` (único bypass: override explícito de admin do GitHub OU label `regression-bypass` no PR — auditável).
- **`scripts/ci_bootstrap_admin.py`**: upsert idempotente de super_admin para CI (banco efêmero). Marca `ci_bootstrap:true` e **recusa** rodar contra banco real com usuários quando `CI!='true'`.
- **Verificado:** `make regression` → 8/8 PASS contra o backend; bootstrap testado em DB descartável (login super_admin válido), depois dropado. Nenhum resíduo.


## CHANGELOG — Homologação Assistida (sandbox isolado) + BUGFIX crítico de rollback (Jun/2026)
**Entregue (sem novas features — foco em comprovar transferência+rollback em ciclo real):**
- **Harness de sandbox ISOLADO** `backend/scripts/homolog_transfer_sandbox.py` (subcomandos `seed`/`baseline`/`validate --expect dest|origin`/`teardown`): cria mantenedora + 2 escolas + calendário + turmas + alunos + amostras de TODOS os domínios (frequência, notas, conteúdo, AEE, Bolsa Família), tudo marcado `homolog_sandbox:true` (zero contato com dados reais; teardown idempotente).
- **Runbook guiado** `memory/HOMOLOGACAO_ASSISTIDA_GUIADA.md` (ciclo dry-run→execute→validate(dest)→receipt→rollback→revalidate(origin) com 7 GATES de decisão humana + critérios de aprovação + contingência) e roteiro completo `memory/HOMOLOGACAO_TRANSFERENCIA_INSTITUCIONAL.md`.
- **🐞 BUGFIX CRÍTICO (rollback):** o snapshot guardava uma *referência* ao `school_history` da turma, que é mutado in-place no re-homing → a reversão NÃO restaurava o histórico de turmas que já possuíam `school_history` (o segmento do destino permanecia aberto). Corrigido com `copy.deepcopy` na captura do snapshot (`routers/school_transfer.py`). O pytest anterior não pegou porque turmas criadas via API não tinham `school_history`; o harness (dados realistas) expôs.
- **Regressão:** novo teste `test_rollback_restores_preexisting_school_history_exactly`. Suíte `test_school_transfer_rollback.py` **11/11 PASS**. Ensaio interno do ciclo completo no sandbox: validate(dest) e validate(origin) **TUDO OK**, recibo PDF 200, rollback idempotente + origem reaberta, teardown limpo.


## CHANGELOG — Fase 3 CONCLUÍDA: UI da Transferência Institucional (Wizard + Painel + Recibo PDF/QR) (Jun/2026)
**Escopo entregue (super_admin):**
- **Recibo PDF oficial com QR verificável** (backend): `GET /admin/school-transfer/{protocol}/receipt` → PDF (reportlab) com protocolo, origem/destino, turmas, alunos, operador, justificativa, data/hora + rodapé de verificação pública (código + QR → `/v/{token}`). Cria/reutiliza `verifiable_documents` (tipo `recibo_transferencia_institucional`); **não grava em `school_documents_log`** (não fecha a janela de rollback). Builder em `pdf/transfer_receipt.py`.
- **Wizard de 5 etapas** (`pages/SchoolTransferWizard.jsx`, rota `/admin/transferencias/nova`): Etapa 1 Origem/Destino (destino filtrado pela mesma mantenedora + resumo de turmas); Etapa 2 Seleção (escola inteira ou turmas específicas + impacto previsto); Etapa 3 Dry Run obrigatório (contagens + validações 🟢🟡🔴, avanço bloqueado sem `can_execute`); Etapa 4 Confirmação forte (senha + justificativa ≥10 + frase exata + resumo); Etapa 5 Resultado (protocolo, data/hora, prazo de reversão).
- **Painel administrativo** (`pages/SchoolTransfers.jsx`, rota `/admin/transferencias`): tabela com protocolo, origem, destino, data, operador, status, reversível (dias restantes) e ações Visualizar / Gerar recibo / Reverter (modal com re-auth + frase). Card de acesso no Dashboard (`nav-school-transfers-button`).
- **Frontend API** `schoolTransferAPI` em `services/api.js`.
**Validação:** testing_agent iter_104 — **29/29 PASS** (wizard etapas 1→4 + painel; execução real NÃO disparada por ser destrutiva). Recibo PDF/QP e rollback validados no backend via pytest (`test_school_transfer_rollback.py` 11/11, incl. recibo). Painel sem linhas na preview (estado de dados, não bug).
**Pendência conhecida:** ações do painel (view/receipt/rollback) não exercitadas via UI por ausência de transferência `executed` persistida na preview — cobertas no nível de API (pytest). Itens adiados por decisão do usuário: integração StatusIndicator↔transferências, notificações, dashboard de métricas, Censo.


## CHANGELOG — Fase 2 CONCLUÍDA (backend): Rollback da Transferência Institucional (Jun/2026)
**Objetivo:** reversão segura (controle de risco) ANTES de expor a UI da transferência aos gestores.
**Implementação (`routers/school_transfer.py`):**
- **`GET /admin/school-transfer/{protocol}/rollback-eligibility`** — informa se a reversão é permitida (para a futura UI/Fase 3).
- **`POST /admin/school-transfer/{protocol}/rollback`** — super_admin + re-auth por senha + frase `CONFIRMO A REVERSÃO DA TRANSFERÊNCIA`.
- **Janela de reversão:** 7 dias a partir de `executed_at` OU primeira emissão de documento oficial (detectada em `school_documents_log` por `class_id`/`student_id` com `emitted_at > executed_at`). Bloqueio automático (409 `WINDOW_EXPIRED` / `OFFICIAL_DOCUMENT_EMITTED`).
- **Reversão completa** usando o `snapshot` já capturado no execute (old_school_id por doc; old_school_history por turma): restaura `classes` (school_id + school_history EXATO → sem sobreposição/lacunas), `students/enrollments/attendance/grades/content_entries/teacher_class_assignments/student_dependencies` e AEE/Bolsa Família.
- **Idempotente:** re-setar o mesmo valor não gera efeito colateral; 2ª chamada retorna o MESMO `rollback_protocol` (status `rolled_back`). Falha parcial NÃO marca rolled_back (re-execução conclui) e libera o lock.
- **Reabertura automática** da escola origem se foi encerrada exclusivamente por essa transferência (`origin_closed`).
- **Auditoria imutável:** quem/quando/justificativa/IP/protocolo original/resultado em `school_transfer_audit.rollback`; evento `reversao_transferencia_institucional` append-only (protocolo `ROLLBACK-{ano}-{seq}`), preservando o evento original.
**Validação:** `tests/test_school_transfer_rollback.py` — 9/9 PASS cobrindo Execute→Rollback, Rollback×2 (idempotência), fora da janela, pós-documento oficial, falha parcial→recuperação, múltiplas turmas, escola inteira (reabertura), segurança (senha/frase/super_admin) e endpoint de elegibilidade. Regressão Fase 1 (`test_school_transfer.py` + `test_school_resolution.py`) 16/16 PASS. NOTA: backend-only — sem UI ainda (Fase 3).


## CHANGELOG — P2 CONCLUÍDO: Indicador Permanente de Status no header (Jun/2026)
**Objetivo:** uma única fonte de verdade, sempre visível, do estado do sistema para o professor (conexão + fila de sincronização + sessão), evitando o risco "achei que estava salvo mas há N registros que falharam".
**Implementação:**
- **Novo hook `hooks/useSessionStatus.js`** (read-only): deriva `sessionState` (active/warn5/warn1/expired) + `remainingMs` do JWT via `getTokenExpMs`/`computeSessionState` (sessionToken.js). Tick de 15s, sem chamadas ao backend. SessionMonitor (P0) intacto.
- **Novo componente `components/session/StatusIndicator.jsx`**: pílula permanente no header com prioridade por risco pedagógico: 1) 🔴 Sessão expirada, 2) 🔴 Falhas, 3) 🟠 Pendências (com contador), 4) ⚫ Offline, 5) 🔵 Sincronizando, 6) 🟢 Sincronizado. Popover (shadcn) com estado/tempo de sessão, última sincronização, pendências/falhas por categoria, botão "Sincronizar agora" e "Entrar novamente" (quando expirada). data-testids: `status-indicator`, `status-indicator-popover`, `status-session-state`, `status-resync-button`, `status-relogin-button`.
- **`Layout.js`**: `ConnectionStatusBadge` → `StatusIndicator`; `FloatingStatusIndicator` removido (import, JSX e **definição/exports** apagados de `OfflineStatus.jsx` — sem código morto). `OfflineBanner` mantido como alerta forte de perda de conexão.
**Arquitetura final de indicadores:** OfflineBanner (evento crítico) · StatusIndicator (estado permanente + ações) · SessionMonitor (avisos/expiração). FloatingStatusIndicator ❌ removido.
**Validação E2E (testing_agent iter_103):** 14/14 asserts PASS — visível desktop+mobile e em múltiplas páginas, popover com sessão "Ativa (expira em 14min)", resync desabilitado sem pendências, transição offline↔online, OfflineBanner ok, FloatingStatusIndicator ausente. Sem chamadas extras ao backend (tick 15s).


## CHANGELOG — Epic P1 CONCLUÍDA: AutoSave anti-perda de dados nos 3 módulos pedagógicos (Jun/2026)
**Objetivo:** garantir que NADA digitado em formulários críticos seja perdido por expiração de sessão, queda de internet ou fechamento do navegador (escolas rurais).
**Implementação:** hook `useAutoSaveDraft` + `DraftRestoreBanner` (Dexie/IndexedDB tabela `drafts`, v4). Integrado em:
- **Notas** (`Grades.js`) e **Frequência** (`Attendance.js`) — já entregues em sessão anterior.
- **Conteúdo / Objetos de Conhecimento** (`LearningObjects.js`) — ENTREGUE NESTA SESSÃO. Bloco AutoSave (`loFormId`, `loDraftData`, `restoreLoDraft`, `discardLoDraft`) declarado após as flags de nível (correção de TDZ). `formId` isola por turma/componente/data/modo: individual=`content:{classId}:ind:{courseId}:{date}`, multi=`content:{classId}:multi:{date}`. Rascunho preserva `formData` + `selectedCourses` (multi). `clearLoDraft()` no sucesso de `handleSave`/`handleDelete`.
**Fix de regressão (backend):** `GET /api/courses` retornava 500 (Pydantic ResponseValidationError) por 1 course legado com `nivel_ensino='INFANTIL'`. Adicionado `field_validator _normalize_nivel_ensino` em `CourseBase` (coerce 'INFANTIL'→'educacao_infantil') + migração do dado no MongoDB.
**Validação E2E (testing_agent iter_100→102):** 10/10 asserts PASS — modo individual e multi-seleção, restauração após reload, limpeza pós-save e isolamento por formId (4 sub-casos). `GET /api/courses` = 200.


## CHANGELOG — Banner "Instalar SIGESC como app" (PWA) (Jun/2026)
**Objetivo:** elevar a confiabilidade offline sem depender de o usuário saber instalar o PWA manualmente.
**Implementação (`pages/Login.js`):** banner azul "📲 Instale o SIGESC como aplicativo" exibido quando NÃO está em modo standalone, não foi dispensado e `storagePersisted !== true`. Captura `beforeinstallprompt` → botão **"Instalar app" (1 clique)** via `prompt()`; quando o evento não está disponível, mostra instrução manual (menu ⋯ → Instalar). Esconde via `appinstalled`, ao conceder persistência, ou ao dispensar (X / "Agora não", flag em sessionStorage). data-testids: `install-pwa-banner`, `install-pwa-button`, `install-pwa-dismiss`. SW bump → v2.12.7.
**Validação (preview):** banner aparece (com fallback de instruções, pois a automação não dispara `beforeinstallprompt`) e o dismiss o remove. PASS. Em Edge/Chrome real, o botão de instalação em 1 clique aparece.

## CHANGELOG — Ajuste: logout ("Sair") preserva a sessão offline (Jun/2026)
**Pedido do usuário (refinamento):** "Sair (logout) não deve limpar a sessão offline".
**Mudança (`AuthContext.logout`):** o logout agora encerra a sessão ONLINE (remove `accessToken`/`refreshToken`/CSRF/tenant/contexto e caches) mas **PRESERVA `userData` + `lastLoginTime`**, mantendo o "Entrar (Offline)" funcional sem internet. Para apagar tudo (inclusive o acesso offline) existe `logoutComplete()` (remove userData/lastLoginTime após o logout). Botão "Sair" (Layout) usa `logout()`.
**Validação (preview):** login online → "Sair" → `userData`/`lastLogin` preservados, `accessToken` removido, painel mostra "Sessão salva: SIM ✓". PASS.
**Status do P0 offline:** ✅ RESOLVIDO e confirmado pelo usuário no app instalado — offline, após fechar/reabrir: "Sessão salva: SIM ✓ / Armazenamento persistente: SIM ✓ / build v2.12.5". SW bump → v2.12.6.

## CHANGELOG — P0 (causa raiz FINAL): armazenamento não-persistente → navegador apaga sessão ao fechar (Jun/2026)
**Teste A decisivo:** logo após login online (sem fechar o navegador), o painel mostra **"Sessão salva: SIM ✓ / build v2.12.4"** — gravação OK e código novo rodando. O "NÃO" só aparece **após fechar/reabrir o navegador**.
**Causa raiz:** `navigator.storage.persisted()` = **false**. O armazenamento do site é "best-effort"; o navegador (Edge) faz **eviction/limpeza ao fechar**, apagando `localStorage` (userData/tokens) e quebrando a sessão offline. A API de login de produção foi testada via curl: 200 OK com token + user (backend OK).
**Correções (v2.12.5):**
- `index.html` + `Login.js`: solicitam **armazenamento persistente** via `navigator.storage.persist()`.
- `Login.js`: painel de diagnóstico agora exibe **"Armazenamento persistente: SIM/NÃO"** (autoexplicativo).
- SW bump v2.12.4 → **v2.12.5** (cache v19).
**Resolução operacional (chave):** o navegador só concede persistência de forma confiável quando o site é **INSTALADO como app (PWA)** (ou com engajamento/notificações). Ação do usuário: **Instalar o SIGESC como aplicativo** (Edge: ícone de instalar na barra de endereço / Menu → Aplicativos → Instalar). Após instalar, o painel passa a "Armazenamento persistente: SIM ✓" e a sessão sobrevive ao fechar → login offline funciona em cold-start. Alternativa: desativar no Edge "Limpar dados ao fechar" e/ou adicionar o site às exceções de cookies/dados.
**Validação (preview):** painel exibe corretamente "Armazenamento persistente: NÃO ⚠" quando não concedido; persist() é solicitado em toda carga.

## CHANGELOG — P0 (cold-start offline): erro nativo ERR_INTERNET_DISCONNECTED ao reabrir o navegador offline (Jun/2026)
**Sintoma:** ao FECHAR o navegador e reabrir OFFLINE, aparecia a página nativa do navegador "Parece que você não está conectado à Internet / ERR_INTERNET_DISCONNECTED" em vez do SIGESC.
**Causa raiz:** quando NÃO há Service Worker ativo, a navegação offline vai direto à rede e falha. O `reset.html` **desregistrava o SW** (e o SW só re-registrava após uma carga ONLINE via OfflineContext). Se o usuário reabrisse offline sem ter recarregado online, ficava sem SW → erro nativo. (A `navigationStrategy` em si está correta: com SW ativo, serve o `/index.html` cacheado — validado.)
**Correções:**
- `public/index.html`: **registro PRECOCE do SW** no `window.load` (toda carga online re-estabelece o SW, independente do React).
- `public/reset.html`: após limpar SW/caches, **re-registra o `/sw.js`** antes de redirecionar — nunca deixa o dispositivo sem SW. (Já preservava a sessão offline desde v2.12.3.)
- SW bump v2.12.3 → **v2.12.4** (cache v18).
**Validação (preview):** SW ativo + offline → navegar para `/` serve o app shell do SIGESC (login offline + painel de diagnóstico), sem erro nativo. PASS.
**Operacional:** após o deploy, basta **1 carga ONLINE** (registra SW + cacheia shell/chunks). Depois, fechar/reabrir offline funciona. **Não usar `reset.html`** no uso normal.

## CHANGELOG — P0 (robustez final): reset preserva sessão + TTL 30d + diagnóstico visível + correção do bug real (Jun/2026)
**Verdade do dispositivo (log do usuário):** `[Auth Offline] {temUserData: false, temLastLogin: false}` rodando no bundle novo — ou seja, no momento do teste o `localStorage` estava VAZIO (não havia sessão salva). Confirmado que o login ONLINE persiste a sessão (painel mostra "Sessão salva: SIM" logo após login). A falha vinha de o `localStorage` ter sido esvaziado (uso do `reset.html`, que fazia `localStorage.clear()`) sem novo login online depois.
**Mudanças:**
- `public/reset.html`: agora **PRESERVA** as chaves da sessão offline (`userData`, `lastLoginTime`, `accessToken`, `refreshToken`, `sigesc_csrf_token`, `activeMantenedoraId`) ao limpar SW/caches. O reset deixa de destruir o acesso offline.
- `AuthContext.js`: `MAX_OFFLINE_SESSION` 7 → **30 dias** (uso em campo).
- `pages/Login.js`: painel **"Diagnóstico da sessão offline" sempre visível** (online e offline) mostrando Conexão, Sessão salva (SIM/NÃO), idade do último login, e-mail salvo e a versão do build — autodiagnóstico sem precisar de console.
- SW bump v2.12.2 → **v2.12.3** (cache v17).
**Validação (preview):** painel mostra "NÃO" sem sessão e "SIM ✓ / há 0.0 dias / e-mail" após login online. As correções anteriores (sem wipe automático em revogação/bootstrap, sem deadlock de refresh) seguem validadas.

## CHANGELOG — P0 (correção definitiva): sessão offline apagada por "revogado" + deadlock de refresh (Jun/2026)
**Sintoma persistente (pós-deploy v2.12.0):** mesmo com `userData` presente e login de 0 dias, o login offline retornava "Faça login online primeiro". Diagnóstico no dispositivo confirmou v2.12.0 no ar.
**Causa raiz (dupla, descoberta com o cenário real de MÚLTIPLAS ABAS):**
1. **Wipe por "revogado":** o `401` de qualquer request (ex.: `/api/mantenedora` na própria tela de login) dispara o interceptor → `refreshAccessToken`. Com várias abas, a ROTAÇÃO do refresh token gera corrida: uma aba rotaciona e revoga o jti antigo; a outra usa o antigo → backend responde "Refresh token revogado" (auth.py:199). O código então fazia `logout() → clearApplicationState() → localStorage.clear()`, apagando `userData`/`lastLoginTime`. → login offline falhava.
2. **Deadlock de refresh:** o `401` do PRÓPRIO `/auth/refresh` era interceptado e, com `isRefreshing=true`, ficava aguardando (`addRefreshSubscriber`) um refresh que nunca completava → `loadUser` travava → tela presa em "Carregando...".
**Correções (`contexts/AuthContext.js`) — conforme diretriz "SOMENTE logout MANUAL invalida a sessão local":**
- `refreshAccessToken`: REMOVIDO o `logout()` automático em "revogado". Em qualquer falha, apenas retorna null (sessão offline preservada).
- `loadUser`: REMOVIDO o ramo `explicitlyRevoked → logout()`. Qualquer falha de `/auth/me` preserva a sessão offline cacheada; nunca faz wipe.
- Response interceptor: ISENTA `/auth/login|register|refresh` do retry-on-401 (evita o deadlock) e, quando o refresh falha, LIBERA todos os subscribers em espera (`cb(null)` → rejeitam) para não travar requests pendentes.
- Diagnóstico adicionado no caminho de falha do login offline (distingue ausente vs expirado >7 dias no console).
- SW bump v2.12.0→v2.12.1 (cache v14→v15) para forçar atualização e permitir confirmação por console.
**Validação (Playwright, preview):** login online → forçar `/auth/me=401` e `/auth/refresh=401 "Refresh token revogado"` (onLine=true) → reload → **userData preservado + painel renderizado, sem travar**. PASS. (Antes: apagava tudo / travava em "Carregando".)
**Deploy:** "Save to Github" → Coolify. No dispositivo, após o deploy: a nova versão (v2.12.1) assume; se necessário, 1x `reset.html` + login online para repovoar; depois o offline persiste.


**Sintoma:** offline numa rota nunca aberta online → `Loading chunk 5692 failed`, quebrando o PWA.
**Causa raiz:** o `sw.js` (install) só pré-cacheava `offline.html`, `manifest.json` e `index.html`. Os ~101 chunks JS das rotas `lazy()` só entravam no cache se a rota fosse visitada online antes.
**Correção (Opção A aprovada pelo usuário):**
- `frontend/public/sw.js`: nova função `precacheBuildAssets(cache)` chamada no `install` — lê `/asset-manifest.json` do Webpack e pré-cacheia TODOS os `.js`/`.css` (exclui `.map`) com `cache.add` individual + `allSettled` (um 404 não aborta o install). Bump `CACHE_NAME` v13→v14 (invalida cache antigo no `activate`). Ciclo de vida revisado: `skipWaiting()` (install), `clients.claim()` + delete de caches != v14 (activate), reload único em `controllerchange` (OfflineContext). Tolerante: em dev (sem asset-manifest) apenas loga e pula.
- `frontend/src/App.js`: wrapper `lazy()` com retry anti-loop — em `ChunkLoadError`/"Loading chunk X failed" recarrega a página UMA vez (guard de 10s em sessionStorage) para puxar o index/manifest novos após deploy.
**Impacto de armazenamento:** ~4,53 MB (102 arquivos js+css; `.map` de 16,6 MB excluídos). Seguro (relatório em `/app/memory/RELATORIO_IMPACTO_CACHE_CHUNKS.md`).
**Validação:** build de produção compila; `sw.js` sintaxe ok; filtro do precache seleciona 102 arquivos cobrindo os entrypoints; app dev (lazy wrapper) funciona. ⚠️ A navegação offline em rota nunca visitada só pode ser validada em runtime APÓS o deploy de produção (Coolify), pois o preview roda em modo dev (sem asset-manifest/chunks hasheados).
**Deploy:** "Save to Github" (Coolify).


## CHANGELOG — P0: Preservação da sessão offline no bootstrap (Jun/2026)
**Sintoma:** após logar online, ao reabrir o SIGESC sem internet (ou com Wi-Fi sem internet/backend fora), a sessão não era reconhecida e aparecia "Sem conexão... Faça login online primeiro". Logs mostravam `/api/auth/refresh → 401`.
**Causa raiz (`contexts/AuthContext.js::loadUser`):** o bootstrap confiava em `navigator.onLine` (otimista — true em LAN sem internet). Ao falhar `GET /auth/me` ou `POST /auth/refresh` (401/erro de rede), o catch chamava `logout() → clearApplicationState() → localStorage.clear()`, **apagando `userData`/`lastLoginTime`/tokens** → sessão offline destruída.
**Correção (frontend-only, auth):**
- `loadUser` agora só faz logout real em **revogação explícita** do servidor (401 com `detail` contendo `revog/revoked`). Em erro de rede/timeout/backend fora/401 por expiração → **mantém a sessão offline cacheada** (`isOfflineSession=true`), sem wipe. Offline sem cache → apenas `setUser(null)` (sem wipe).
- Recuperação automática offline→online: `refreshAccessToken` em sucesso faz `setIsOfflineSession(false)`; refresh proativo volta a rodar mesmo em modo offline transitório (só age `isOnline()`).
- Revisados todos os logouts: os de `Layout/Vaccine/Associal` são manuais (mantidos); removidos os `logout()` automáticos do bootstrap; `localStorage.clear()` agora só ocorre em logout MANUAL ou login novo.
**Validação (Playwright, preview):** (1) backend bloqueado com `onLine=true` → sessão preservada em /dashboard; (2) `set_offline(true)` → sessão offline restaurada. Ambos PASS.
**Pendente:** P0 dos chunks/lazy loading (`sw.js` não pré-cacheia chunks do `asset-manifest.json`).


## CHANGELOG — Fix: frequência divergindo do horário no sábado letivo (Jun/2026)
**Sintoma:** ao lançar frequência num sábado letivo, aparecia "Nenhuma aula deste componente neste dia da semana" / "não há aulas previstas para esta data", mesmo o Horário de Aulas mostrando corretamente (ex.: "5º Sábado Letivo (Aulas de Sexta)").
**Causa raiz:** o endpoint `GET /api/attendance/schedule-classes-count` (`routers/attendance.py`) retornava `count:0` para qualquer sábado, sem aplicar a rotação do sábado letivo (o horário aplicava; a frequência não → divergência).
**Correção:** o endpoint agora detecta sábado letivo via `get_saturday_weekday_map` e conta os slots do componente no **dia da semana correspondente** (mesma rotação 1º=Seg…5º=Sex). Sábado não-letivo e domingo continuam com 0. Carga horária semanal agregada (linhas ~1408/1585) não muda (estimativa semanal, não por data).
**Teste:** `tests/test_sabado_letivo.py::test_schedule_classes_count_sabado_letivo` (verde) — count = nº de aulas do dia correspondente. Total 3 testes verdes.
**Deploy:** "Save to Github" (Coolify).


## CHANGELOG — Sábado Letivo tratado como dia letivo normal (Jun/2026)
**Objetivo:** sábado marcado como `sabado_letivo` deve gerar aulas, frequência, carga horária, diário e relatórios como qualquer dia letivo.
**Causa raiz:** o diário expandia a grade horária casando apenas `isoweekday`. Como a grade só tem Seg–Sex, o sábado (dia 6) nunca casava → nenhuma aula no sábado letivo (apesar da contagem de dias letivos já incluí-lo). A regra de rotação (1º sábado=Seg, 2º=Ter…) existia só na visualização da grade (`get_saturday_schedule`), não no diário/frequência/carga.
**Decisão do cliente:** opção (a) — manter a rotação automática e propagá-la a todas as áreas.
**Correção:**
- Novo helper `services/school_calendar_helper.get_saturday_weekday_map(db, academic_year, mantenedora_id, school_id)` → `{sabado_iso: isoweekday_correspondente (1-5)}`, indexando TODOS os sábados letivos do ano (estável p/ qualquer período). Ciclo Seg–Sex (`index % 5 + 1`).
- Aplicado em `routers/calendar_diary_state.py` e `services/diary_snapshot_service.py`: `effective_wd = saturday_map.get(iso, day.isoweekday())` ao casar slots. Isso alimenta automaticamente diário, frequência (chamada habilitada no sábado), carga horária (`expected_slots`) e relatórios/dashboards (data-driven).
- Áreas 2 (frequência) e 5 (relatórios) cobertas transitivamente: `attendance.py` já permitia chamada em sábado letivo; PDFs leem registros reais + contagem de dias já incluía sábados.
**Testes:** `tests/test_sabado_letivo.py` (2 verdes) — rotação cíclica `[1,2,3,4,5,1]` e diary-state mostrando aulas no sábado letivo (controle: sábado comum = 0 aulas).
**Deploy:** "Save to Github" (Coolify).


## CHANGELOG — Fix CORS de produção (origem do frontend não permitida) (Jun/2026)
**Sintoma (produção real):** preflight CORS bloqueado em TODAS as rotas (`/api/mantenedora`, `/api/auth/login`) — "Response to preflight request ... does not have HTTP ok status" — origem `https://sigesc.aprenderdigital.top` chamando `https://api.sigesc.aprenderdigital.top`.
**Causa raiz:** o backend de produção só tinha o domínio `api.` na whitelist (provavelmente via `REACT_APP_BACKEND_URL`). O domínio do FRONTEND (`sigesc.aprenderdigital.top`) não estava permitido → Starlette CORS retorna 400 no preflight de origem não permitida. (O preview usa ingress com CORS `*`, por isso o problema não aparecia lá.)
**Correção (`server.py`):** derivação automática do domínio do frontend a partir do backend no padrão `api.<dominio>` → `<dominio>`. Assim, com apenas `REACT_APP_BACKEND_URL=https://api.sigesc.aprenderdigital.top`, o `https://sigesc.aprenderdigital.top` passa a ser whitelisted. (Validado em isolamento.)
**Ação do usuário (uma das duas):**
- IMEDIATO (sem redeploy de código): no Coolify do serviço BACKEND, definir `CORS_ORIGINS=https://sigesc.aprenderdigital.top` (ou `CORS_ORIGIN_REGEX=https://([a-z0-9-]+\.)?aprenderdigital\.top`) e reiniciar o container.
- DEFINITIVO: "Save to Github" → Coolify pull (o fix de derivação resolve sem env extra).


## CHANGELOG — P1: Login universal + reset de estado (Jun/2026)
**Sintoma:** após super_admin trocar de mantenedora e fazer logout, o login passava a falhar com "Erro ao fazer login" NO MESMO navegador, mas funcionava em aba anônima/outro navegador.
**Causa raiz:** (1) o logout NÃO limpava `activeMantenedoraId` do localStorage; (2) o interceptor do axios injetava o header `X-Mantenedora-Id` em TODA request, inclusive no POST `/auth/login`; (3) `X-Mantenedora-Id` NÃO estava no CORS `allow_headers` do backend. Em produção (frontend ≠ backend), o preflight CORS do login falhava → "Erro ao fazer login". Aba anônima não tinha `activeMantenedoraId` → funcionava.
**Correções (arquitetura "login universal"):**
1. **Backend CORS** (`server.py`): adicionado `X-Mantenedora-Id` ao `allow_headers`.
2. **Login pristino** (`services/api.js` + `AuthContext.js`): requests para `/auth/login`, `/auth/register` e `/auth/refresh` NUNCA herdam token/tenant/CSRF anteriores.
3. **`clearApplicationState()`** (`services/api.js`): reset total de localStorage+sessionStorage. Chamado no logout (estado de "primeira visita") e no login bem-sucedido (descarta contexto de usuário/tenant anterior → troca de usuário limpa).
**Validação (browser, cenários do cliente):** (a) estado obsoleto injetado → login 200 + `activeMantenedoraId` limpo; (b) logout → localStorage vazio `[]` + redirect /login. Critérios de aceite 1–5 atendidos.
**Deploy:** subir via "Save to Github" (Coolify).


## CHANGELOG — P0 CRÍTICO: Isolamento Multi-Tenant blindado (Jun/2026)
**Vulnerabilidade:** gerentes (e qualquer não-super_admin) começavam corretos mas, após ~15min, passavam a ver dados de OUTRA mantenedora ("mudança de contexto").
**Causa raiz (confirmada):** `POST /api/auth/refresh` (routers/auth.py) reconstruía o access token SEM o claim `mantenedora_id` (o `/login` incluía). Após o refresh, `get_current_user` lia `mantenedora_id=None` → `apply_tenant_filter` deixava de filtrar (via TUDO) e `resolve_active_mantenedora` caía na PRIMEIRA mantenedora.
**Correções (todas aprovadas pelo cliente, P0):**
1. **Raiz:** `/refresh` agora preserva `mantenedora_id` (+ role/school_ids), idêntico ao `/login`. (verificado via decode do token)
2. **FAIL-CLOSED (padrão da plataforma):** `tenant_scope.apply_tenant_filter` — não-super_admin sem `mantenedora_id` recebe filtro impossível `mantenedora_id=__INVALID_TENANT__` (sem tenant = ZERO dados, nunca todos). Mesma blindagem aplicada em `routers/users.py` (list + count, que filtravam manualmente).
3. **`resolve_active_mantenedora`:** nunca cai na "primeira mantenedora" para não-super_admin (só super_admin); escopo apontando a tenant inexistente → None.
4. **Auditoria permanente:** novo `tenant_audit.py` + coleção `tenant_security_events`. Loga APENAS divergências: `missing_tenant`, `tenant_mismatch`, `cross_tenant_attempt`, `invalid_token` (JSON: user_id, role, user_mantenedora, requested_mantenedora, endpoint, método, timestamp). Log + persistência best-effort.
5. **Testes automatizados:** `tests/test_multi_tenant_isolation.py` (cenário Mantenedora A/B: refresh preserva tenant; A só vê A, B só vê B; token sem tenant → 0 resultados). `tests/test_tenant_scope_resolver.py` atualizado para o comportamento seguro.
**Arquivos:** routers/auth.py, tenant_scope.py, tenant_audit.py (novo), auth_middleware.py, routers/users.py.
**Validação:** todos os testes de tenant relevantes verdes. Falhas remanescentes no harness (test_tenant_admin/phase2) são PRÉ-EXISTENTES (CSRF ausente no harness em POST e dado `nivel_ensino:'INFANTIL'`), não relacionadas. Smoke test da UI OK.
**Deploy:** subir via "Save to Github" (Coolify) — correção P0, deploy imediato recomendado.


## CHANGELOG — Fix: células P/F/J em branco no PDF de Frequência (Jun/2026)
**Bug:** no PDF "Controle de Frequência" por bimestre, um ou dois alunos ATIVOS apareciam com todas as células P/F/J em branco (ex.: aluna Eloah Botelho Ferreira, turma "Pré I A"), mesmo tendo frequência lançada na tela.
**Causa raiz:** o recurso (Fev/2026) que apaga células a partir da `action_date` de alunos que SAÍRAM da turma (`student_history`: transferencia_saida/remanejamento/progressao/reclassificacao/desistencia/cancelamento) também atingia alunos que continuam ATIVOS na turma mas possuem um registro histórico ANTIGO para aquela turma — caso típico de aluno cancelado/remanejado e depois REMATRICULADO na mesma turma. Com a `action_date` antiga, todas as frequências posteriores eram omitidas.
**Fix (`routers/attendance_ext.py`):** monta `active_in_class_ids` (matrículas ativas + alunos com class_id direto) e NÃO aplica o apagamento por `action_date` a alunos ativos na turma. Mantém o comportamento correto para alunos genuinamente inativos (Fonte 2).
**Testes:** `tests/test_attendance_pdf_blank_cells_regression.py` (1 verde — valida via pdfplumber que aluno ativo com histórico de cancelamento antigo renderiza "P P", FALTAS=0/PRESEN.=2). Verificado também o caso real-simulado no preview. Deploy via "Save to Github".


## CHANGELOG — Tutorial de Transferência: capturas reais (Jun/2026)
**Aprimoramento:** o tutorial "Transferir um Aluno de uma Escola para Outra" (`/tutoriais/secretarios/transferencia`) passou a incluir 4 capturas de tela reais do sistema, inseridas em cada passo:
- `transf-1-lista.png` — tela Alunos com escola selecionada (Editar)
- `transf-2-acoes.png` — aba Turma/Observações com o seletor "Ação"
- `transf-3-transferir.png` — modal "Transferir Aluno" (motivo, data, confirmar)
- `transf-4-matricular.png` — modal "Matricular Aluno" (escola/turma/ano de destino)
**Como foram geradas:** script Playwright temporário percorreu o fluxo real logado (admin) e salvou os PNGs em `frontend/public/tutorials/`. Aluno de teste criado/excluído via API (sem resíduo). Validado: as 4 imagens carregam (naturalWidth=1280) na página.


## CHANGELOG — Bolsa Família: lista de transferidos no PDF (Jun/2026)
**Aprimoramento:** no PDF do "Acompanhamento Bolsa Família", antes da assinatura, passa a exibir a seção **"Alunos Transferidos no Período"** com colunas: Nome do Estudante, Data da Transferência e Situação/Escola de Destino.
**Regras:** lista os alunos BF com `transferencia_saida` da escola (ou da turma, quando o filtro de turma está aplicado) no ano letivo do relatório. Destino = matrícula ATIVA atual do aluno: se estiver ativo em OUTRA escola da rede → exibe o nome da escola; caso contrário → "Fora da rede". Transferências canceladas (aluno voltou à escola de origem) são omitidas.
**Arquivos:** `routers/bolsa_familia.py` (coleta em `generate_bolsa_familia_pdf` + render em `_generate_bf_pdf`).
**Validação:** PDF 200; extração confirmou os 2 caminhos — "Escola Demo Portal" (rede) e "Fora da rede" — com a assinatura logo após.
**Bug descoberto (NÃO corrigido — fora de escopo):** `POST /api/students/{id}/transfer` retorna HTTP 500 por serialização de ObjectId no retorno (`new_enrollment` mutado pelo `insert_one`), embora os dados sejam gravados. Recomendado corrigir (retornar doc sem `_id`).


## CHANGELOG — Bolsa Família: PDF institucional + coluna Faltas (Jun/2026)
**3 aprimoramentos no "Acompanhamento Bolsa Família":**
1. **PDF institucional** (`_generate_bf_pdf` em `routers/bolsa_familia.py`): cabeçalho com brasão/logotipo da mantenedora + nome + secretaria + slogan (mesmo padrão dos demais documentos do sistema, via `get_logo_image`). Título "Acompanhamento de Frequência Escolar — Programa Bolsa Família".
2. **Identificação da turma no PDF**: quando o filtro `class_id` é aplicado, o PDF passa a exibir uma linha "Turma: {nome} ({série})" no bloco da escola.
3. **Coluna "Faltas" (somente na tela)**: em `frontend/src/pages/BolsaFamilia.js`, entre as colunas Mês e Frequência, exibindo `months[m].absences` (faltas válidas somadas no mês, em âmbar quando > 0). NÃO reproduzida no PDF.
**Validação:** PDFs com/sem turma geram 200; extração confirmou cabeçalho institucional + "Turma Multi 1-2-3 (1º ANO)". Screenshot confirma a coluna FALTAS na tela. Deploy via "Save to Github".


## CHANGELOG — Fix P0: "Network Error" ao remanejar aluno (Jun/2026)
**Bug:** `PUT /api/students/{id}` com mudança de `class_id` (remanejamento) retornava HTTP 500 ("Network Error" no front).
**Causa raiz:** ao criar a nova matrícula, o backend carregava o MESMO `enrollment_number` da matrícula de origem. Como existe índice único global `uq_enrollment_number` (partial: `enrollment_number > ''`) e a matrícula antiga (agora `relocated`) ainda mantinha esse número, o `insert_one` quebrava com `DuplicateKeyError`.
**Fix (`routers/students.py` ~1617-1665):** o número de matrícula (identidade do aluno) é transferido para a NOVA matrícula ativa; o número da matrícula de origem é liberado (`enrollment_number=""`) e preservado em `previous_enrollment_number` para auditoria. Insert protegido com try/except → 409 amigável. Regras de remanejamento/progressão/reclassificação preservadas.
**Testes:** `tests/test_relocate_student_regression.py` (2 verdes — retorna 200, número preservado, histórico registra remanejamento).
**Deploy:** subir via "Save to Github" (Coolify puxa do repositório).


## CHANGELOG — Indicadores da Rede: reconciliação de contagens (Fev/2026)
**Bug:** No painel "Indicadores da Rede" (página Alunos), a soma por SÉRIE e por COR/RAÇA não fechava com o total de ativos, em todas as escolas.
**Causa raiz:** a contagem por série exigia correspondência EXATA com rótulos fixos do front (ex.: cadastro `PRÉ-ESCOLA I` não casava com `Pré I`) → alunos sumiam; alunos sem cor/raça não apareciam.
**Correção (aprovada pelo usuário, testada 100%):**
- Canonicalizador robusto `backend/utils/serie_canonical.py` (`canonicalize_serie`): normaliza acentos/caixa/hífens/ordinais + aliases (`PRÉ-ESCOLA I/II`→`Pré I/II`, `Berçário`, `Maternal`, `1º..9º Ano`, `1ª..4ª Etapa`); detecta nível II antes de I; nomenclaturas desconhecidas (Creche, Jardim, "Maternal III", "Prézinho") → `None`.
- `GET /api/students` agrupa por série, canonicaliza e devolve `series_counts` (chaves UPPER), `unmapped_series` (raw→qtde) e contabiliza os não mapeados em `SÉRIE NÃO RECONHECIDA`. **Invariante garantida:** `sum(series_counts) == active_count`. Log de auditoria (`logger.warning`) das séries não mapeadas.
- `race_counts` inclui bucket `nao_informada`.
- Frontend (`StudentsComplete.js`): chip laranja "Não informada: N" (`data-testid=race-nao-informada`) em Cor/Raça; bloco vermelho "Série não reconhecida: N" (`data-testid=series-nao-reconhecida`) listando as nomenclaturas brutas.
- Testes: `tests/test_serie_canonical.py`, `tests/test_network_indicators_reconciliation.py` (19 passed no total). Validado pelo testing agent (iteração 83) — reconciliação confirmada nas 6 escolas.
- Rota frontend correta: `/admin/students`.
- *Dívida técnica anotada:* `StudentsComplete.js` >3800 linhas — recomendado quebrar em componentes (IndicadoresPanel, FiltrosBar, ListaAlunos).


## CHANGELOG — Boletim Online + Status Conceitual (Fev/2026)
**Boletim Online do Aluno (`/api/student/me/report-card` + `BoletimAluno.jsx`):**
- Tabela numérica (3º-9º/EJA): `Componente | 1º Bim | 2º Bim | Rec 1 | 3º Bim | 4º Bim | Rec 2 | Média | Situação` (removidas Faltas/Rec Final/Final).
- Média ponderada oficial `(B1×2 + B2×3 + B3×2 + B4×3)/10`. Rec semestral substitui a MENOR nota do semestre; em EMPATE substitui a de MAIOR peso (B2 no 1º sem, B4 no 2º sem) e só se a rec for maior. Campos vazios = 0.
- Turmas conceituais (Ed. Infantil + 1º/2º ano): Média = MAIOR conceito; tabela com B1-B4 + Média + Situação.
- Alinhado tie-break em `gradeHelpers.jsx` (`<=`→`<`) para consistência com a tela de lançamento.

**Padronização SYSTEM-WIDE do status de turmas CONCEITUAIS** (Ed. Infantil + 1º/2º ano), aplicada em Boletim Online, Boletim PDF, Ficha Individual, Livro de Promoção e tela de Promoção:
- Durante o ano (nem todas B1-B4 lançadas) = **"Em andamento"**.
- Ao encerrar (todas as 4 notas/conceitos lançadas, ignorando componentes nunca avaliados) = **"Concluiu a etapa"** (Ed. Infantil) / **"Promovido(a)"** (1º/2º ano).
- Status especiais (transferido/desistente/falecido) sempre prevalecem.
- Centralizado em `grade_calculator.determinar_resultado_documento` (constantes `STATUS_EM_ANDAMENTO/CONCLUIU_ETAPA/PROMOVIDO`).
- Correções de consistência: `documents.py` (Livro) agora resolve componentes igual ao Boletim (merge de `courses_map` com componentes das notas); defaults de `academic_year` alinhados para 2026 (Livro GET/job, Ficha, Batch) — divergência anterior era por ano default 2025 vs dados 2026.
- Testes: `/app/backend/tests/test_status_conceitual.py` (9 passed). Verificação por extração de PDF (Livro + Ficha → "Promovido(a)" em 2026).


## Multi-Tenancy Architecture
- Collection `mantenedoras` (plural) é a fonte definitiva de dados de tenants
- Collection legacy `mantenedora` (singular) foi removida
- Row-Level Security via `tenant_scope.py` (`apply_tenant_filter`)
- Super_admin tem acesso cross-tenant e ignora RLS quando sem header `X-Mantenedora-Id`
- Frontend: `TenantSwitcher` + `TenantSyncBoundary` permitem troca fluída sem reload

## Implemented Features (histórico)


### Grade Horária — Fase 2: Migração definitiva `class_schedules` → `teacher_class_assignments` **[Fev/2026]** ✅ LOCAL (pronto p/ deploy + piloto)

Corrige a MODELAGEM do anti-pattern WRITE!=READ (a Fase 1/hotfix corrigiu só
a leitura via dual-read). Persiste a grade legacy no modelo novo como fonte
única da verdade. Estratégia aprovada pelo owner: curto prazo = compat;
médio = fonte única; longo = remoção controlada do legado.

**Transform:** reutiliza `services.legacy_schedule_bridge.build_assignments_from_legacy`
(validado nas Fases 9/10 do Diário). ZERO regra nova de mapeamento.

**HARD INVARIANTS:**
1. NUNCA toca turma com assignment REAL no modelo novo (`source != legacy_migration`).
2. Id determinístico `legacy::{class}::{course}::{teacher}` → re-rodar não duplica.
3. Apply FALHA (422 `UNEXPECTED_DETERMINISTIC_DUPLICATE`) se id colidir com doc não-migração.
4. Rollback apaga só docs criados pela migração com CAS rigoroso (`updated_at == created_at`).

**Marcadores no doc criado:** `source="legacy_migration"`, `migrated_from_legacy=True`,
`migration_run_id=<run_id>`, `synthetic_validity=True`, vigência sintética
`{ano}-02-01`→`{ano}-12-31`.

**Endpoints (super_admin, envelopados por `with_critical_mutation`):**
- `GET  /api/admin/grade/legacy-migration/preview?academic_year&school_id&class_id`
  → total turmas afetadas, total assignments a criar, breakdown por escola,
    turmas ignoradas (já têm modelo novo) + amostra, 5 docs sintetizados.
- `POST /api/admin/grade/legacy-migration/apply` (`dry_run=true` default; scope
  `school_id`/`class_id`/`academic_year` p/ rollout faseado/piloto). Retorna
  `diagnostic_before/after`, `legacy_only_dropped`, `without_any_delta`,
  `diagnostic_ok`, `elapsed_seconds`, `throughput_docs_per_sec`.
- `GET  /api/admin/grade/legacy-migration/runs[/{run_id}]`
- `POST /api/admin/grade/legacy-migration/runs/{run_id}/rollback` (relatório final).

**Coleções novas (on-demand):** `grade_legacy_migration_runs` / `_locks` / `_idempotency`.

**NÃO removido (compat mantida):** dual-read do painel, bridge legacy, compat
Diário e Attendance. Remoção controlada = sprint futuro pós-validação prod.

**Arquivos:**
- ✨ `/app/backend/services/grade_legacy_migration_service.py`
- ✨ `/app/backend/routers/grade_legacy_migration.py`
- 📝 `/app/backend/server.py` (registro do router)
- ✨ `/app/backend/tests/test_grade_legacy_migration.py` (8 testes)

**Validação:** 8/8 testes verdes (preview, apply idempotente, dry-run, invariante
de não-sobrescrita, duplicidade determinística aborta, rollback c/ CAS, rollback
preserva doc editado manualmente, filtro por escola). Lint limpo. E2E HTTP:
login→CSRF→preview→dry-run apply OK (na base local 11 turmas já têm modelo novo
→ corretamente ignoradas; nada migrado). Endpoints respondem 401 sem auth.

#### Bugfix P0 [Fev/2026] — 500 "ObjectId não serializável" em apply multi-turma
- **Causa raiz:** `insert_many` do Motor MUTA os dicts de entrada injetando
  `_id` (ObjectId). Como `sample_synthesized` da resposta referenciava esses
  mesmos dicts, o ObjectId vazava no payload e o FastAPI `jsonable_encoder`
  quebrava (500) — SOMENTE quando `created>0` (apply com inserção real);
  dry_run e re-runs idempotentes retornavam 200. Disparava em escolas
  multi-turma (mais docs inseridos).
- **Impacto:** os dados ERAM gravados e a auditoria (`record_run`) ERA
  persistida ANTES do erro (a falha era só na serialização da resposta HTTP).
  Nenhuma corrupção; rollback continua possível pelos run_id já gravados.
- **Fix:** `insert_many([dict(c) for c in pending])` (insere cópias; originais
  ficam livres de `_id`). + Preview agora desconta já-migrados
  (`already_migrated_assignments`) → `total_classes_affected` reflete o
  progresso REAL (antes ficava preso em 118).
- **Testes:** `test_apply_multi_class_no_objectid_leak`,
  `test_preview_excludes_already_migrated` (10/10 verdes).
- **Pós-fix em prod (pré-deploy):** ~34 turmas já migradas com sucesso
  (legacy_only 120→86) apesar dos 500 cosméticos.

#### ✅ CONCLUÍDA EM PRODUÇÃO [30/Mai/2026]
Rollout faseado executado (piloto → lote pequenas/médias → 5 grandes individuais).
Resultado final: **1182/1182 assignments migrados**, `legacy_only` 120→2,
`faltam (turmas): 0`. Os 2 `legacy_only` remanescentes são turmas com
`class_schedules` SEM slots úteis (grade vazia na origem — nada a migrar).
Todos os applies retornaram 200 limpo pós-fix; idempotência confirmada
(re-runs `created=0`). PENDENTE: validação operacional do usuário (painel
"Ver Conflitos da Rede" + spot-check de Diários) e período de observação
antes da Fase 3.


### Bolsa Família — Análise de Impacto da Consolidação Diária **[Fev/2026]** ✅ PRONTO P/ VALIDAÇÃO EM PROD

Regra nova (já em `attendance_utils.compute_monthly_valid_absences`):
consolidação diária — presença em **≥ 50%** das aulas do dia torna o dia
inteiro PRESENTE; < 50% conta 1 falta. Validado: 35/35 testes unitários
verdes (consolidação + frequência canônica + suggestion). Zero regressão no
domínio BF.

**Achados estatísticos (analíticos):**
- **Monotonicidade**: o método novo NUNCA reduz a frequência vs o antigo —
  só aumenta ou mantém. (Dia mono-componente = idêntico; dia multi-componente
  = no máx. 1 falta/dia vs N faltas/dia antes.) Qualquer delta negativo é
  anomalia e é sinalizado pelo script.
- **Correção de unidade**: o método ANTIGO somava faltas POR COMPONENTE
  contra um denominador POR DIA (`school_days`) — descasamento de unidade que,
  em turmas `by_course` (Anos Finais/EM), podia gerar frequência absurdamente
  baixa/negativa. O novo método alinha numerador e denominador em DIAS.

**Análise regulatória (PBF):**
- Limiares de condicionalidade: **60%** (4–5 anos) e **75%** (6–17 anos),
  apurados mensalmente via Sistema Presença MEC.
- O corte de **≥50%/dia é regra de negócio LOCAL** (decisão do owner), NÃO
  norma MEC — precisa ser defensável em auditoria.
- Impacto: frequências reportadas SOBEM → alunos podem migrar de
  "descumprimento" → "cumprimento". Benéfico onde o número antigo estava
  errado (by_course); risco de SUPER-reporte se o MEC esperar apuração por
  carga horária em grades fracionadas. Revisar `crossed_threshold` antes do
  ciclo oficial.

**Ferramenta de validação em prod (read-only):**
`/app/backend/scripts/bf_consolidation_impact.py [ANO]` — compara método
antigo vs novo sobre a base real e reporta: student-meses alterados, delta
médio/máx, deltas negativos (anomalias) e nº de alunos que cruzam o limiar
PBF, com ranking por escola. Saída JSON em
`/app/test_reports/bf_consolidation_impact_<ANO>.json`. NÃO escreve nada.


### Fix 500 em `/api/curriculum/adaptations/availability` **[Fev/2026]** ✅ EM PROD

**Causa raiz:** `_require_any_auth` em `routers/curriculum_v2.py:38` chamava
`AuthMiddleware.require_permission(db, 'nav-curriculum-button', None)`. Para
usuários **não super_admin sem override na Matriz**, o middleware caía no
fallback `require_roles(None)`, executando `effective_role not in None` →
`TypeError: argument of type 'NoneType' is not iterable`. Bug existia desde
a criação do router v2 e só disparava para roles não-admin (super_admin tem
bypass na linha 142 do middleware).

**Auditoria global:** verifiquei TODOS os 80+ call sites de `require_permission`
no projeto — apenas `curriculum_v2.py:38-40` usava `None`. Confirmado que o
padrão NÃO se repete em nenhum outro router.

**Fix aplicado (Opção B — local, conservadora):**
- `/app/backend/routers/curriculum_v2.py::_require_any_auth` reescrito para
  replicar a lógica de Matriz LOCALMENTE, com semântica explícita de
  "permissivo por default" (qualquer autenticado passa, override negativo
  é honrado).
- **Zero alteração** em `auth_middleware.py` — preservada a policy global
  de segurança (decisão do owner: "middleware global não deve mudar
  semântica de segurança por causa de bug local").

**Testes (6 novos em `tests/test_curriculum_v2_auth_regression.py`):**
- super_admin bypass (sem consulta DB)
- non-admin sem override → passa (regressão principal do bug)
- non-admin com override `visible=False` → 403
- non-admin com override `visible=True` → passa
- override de role diferente não afeta usuário atual
- falha na consulta Mongo → fail-open (não bloqueia leitura)

**Validação:** 41/41 testes verdes · lint limpo · backend reload OK · route
responde 401 sem auth (correto).


### Fix Painel Integridade da Grade — `class_schedules` vs `teacher_class_assignments` **[Fev/2026]** ✅ LOCAL

**Causa raiz (anti-pattern WRITE_PATH != READ_PATH):**
A UI atual de cadastro de grade horária ("Horário de Aulas") grava na
coleção legacy `class_schedules`. O painel "Integridade da Grade Horária"
e o serviço `grade_integrity_service.py` liam APENAS a coleção nova
`teacher_class_assignments`, que está ~vazia em prod. Consequência: ~todas
as turmas ativas viravam falso positivo CLASS_WITHOUT_ASSIGNMENT severidade
crítica → ruído operacional + risco da equipe "corrigir" turmas que já
estavam corretas.

**Caminho C aprovado pelo owner ("sem hesitar"):**
1. ✅ **HOTFIX B** (hoje): painel passa a considerar AMBAS as coleções
   como fontes de "tem grade?" (`legacy ∪ novo`). Modo híbrido temporário,
   marcado como débito arquitetural explícito.
2. ✅ **Diagnóstico read-only** (hoje): endpoint dedicado mapeia o gap.
3. ⏳ **Migração definitiva** (sprint dedicado, NÃO agora): legacy → novo
   via `with_critical_mutation` + dry-run + rollback contract.

**Arquivos alterados:**
- `/app/backend/services/grade_integrity_service.py:341-393`:
  união de `class_schedules.distinct("class_id")` + assignments. Guarda
  `try/except` se coleção legacy não existir (ambiente novo).
- `/app/backend/routers/maintenance.py`: novo endpoint
  `GET /api/admin/maintenance/schedules-write-read-diagnostic` retornando
  5 buckets (both / legacy_only / new_only / without_any) + amostra de
  turmas realmente sem grade + interpretação automática
  (`anti_pattern_detected`, `migration_safe`, `real_missing_schedule_count`).
- `/app/backend/tests/test_grade_integrity.py`: novo teste de regressão
  `test_class_with_legacy_class_schedule_NOT_flagged` (12/12 verdes).

**Validação local:** lint limpo, backend supervisord saudável, endpoint
retorna 401 sem auth (correto), 12/12 testes do grade_integrity verdes.



### Dependência de estudos em turma multisseriada — seletor de série **[Fev/2026]** ✅ LOCAL

**Problema:** modal "Vincular componente em dependência" lista componentes
de turmas multisseriadas misturando séries (ex.: turma "6º E 7º ANO MULTI"
mostra componentes do 6º e 7º junto). Coordenador/secretário não consegue
definir qual SÉRIE específica o aluno cursará na dependência.

**Solução (escopo cirúrgico, conservador):**
- Backend (`/api/classes/{id}/curriculum`): expõe `is_multi_grade`, `series`,
  e `grade_levels` em cada componente. Sem mudança de contrato — só campos
  adicionais retro-compat.
- Frontend (`StudentDependencySection.jsx::AddDependencyModal`): novo
  dropdown **"Série da dependência"** que aparece APENAS quando turma destino
  tem `is_multi_grade=true` E `series.length >= 2`. Multi com `series=[única]`
  segue caminho normal (sem ambiguidade — coerente com Sprint 1.2).
- Filtragem de componentes client-side por `grade_levels.includes(série)`.
  Componentes sem `grade_levels` (vazio) interpretados como "aplica a todas
  as séries" (defensivo, evita esconder componente legacy).
- Botão "Vincular" + select de Componente desabilitados até série ser
  selecionada (quando aplicável).
- Validação no submit + mensagem amigável.

**Modelo:** `StudentDependencyBase.target_series: Optional[str]`. Para turmas
regulares fica `None` (série efetiva já vem de `classes.grade_level`).

**Arquivos:**
- `/app/backend/routers/classes.py` — payload de `/curriculum` enriquecido
- `/app/backend/models.py` — campo novo `target_series`
- `/app/frontend/src/components/StudentDependencySection.jsx` — dropdown
  condicional + filtragem + estado `selectedSeries`

**Validação local:** 52/52 testes verdes (sem regressão), lint JS+Py limpo,
backend/frontend supervisord saudável.



### Sprint 1.2 — Backfill `student_series` **[Fev/2026]** ✅ LOCAL (pronto pra deploy)

> *Owner: "validar 1.497 processados, 0 perda de aluno, 0 null inesperado,
> distribuição coerente. Não é só rodar sem erro."*
> *Owner (rollback): "capacidade de desfazer exatamente o apply sem
> reconstrução de regra."*

Primeira aplicação real do padrão `with_critical_mutation` em escala
(esperado: 1.497 alunos com `student_series` vazio). 4 ajustes finos sobre
a proposta inicial + **rollback contract explícito**, todos aprovados pelo
owner antes de codar.

**Regras aprovadas:**
- HARD INVARIANT: NUNCA sobrescreve `student_series` preenchido (guard
  `$or [exists:False, None, ""]` no update — protege contra race).
- Categoria A (regular): `fill = classes.grade_level` — determinístico.
- Categoria B (multi `series=[única]`): só fill se outros alunos da turma
  com `student_series` preenchido bate com `series[0]` OU estão todos vazios
  (consistency check via aggregate join enrollments→students).
- Categoria C/D/E: SKIP puro (sem regex em E, sem heurística em C).
- Telemetria no aluno: APENAS `series_backfill_run_id` + `_source` +
  `_at`. Fonte primária da auditoria é a runs collection.

**Rollback contract (Sprint 1.2.R):**
Cada apply grava em `diff.rollback`:
```json
{ "type": "field_restore",
  "fields": ["student_series"],
  "telemetry_fields_to_unset": ["series_backfill_run_id", "_source", "_at"],
  "strategy": "restore_previous_value_from_snapshot",
  "reversed_by_run_id": null }
```
- Endpoint `POST /series-backfill/runs/{run_id}/rollback`:
  - 404 se run não existe; 400 se mode≠apply; 409 se já revertido
  - Para cada `diff.applied[]`, restaura `student_series` ao `from`
    + remove telemetria, com **CAS lógico** (`student_series == entry.to`)
    pra NÃO sobrescrever mudanças manuais posteriores
  - Cria novo run com `mode="rollback"` apontando ao original via
    `summary.reversed_run_id`
  - Marca run original com `diff.rollback.reversed_by_run_id`
  - Envelopado por `with_critical_mutation` (lock + idempotency)

**Arquivos novos/alterados:**
- `/app/backend/routers/student_series_backfill.py` — endpoints + lógica + rollback
- `/app/backend/server.py` — registra o router
- `/app/backend/lib/critical_mutation.py` — pré-gera `run_id` antes do
  executor (`executor(run_id)`); detecção via `inspect` mantém
  backward-compat com executors sem args
- `/app/backend/tests/test_student_series_backfill.py` — 15 testes (4 rollback)

**Endpoints:**
- `GET  /api/admin/students/series-backfill/preview` (read-only)
- `POST /api/admin/students/series-backfill/apply` (dry_run + apply)
- `GET  /api/admin/students/series-backfill/runs[/<id>]`
- `POST /api/admin/students/series-backfill/runs/{run_id}/rollback` ✨

**Coleções novas em prod (criadas on-demand):**
`student_series_backfill_runs` / `_locks` / `_idempotency`

**Validação local:** 56/56 testes verdes (15 backfill + 41 herdados),
lint limpo, backend reload OK, endpoints respondem 401.



### Sprint 1.1.E — Padrão reutilizável `with_critical_mutation` **[Fev/2026]** ✅ EM PROD

> *Owner: "se você NÃO fizer (e) agora, você está aceitando replicar manualmente
> o Sprint 1.1 em cada operação futura — dívida operacional em 2–3 sprints."*

Extração arquitetural do Sprint 1.1: as 3 camadas (idempotência + lock +
audit) viraram um padrão reutilizável em `/app/backend/lib/critical_mutation.py`.

**Arquivos novos/alterados:**
- `/app/backend/lib/__init__.py` — pacote `lib` para utilitários internos
- `/app/backend/lib/critical_mutation.py` — orquestrador + helpers genéricos
- `/app/backend/routers/dedup_enrollments.py` — refatorado para usar a lib
  (re-exports mantêm backward-compat com tests)
- `/app/backend/tests/test_critical_mutation.py` — 7 testes da abstração

**API do orquestrador:**
```python
from lib.critical_mutation import with_critical_mutation

return await with_critical_mutation(
    db, target="<seu_target>", actor=user,
    request=request, response=response,
    executor=lambda: my_work(),
    runs_collection="<your>_runs",
    locks_collection="<your>_locks",
    idempotency_collection="<your>_idempotency",
)
```

O `executor` retorna `{"mode": "...", "summary": {...}, "diff": {...}, "payload": {...}}`.
O wrapper injeta `run_id`, `started_at`, `finished_at`, `duration_ms` no payload.

**Decisões de design:**
- Coleções são parâmetros **explícitos** (não defaults mágicos) → clareza e
  preserva trilhas históricas separadas (Sprint 1.0 continua em `dedup_runs`).
- `Idempotency-Key`/lock TTL configurável via env: `CRITICAL_MUTATION_IDEMPOTENCY_TTL_HOURS` (24h), `CRITICAL_MUTATION_LOCK_TTL_SECONDS` (600).
- Re-exports em `dedup_enrollments.py` (`_normalize_created_at`, `_record_dedup_run`, `_acquire_lock`, etc.) preservam compat com 28 testes herdados.

**Pronto para reutilização imediata em (sem reescrever lógica):**
- `dedup_disabilities[]` (Sprint 1.2)
- `migrate_student_series` (Sprint 1.3)
- `delete_orphan_atendimento_aee` (Sprint 1.2)
- qualquer endpoint destrutivo futuro

**Validação:** 35/35 testes verdes · lint limpo · backend supervisord saudável
após reload · endpoints respondem 401 (auth corretamente aplicada).


### Sprint 1.1 — Hardening (Idempotência + Lock + Fingerprint) **[Fev/2026]** ✅ EM PROD

> *Owner: "o próximo risco real não é bug — é execução duplicada ou
> concorrente."*

Transforma `POST /api/admin/students/duplicate-enrollments/dedup` em operação
**determinística e re-executável com segurança**. Elimina dependência de "boa
vontade operacional" presente no Sprint 1.0.

**3 camadas implementadas em `/app/backend/routers/dedup_enrollments.py`:**

1. **Idempotency-Key (header opcional, backward-compatible)**
   - Coleção `dedup_idempotency` com índice composto único `(key, target)` + TTL `created_at`
   - TTL configurável via `DEDUP_IDEMPOTENCY_TTL_HOURS` (default: **24h**)
   - Cache hit retorna a resposta original com header `X-Idempotent-Replay: true`
   - Sem header → comportamento legacy preservado (zero breaking change)

2. **Lock distribuído por `target`**
   - Coleção `dedup_locks` (`_id = target`), TTL Mongo limpa stale (`expireAfterSeconds=0`)
   - TTL configurável via `DEDUP_LOCK_TTL_SECONDS` (default: **600s = 10min**)
   - Aquisição atômica: `replace_one` para stale ou `insert_one` para novo
   - Concorrente recebe **409** com `{lock_holder, expires_at}` no body
   - Release CAS por holder (não derruba lock de terceiros)
   - **Granular por target**: futuras operações (`dedup_disabilities`, etc.) terão locks independentes

3. **Execution fingerprint**
   - Sugestão do owner: `sha256(target + mode + UTC_day)[:16]` gravado em todo `dedup_run`
   - Telemetria de agrupamento (não substitui idempotency)
   - Permite relatórios tipo "quantos applys em dedup_enrollments hoje"

**Testes (28/28 verdes em `tests/test_dedup_enrollments.py`):**
- 4× execution fingerprint (determinismo, variação por target/mode)
- 6× lock (acquire, concurrent block, release-by-holder, takeover de expirado, granularidade)
- 5× idempotency (lookup miss/hit, race silenciosa, isolamento por target)
- + 13 testes herdados do Sprint 1.0 (canonical/datetime/envelope)

**Comportamento de resposta:**
| Cenário | HTTP | Header novo | Notas |
|---|---|---|---|
| Sem `Idempotency-Key` | 200 | — | Legacy |
| `Idempotency-Key` 1ª vez | 200 | `X-Idempotent-Replay: false` | Executa + grava |
| Mesma key, retry | 200 | `X-Idempotent-Replay: true` | Cache hit, sem reexecutar |
| Execução concorrente | **409** | — | `{lock_holder, expires_at}` |

**Não inclui (Sprint 1.2+):**
- Job periódico de detecção contínua
- Tela `/admin/audit/dedup-runs`
- Sampling de diff (postergado até > 500 itens/run)


### Sprint 1.0 — Saneamento de Matrículas Duplicadas **[Fev/2026]** ✅ FECHADO

> *Owner: "execute o apply agora, uma vez, manualmente, e valide imediatamente
> o estado no banco — não apenas o retorno da API."*

Resolveu 195 matrículas duplicadas (194 alunos afetados) com governança
auditável, validação DB-direct pré/pós e zero regressão.

**Métricas de execução em prod (26/Mai/2026):**
- baseline: 5857 alunos · 4591 matrículas ativas · 194 grupos duplicados · 0 deduped
- apply: `inactivated=195` em 599ms (run_id `6607e968-e1ad-4a47-b2d4-c4888a899e2d`)
- pós: 5857 alunos (idêntico) · 4396 ativas (=4591-195) · 195 deduped · **0 duplicados restantes** · **0 regressões**

**Regra de canonical aplicada (combo "i" aprovada pelo owner):**
1. Preferência por matrícula cujo `school_id == students.school_id`
2. Entre preferenciais, a mais recente (`created_at`)
3. Fallback: mais recente de todas

**Fix técnico que destravou o sprint:**
- `TypeError: can't compare offset-naive and offset-aware datetimes` em
  `_find_duplicate_enrollments` ao misturar `created_at` tz-naive e tz-aware
- Solução: função `_normalize_created_at` que força UTC tz-aware (módulo `routers/dedup_enrollments.py`)
- 13 testes em `tests/test_dedup_enrollments.py` (5 são regressão do bug)

**Trilha de auditoria — coleção `dedup_runs` (Sprint 1.0):**
- `run_id` (uuid único), `mode` (`dry_run|apply`), `target`, `summary`, `diff`
  (`duplicates_removed[]`, `kept_records[]`), `actor`, `environment`, timestamps
- Índices lazy: `run_id` unique + `created_at` desc + `mode` + `actor.user_id`
- Endpoints novos:
  - `GET /api/admin/students/dedup-runs?mode=&target=&limit=&skip=`
  - `GET /api/admin/students/dedup-runs/{run_id}`
- Diff completo (195 + 194 itens) ainda cabe folgado no limite de 16MB do Mongo
  (~30KB por run). **TODO v2 (pós-estabilização):** sampling + CSV anexo quando
  `would_inactivate > 500`.

**Backlog gerado pela operação:**
- 94 alunos órfãos legítimos (sem matrícula ativa): 86 `transferred`, 4 `cancelled`,
  2 `relocated`, 2 mistos. Pré-existentes — não causados pelo apply. Limpeza
  cadastral separada.
- `ENVIRONMENT=prod` não setado no Coolify (registros gravam `environment="unknown"`).
  Não-bloqueante; setar no painel de Env Vars do app backend.
- Apostergado: `idempotency_key` + lock de execução para o endpoint dedup
  (entram quando houver demanda real de execução repetida).


### Diário — Fase 10: Matching Pedagógico Flexível **[Fev/2026]**

> *Owner: "Não é afrouxar o Diário. É reconhecer que a semântica de slot só
> vale quando a grade é disciplinar de fato. Ensino Médio exige rigidez por
> aula. Educação Infantil exige coerência pedagógica integrada."*

Resolve falsos positivos de `orphan/inconsistent` em etapas com grade
pedagogicamente integrada (Educação Infantil, Anos Iniciais EF, EJA-Anos
Iniciais, multisseriadas) sem perder auditabilidade nem rastreabilidade.

#### Campo novo
- `classes.diary_matching_mode`: `"strict"` | `"flexible"`
- Quando ausente, **inferência determinística por etapa**:
  - `is_multi_grade=true` → flexible
  - `education_level` contém `infantil` / `anos_iniciais` / `creche` / `pré-escola` / `eja_anos_iniciais` → flexible
  - Caso contrário → strict

#### Algoritmo (Frontend NUNCA decide)
- **STRICT** (Anos Finais / EM): `same_date + same_slot + same_component + same_teacher`
- **FLEXIBLE**: depois do matching estrito, attendances/CEs órfãos são
  reaproveitados quando `same_date + (same_teacher OR same_component)`
  Reason marcado em `flexible_match_reason`:
    - `same_teacher_same_day`
    - `same_component_same_day`

#### Garantias (regras de não-bypass)
- `same_date` SEMPRE obrigatório — data diferente continua órfã.
- Vínculo semântico (teacher OU component) SEMPRE exigido — nunca casa por data isolada.
- Cada match marca `matched_by: "strict" | "flexible"` no entry.

#### Componentes
- Novo: `/app/backend/services/diary_matching_mode.py` (puro, sem I/O)
- Modificado: `routers/calendar_diary_state.py` (Etapa 4b — matching flexível)
- Modificado: `services/diary_snapshot_service.py` (mesma lógica + congela
  `matching_mode_used` no payload imutável)
- Modificado: `frontend/src/pages/DiaryCalendar.jsx` (badge discreto
  "Correspondência flexível" + tooltip pedagógico)
- Response do `/api/calendar/diary-state` agora inclui `matching_mode`.

#### Observabilidade
- Log estruturado `[diary_matching] matched_by=flexible reason=... class_id=...`
- Permite medir adoção e detectar abuso futuro.

#### Imutabilidade
- Snapshots publicados congelam `matching_mode_used` no payload.
- Mudar `diary_matching_mode` da turma DEPOIS NÃO altera snapshots
  (hash SHA-256 preservado, validado em pytest).

#### Bloqueios mantidos
- NÃO transforma flexible em "só same_date"
- NÃO infere dinamicamente em runtime quando o campo está set
- NÃO faz repair / backfill / migração automática

#### Testing
- 6/6 pytest verdes (`test_diary_matching_mode.py`):
  unit, strict_unchanged, flexible_same_teacher, flexible_same_component,
  flexible_rejects_unrelated, snapshot_freezes_matching_mode.
- Suíte completa Diário: 66/66 verdes, zero regressão.

---

### Diário — Fase 9: Legacy Schedule Bridge **[Fev/2026]**

> *Owner: "Esse bridge não é gambiarra. É camada de compatibilidade temporal
> entre um domínio legado operacional e um domínio novo auditável."*

Resolve a divergência arquitetural descoberta em produção: a grade horária
estava armazenada em `class_schedules + teacher_assignments` (modelo legacy),
mas o Diário consultava exclusivamente `teacher_class_assignments` (modelo
novo, vazio para a maioria das escolas). Resultado: 100% dos lançamentos
viravam "INCONSISTENTE" no calendário operacional.

#### Solução: read-time bridge transparente
- **Novo**: `/app/backend/services/legacy_schedule_bridge.py`
  - Função `build_assignments_from_legacy(db, class_doc)` que lê
    `class_schedules + teacher_assignments` e devolve assignments
    sintéticos no MESMO shape esperado pelo Diário.
  - Mapeia `day` ("segunda") → ISO weekday (1).
  - Resolve professor via lookup determinístico em `teacher_assignments`
    (course_id matching, status='ativo', desempate por created_at).
  - Vigência sintética: `valid_from = {academic_year}-02-01`,
    `valid_until = {academic_year}-12-31`.
  - Marca saída com `source="legacy_bridge"` e `synthetic_validity=True`.

#### Pontos de aplicação (obrigatório nos DOIS)
- `routers/calendar_diary_state.py` — UI operacional do Diário
- `services/diary_snapshot_service.py` — Snapshot imutável (congela bridge
  no payload; mudanças posteriores no legacy NÃO afetam o snapshot)

#### Ordem de resolução (sem merge, sem sincronização)
```
1. Lê teacher_class_assignments (modelo NOVO — prioridade absoluta)
2. Se vazio → usa bridge legacy
3. NUNCA mistura os dois
```

#### Observabilidade
- Log estruturado `[legacy_bridge] legacy_bridge_used=True class_id=... school_id=... academic_year=...`
- Permite medir adoção do modelo novo sem guesswork.

#### Testing
- 4 cenários pytest verdes (`test_legacy_schedule_bridge.py`):
  1. Legacy puro → slots reconhecidos
  2. Modelo novo presente → legacy ignorado
  3. Slot sem professor → não explode (teacher_id=None + warning)
  4. Snapshot congelado → hash imutável após mutação do legacy
- Suíte completa Diário: 60/60 verdes, zero regressão.

#### Bloqueios explícitos (proibido implementar agora)
- Migração automática · Sincronização bidirecional · Escrita dupla ·
  Backfill · Cache persistente · Repair jobs · Normalização em banco.

---

### Diário — Fase 8b: Endpoint de Diagnóstico da Grade **[Fev/2026]**

`GET /api/admin/diary/grade-diagnose/{class_id}` — read-only, LGPD-safe,
restrito a admin/diretor/super_admin/gerente/semed3.

Retorna: inventário de assignments, distribuição de `valid_from`,
cobertura mensal com flag `is_suspicious`, lista de datas órfãs,
diagnóstico textual (`CADASTRAR_GRADE` | `GRADE_DELETADA` |
`AJUSTAR_VALID_FROM` | `OK`). Foi a ferramenta usada em produção para
identificar a causa raiz que motivou a Fase 9 (Legacy Schedule Bridge).

#### Testing
- 4 testes pytest verdes (`test_admin_diary_diagnose.py`).

---

### Diário — Fase 8: UI de Snapshot Management **[Fev/2026]**

> *Owner: "Construir somente a interface operacional mínima necessária.
> Comunicar 'documento institucional verificável' — não 'gerenciador técnico
> de snapshots'. UI nunca recalcula; apenas representa o backend."*

Fecha o ciclo operacional do Diário Institucional. Coordenação/Direção
operam emissão, assinatura e revogação de documentos sem precisar tocar
endpoints. Backend pré-existente (Fases 5, 5b, 6, 7) zero alteração.

#### Componentes
- Novo: `/app/frontend/src/components/diary/SnapshotsDrawer.jsx`
- Integrado a: `/app/frontend/src/pages/DiaryCalendar.jsx` (botão
  "Documento do período" no header — visível para
  admin/diretor/secretario/coordenador/gerente)

#### Fluxo (Sheet lateral)
- **Período atual** com botão verde "Emitir documento do período" →
  cria draft + auto-publica + dispara render_job. Polling a cada 4s.
- **Documentos emitidos** (lista da turma toda, ativos primeiro):
  - Badge de status (draft/published/superseded/revoked)
  - Code SIGESC-DIARY-XXXX-XXXX + hash encurtado SHA-256
  - "Baixar PDF" quando render_job=completed
  - URL de verificação pública /verify/diary/{token} + copy + abrir
  - Assinaturas: lista (Pen icon, role, tipo, data) + "Assinar"
    (form com role/full_name/tipo manual ou imagem) + revogar
    assinatura (rationale ≥30)
  - "Revogar documento" — dialog em 2 etapas com rationale ≥30 chars

#### Diretrizes obedecidas
- Frontend NUNCA recalcula. Só renderiza estado do backend.
- UI institucional, linguagem humana, sem JSON cru.
- Revogar = ato grave → confirmação dupla obrigatória.
- Idempotência respeitada: oculta "Emitir" quando já existe ativo.

#### Testing
- testing_agent_v3_fork iteration_81: 100% verde, zero bugs/issues.
- Cobertura: emit+publish, render polling, download PDF, verify URL,
  sign form open + role/type, revoke 2-step validation, idempotência.

---

### Diário — Fase 6b: UI Operacional do Integrity Report **[Mai/2026]**

> *Owner: "O `integrity-report` NÃO é um relatório técnico. Ele é um painel
> operacional de saneamento institucional. Transformar inconsistências em
> fila de trabalho. Sem isso, a Fase 7 perde valor."*

A UI deixou de ser "melhoria visual" e virou **infraestrutura operacional**.
Os 807 issues detectados pelo backend agora viraram cards executáveis em
linguagem humana, com workflow rastreável.

#### Backend — Workflow State
- Coleção nova: `grade_integrity_issue_states`
- Fingerprint determinístico SHA-256 (16 chars) por issue — mesma issue
  amanhã = mesmo fingerprint = estado workflow persiste.
- 4 estados: `open | in_analysis | resolved | wont_fix`.
- `notes[]` **append-only** com author + timestamp.
- Campos: `assigned_to_user_id`, `assigned_to_name`, `resolved_at`,
  `resolved_by_user_id`, `updated_at`.
- Endpoint: `POST /api/teacher-class-assignments/integrity-report/issues/{fingerprint}/state`
- Auditoria automática em `audit_logs` com `action=update_integrity_state`.

#### Humanização (PT-BR)
Cada issue agora retorna 3 campos novos do backend:
- `human_title`: "Conflito de Professor" (em vez de "TEACHER_DOUBLE_BOOKING")
- `human_summary`: descrição em PT clara e contextual
- `impact`: o que acontece se NÃO corrigir

Função `_humanize()` no service mapeia os 8 kinds.

#### Summary enriquecido
- `affected_schools` (count distinct)
- `affected_teachers` (count distinct)
- `affected_classes` (count distinct)
- `by_status` distribution (open/in_analysis/resolved/wont_fix)

#### Frontend — `/admin/grade-integrity` (`GradeIntegrity.jsx`)
**4 chips executivos**: Inconsistências total · Críticas · Médias · Baixas
+ metadata pills (escolas/professores/turmas afetados).

**5 filtros**: Escola · Tipo de problema · Severidade · Situação (default
"Abertas") · Ano letivo.

**Cards humanizados** (NÃO JSON técnico):
- Chip de severidade colorido (vermelho/âmbar/azul)
- Chip de status (Aberto/Em análise/Resolvido/Não corrigir)
- Título humano + descrição em PT + impacto em itálico
- Turma + Professor envolvidos visíveis sem clique
- Severidade ordena automaticamente (high → medium → low)

**Drill-down (Sheet lateral)**:
- Resumo humanizado + bloco vermelho "Impacto:" + bloco verde "Ação sugerida:"
- Workflow institucional com botões contextuais:
  - `open` → "Marcar como em análise"
  - `open|in_analysis` → "Marcar como resolvido" / "Não corrigir"
  - `resolved|wont_fix` → "Reabrir"
- Lista de vínculos envolvidos com **link direto** "Abrir vínculo"
  para `/admin/teacher-assignments?focus={assignment_id}`
- Slot conflitante + período da lacuna quando aplicável
- Observações append-only (textarea + botão "Adicionar observação")

**Atualização local otimista**: após mudança de state, lista e drill-down
refletem instantaneamente. Filtro por situação default "Abertas" — issue
resolvida desaparece da view.

#### Validação E2E
Smoke test completo: login → navegação → cards visíveis → drill-down →
mark as `in_analysis` → adicionar observação → toast confirmação → state
persistido no banco e renderizado.

#### Arquivos
- 📝 `/app/backend/services/grade_integrity_service.py` (+ fingerprint,
  humanize, load_states, update_issue_state, ensure_integrity_indexes)
- 📝 `/app/backend/routers/teacher_class_assignments.py` (+endpoint state)
- 📝 `/app/backend/server.py` (+ensure_integrity_indexes no startup)
- ✨ `/app/frontend/src/pages/GradeIntegrity.jsx` (novo, ~620 linhas)
- 📝 `/app/frontend/src/App.js` (rota `/admin/grade-integrity`)
- 📝 `/app/frontend/src/pages/Dashboard.js` (menu "Integridade da Grade")

Regressão completa: **77 testes verdes** (mantidos integralmente).



### Diário — Fase 7: Fluxo Institucional de Validação + Multi-maturidade de Assinatura **[Mai/2026]**

Salto institucional. O documento deixou de ser "do professor" e virou "da
escola". A coordenação pedagógica agora tem ação executável dentro do
calendário operacional.

> *Owner: "Sem validação institucional, o documento continua sendo do
> professor, não da escola."*

#### Backend (3 endpoints novos em `/api/attendance`)
1. **`POST /api/attendance/{id}/validate`** — valida UMA frequência.
   Requer `attendance.records.length > 0`. Bumpa `version`. Grava
   `validated_by`, `validated_by_name`, `validated_by_role`, `validated_at`.
   Audit log obrigatório com `change_kind=validation`.

2. **`POST /api/attendance/validate-batch`** `{class_id, dates[]}` —
   internamente roda N validações individuais. Cada uma gera audit_log
   próprio. Todas compartilham `batch_marker` (UUID) para correlação
   posterior. **NÃO cria "uma validação única"** — princípio do owner.

3. **`POST /api/attendance/{id}/unvalidate`** `{rationale ≥ 30}` —
   reverte preservando histórico em `validation_history[]` (append-only).
   Roles autorizados: quem validou OR admin/super_admin.

Constraints:
- `EMPTY_RECORDS` (422) se attendance vazia.
- `ALREADY_VALIDATED` (409) idempotente.
- `RATIONALE_TOO_SHORT` (422) se rationale < 30.
- `FORBIDDEN_UNVALIDATE` (403) se não autor original nem admin.
- `NOT_VALIDATED` (409) se tentar reverter sem validação.

Roles de validação: `coordenador`, `apoio_pedagogico`, `diretor`,
`secretario`, `admin*`, `super_admin`, `gerente`.

#### Multi-maturidade de Assinatura (suporte aos 3 níveis simultâneos)
`POST /api/diary/snapshots/{id}/sign` agora aceita `signature_type`:

| signature_type | Validação | Cenário |
|---------------|-----------|---------|
| `manual` (default) | nenhuma | Município imprime e assina à caneta. PDF gera linha física. |
| `image` | `image_file_id` obrigatório | Secretaria com imagem de assinatura cadastrada. PDF embute referência. |
| `icp_brasil` | `certificate_info` obrigatório | Reservado (futuro). |

Schema do signature:
```
{id, role, full_name, signed_by_user_id, signature_type,
 signed_at, signed_document_hash,
 image_file_id, certificate_info,
 ip_address, user_agent,
 status: "active|revoked",
 revoked_at, revoked_reason, revoked_by_user_id}
```

**`POST /api/diary/snapshots/{id}/signatures/{sig_id}/revoke`** —
revoga PRESERVANDO o objeto (status=revoked + metadados). Diretriz 7
do owner: nunca delete, sempre marcar. Slot fica liberado para nova
assinatura do mesmo (role, user).

#### PDF atualizado (`diary_pdf_handler.py`)
Renderiza assinaturas conforme tipo:
- **manual**: linha física `________________________`, nome, cargo, data esperada
- **image**: bloco textual + referência ao file_id + disclaimer "não equivale à assinatura ICP-Brasil"
- **icp_brasil**: bloco com subject/issuer/valid_until
- Fallback se nenhuma assinatura: linha física institucional padrão (NUNCA deixa "sem assinatura").
- Hash vinculado mostrado em todas as maturidades.

#### Endpoint agregador atualizado (`/diary-state`)
- Inclui `validated_by_name`, `validated_at` em cada `entry` que tem validação.
- Nova classificação `validated` em `day_status_counts` (peso > complete).
- `_classify_day` retorna `"validated"` quando **TODOS** entries do dia
  têm `attendance_status=="validated"`.

#### Frontend (`DiaryCalendar.jsx`)
- **5 chips** no SummaryBar: Todos / **Validados (verde forte)** / Completos
  (aguardando validação) / Pendentes / Inconsistências.
- **Botão "Validar período"** no header (verde) — só aparece se houver
  dias complete/corrected. Lote com confirmação + audit_log por dia.
- **Painel de Validação** em CADA slot do drill-down:
  - Estado `completed` → botão "Validar institucionalmente" (verde).
  - Estado `validated` → ícone shield + "Validado por X" + "em DD/MM/YYYY HH:MM"
    + botão "Reverter validação" (cinza, abre prompt obrigatório de rationale).
- Atualização otimista: após validar, refetch + drill-down se mantém aberto
  com dados frescos.
- Toasts (sonner) em todos os fluxos.

#### Testes
- `tests/test_validation_and_signatures.py` — **11 testes verdes**:
  1. validate marca campos + audit_log
  2. blocks empty records (422)
  3. already_validated (409)
  4. unvalidate rationale curto (422)
  5. admin unvalidate preserva validation_history[]
  6. validate-batch: N audit_logs com batch_marker correlacionado
  7. validate-batch pula dias sem attendance
  8. signature manual (default)
  9. signature image exige file_id
 10. signature icp_brasil exige certificate_info
 11. revoke_signature preserva objeto + libera slot

**Regressão completa: 77/77 verdes** (66 anteriores + 11 novos).

#### Arquivos
- 📝 `/app/backend/routers/attendance.py` (+3 endpoints, 2 models, helper `_validate_single`)
- 📝 `/app/backend/services/diary_snapshot_service.py` (`add_signature` reescrito multi-maturidade + `revoke_signature` novo)
- 📝 `/app/backend/services/diary_pdf_handler.py` (render 3-tier)
- 📝 `/app/backend/routers/diary_snapshots.py` (sign request expandido + endpoint revoke)
- 📝 `/app/backend/routers/calendar_diary_state.py` (validated_by_name nos entries; classify_day reconhece `validated`)
- 📝 `/app/frontend/src/pages/DiaryCalendar.jsx` (chips, batch button, validation panel no drill-down)
- ✨ `/app/backend/tests/test_validation_and_signatures.py` (novo, 11 testes)



### Diário — Fase 6: Integrity Report da Grade Horária **[Mai/2026]**

Detector arquitetural. Pré-requisito **absoluto** para a Fase 7 (validação
institucional): sem grade correta, completude é falsa, alertas mentem,
PDFs mentem e validação vira teatro. Owner explícito:

> *"O próximo gargalo operacional do SIGESC NÃO será código. Será qualidade
> da grade horária cadastrada. O endpoint de integrity-report será
> obrigatório, NÃO opcional."*

#### Endpoint
`GET /api/teacher-class-assignments/integrity-report?school_id=&class_id=&reference_date=&academic_year=`

Roles autorizados: admin, super_admin, secretario, gerente, semed3, coordenador.

#### 8 classes de inconsistência detectadas

| Kind | Severidade | O que detecta |
|------|-----------|---------------|
| `TEMPORAL_GAP` | high | Mesmo (class, comp, weekday, aula) com lacuna entre `valid_until` de um e `valid_from` do próximo |
| `OVERLAP` | high | 2+ assignments ativos no mesmo (class, weekday, aula) sem `is_substitute` |
| `TEACHER_DOUBLE_BOOKING` | high | Mesmo professor em 2 turmas diferentes simultaneamente no mesmo slot |
| `CLASS_WITHOUT_ASSIGNMENT` | high | Turma ativa do ano corrente sem nenhum assignment vigente |
| `EXPIRED_NO_SUCCESSOR` | medium | Assignment expirado SEM nenhum sucessor cobrindo a data atual |
| `ORPHAN_TEACHER` | medium | `teacher_id` não existe em `users` ou está apagado |
| `DUPLICATE_SLOT` | low | Mesmo (weekday, aula) duplicado dentro de um `weekly_slots[]` |
| `INVERTED_VALIDITY` | low | `valid_until < valid_from` |

Cada issue retornada inclui: `kind`, `severity`, `class_id/name`, `school_id`,
`component_id`, `weekday`, `aula_numero`, `assignment_ids[]`, `recommendation`
(em português) com ação corretiva concreta.

#### Resposta
```
{
  "reference_date": "2026-05-22",
  "filters": {school_id, class_id, academic_year},
  "summary": {
    "total_issues": N,
    "by_severity": {high, medium, low},
    "by_kind": {KIND: count},
    "classes_scanned": N,
    "assignments_scanned": N
  },
  "issues": [...]
}
```

#### Resultado do primeiro scan em produção
**807 issues encontradas** no dataset real (validou empiricamente a hipótese
do owner):
- 759 `TEACHER_DOUBLE_BOOKING` (seeds duplicando professor em várias turmas)
- 43 `CLASS_WITHOUT_ASSIGNMENT` (turmas sem grade cadastrada)
- 4 `OVERLAP` (cobertura duplicada sem `is_substitute`)
- 1 `EXPIRED_NO_SUCCESSOR`

A correção destes problemas pela coordenação é a próxima fase manual antes
da Fase 7 (Validação Institucional).

#### Arquivos
- ✨ `/app/backend/services/grade_integrity_service.py` (novo, 320 linhas)
- 📝 `/app/backend/routers/teacher_class_assignments.py` — endpoint inline
- ✨ `/app/backend/tests/test_grade_integrity.py` (11 testes verdes,
  com fixtures isoladas em `users`/`classes`/`teacher_class_assignments`)

Regressão completa: **66 testes verdes** (55 anteriores + 11 novos).



### Diário — Fase 5 Backend: Snapshot Imutável + PDF + Observabilidade **[Mai/2026]**

Salto institucional do módulo. Transformou o diário escolar de "registro" em
**evidência institucional verificável**. O frontend já não é a única "camada
nova" — o documento congelado agora vive permanentemente no banco com hash
SHA-256 imutável.

#### Arquitetura (10 diretrizes do owner)
1. ✅ **PDF lê snapshot**, NUNCA banco vivo.
2. ✅ **Multi-autoria preservada**: `created_by`, `updated_by`, `published_by`,
   `corrected_by`, `validated_by` por slot + `authors_registry` agregado.
3. ✅ **Hash SHA-256 imutável** sobre payload canonicalizado
   (`json.dumps(sort_keys=True, ensure_ascii=False, separators=(",",":"))`).
4. ✅ **branding{}** reservado no schema desde já — `mantenedora_name`,
   `school_name`, `logo_file_id`, `primary_color`, `secondary_color`,
   `document_footer`, `signature_layout`.
5. ✅ **renders[]** como array — snapshot é verdade, PDFs são derivações.
   Cada render carrega `template_version`, `render_engine_version`,
   `generated_file_id`, `checksum_sha256`, `generated_at`, `generated_by`.
6. ✅ **semantic_rules_version="1"** — congela o significado institucional
   dos estados (complete/empty/inconsistent/etc).
7. ✅ **signatures[]** append-only. Campo `revoked_signature_at` em vez de
   delete. Cada assinatura grava `signed_document_hash` (anti-substituição).
8. ✅ **Idempotência**: enquanto `status ∈ {draft, published}`, retorna
   existente. Só após `superseded`/`revoked` é possível novo snapshot.
9. ✅ **supersede ≠ revoke** — separação semântica/jurídica preservada.
10. ✅ **Canonicalização documentada explicitamente** no docstring do serviço.

#### Schema novo: `diary_snapshots`
```
{id, code:SIGESC-DIARY-XXXX-XXXX, schema_version,
 semantic_rules_version, template_version, render_engine_version,
 document_type:"diary_period", class_id, school_id, mantenedora_id,
 period:{type:month|bimester|custom, from, to, label, academic_year},
 branding:{...}, payload:{class, summary, days[], authors_registry, orphan_evidence},
 payload_hash_sha256, verification_token (sparse), renders:[],
 status:draft|published|superseded|revoked,
 superseded_by_snapshot_id, revoked_at, revoked_reason, revoked_by_user_id,
 signatures:[], issued_at, issued_by_user_id, created_at, created_by_user_id,
 audit_trail:[]}
```
Índices: `id` unique, `code` unique, `verification_token` unique+sparse,
`(class_id, period.from, period.to, status)` composto, `(school_id, created_at desc)`,
`mantenedora_id`.

#### Endpoints
- `POST /api/diary/snapshots` — cria draft (idempotente)
- `POST /api/diary/snapshots/{id}/publish` — calcula hash, gera token + code,
   enfileira `render_job` (handler `diary_period`)
- `POST /api/diary/snapshots/{id}/supersede` `{new_snapshot_id, rationale≥30}`
- `POST /api/diary/snapshots/{id}/revoke` `{rationale≥30}` (hash preservado)
- `POST /api/diary/snapshots/{id}/sign` `{role, full_name}` — assinatura
   institucional append-only
- `GET /api/diary/snapshots/{id}` — payload completo
- `GET /api/diary/snapshots?class_id&status&period_from&period_to` — listagem
   paginada (sem `payload` para economizar payload)
- `GET /api/admin/observability/diary-state` (super_admin) — métricas p95/p99
   do endpoint agregador (sem cache nesta rodada — diretriz "medir antes")

#### Integração com `render_jobs`
Registrou handler `diary_period` em `register_render_handler`. Worker existente
processa o job e gera PDF com ReportLab (template `diary-v1`). O PDF é
armazenado em `document_files`, hash SHA-256 calculado, e uma entrada é
appendada em `diary_snapshots.renders[]` (1:N snapshot↔renders).

#### Testes (11 verdes — `tests/test_diary_snapshots.py`)
1. Hash determinístico unitário.
2. Idempotência draft (mesmo período → mesmo snapshot).
3. Publish gera hash + token + render_job.
4. Hash imutável após signature.
5. Sign duplicado por (role, user) → 409.
6. Revoke preserva hash original (diretriz 9).
7. Rationale curto bloqueado (422).
8. Schema reservado (branding/renders[]/semantic_rules_version).
9. **Snapshot NÃO muda quando attendance é alterado após publicação**
   (validação crítica da imutabilidade).
10. Render job idempotente por `idempotency_key`.
11. Worker popula `renders[]` (array, não singular).

Regressão completa: **55 testes verdes** (44 anteriores + 11 novos).

#### Observabilidade do `/diary-state`
Canal dedicado `MetricChannel("diary_state")`:
- p95/p99/p50 latency em buckets [10, 25, 50, 100, 250, 500, 1000, 2500, 5000] ms
- Distribuição de `range_bucket` (1d/1w/1m/2m/3m)
- `avg_range_days` derivado
- Endpoint: `GET /api/admin/observability/diary-state` (super_admin only)
- Cache: **desativado** explicitamente (`cache_enabled=false`,
   `cache_decision_note` documenta o motivo arquitetural).

#### Arquivos criados/modificados
- ✨ `/app/backend/services/diary_snapshot_service.py` (novo, 540 linhas)
- ✨ `/app/backend/services/diary_pdf_handler.py` (novo, 280 linhas)
- ✨ `/app/backend/routers/diary_snapshots.py` (novo, 230 linhas)
- ✨ `/app/backend/tests/test_diary_snapshots.py` (novo, 280 linhas, 11 testes)
- 📝 `/app/backend/routers/calendar_diary_state.py` — observabilidade adicionada
- 📝 `/app/backend/routers/admin_observability.py` — endpoint `/diary-state`
- 📝 `/app/backend/utils/render_jobs.py` — `DOCUMENT_TYPES += ("diary_period",)`
- 📝 `/app/backend/server.py` — wiring de router + handler + indexes



### Diário — Fase 5 Frontend: Calendário Operacional **[Mai/2026]**

UI de governança visual do diário escolar — renderizador SEMÂNTICO PURO sobre
o endpoint agregador `GET /api/calendar/diary-state/{class_id}` criado nas
rodadas anteriores. NÃO recalcula nada; apenas mapeia os 7 estados retornados
pelo backend (`inconsistent | empty | validated | corrected | partial |
complete | not_expected`) para a paleta definida em
`/app/design_guidelines.json`.

#### Arquivos
- `/app/frontend/src/pages/DiaryCalendar.jsx` — página principal.
- Rota: `/admin/diary-calendar` (App.js).
- Menu: "Calendário do Diário" em **Gestão Pedagógica** (Dashboard.js).
- Permissão: super_admin, gerente, admin/admin_teste, secretario, diretor,
  coordenador, apoio_pedagogico, auxiliar_secretaria, professor, semed*.

#### Diretrizes obeídas (16 do owner)
1. ✅ Ferramenta operacional, não dashboard decorativo.
2. ✅ Default = primeira escola visível ao usuário + ano corrente + mês corrente.
3. ✅ Role-based: professor/SchoolStaff limitados a `user.school_ids`;
     admin/SEMED veem todas.
4. ✅ Lazy loading por mês (range 1 mês). Nunca carrega ano inteiro.
5. ✅ Semântica triplicada — cor + ícone (lucide) + label + tooltip.
6. ✅ `not_expected` quase invisível (`opacity-50`, sem badge forte).
7. ✅ `inconsistent` com `ring-2 ring-red-600 ring-inset` (impossível ignorar).
8. ✅ Drill-down via Sheet lateral — frequência, status, professores
     esperados, conteúdos, horários, badges de status.
9. ✅ Frontend NÃO infere estado. Mapeia 1:1 o que o backend devolveu.
10. ✅ Modo gestão: filtro de severidade nas chips do SummaryBar
      (clicar em "Pendentes" → highlight do chip ativo).
11. ✅ Célula compacta: número, ícone, label, contagem de aulas,
      micro-indicadores. Detalhe fica no drill-down.
12. ✅ Performance: `Skeleton` durante load, `AbortController` em filtros,
      seleção sob demanda (anti race-condition via `defaultedRef`).
13. ✅ Menu visível em primeiro nível ("Calendário do Diário").
14. ✅ URL: `/admin/diary-calendar`.
15. ✅ Foco: descobrir inconsistências reais, não estética.
16. ✅ Coordenação bate o olho e entende: SummaryBar bold + grid colorido +
      legenda fixa.

#### Componentes principais (todos no mesmo arquivo)
- `Legend` — barra horizontal com 7 estados (sempre visível).
- `SummaryChips` — bento de 4 chips clicáveis (severity filter).
- `DayCell` (desktop) — grid 7 colunas, `min-h-[120px]`, com semântica visual,
  ring vermelho destacado em `inconsistent`, `opacity-50` em `not_expected`.
- `MobileDayRow` — lista vertical ordenada por severidade no `<md`, esconde
  `not_expected` integralmente.
- `DayDrillDown` — `Sheet` lateral com resumo + lista de slots
  (`Aula N`, professor, componente, horário, badges de attendance/content).
- `OrphanEvidenceList` — bloco vermelho separado quando `summary` traz
  `orphan_attendance_dates` ou `orphan_content_dates`.

#### Tests
- `/app/test_reports/iteration_80.json` — Frontend E2E: **100% verde,
  zero issues**. 16 diretrizes do owner validadas explicitamente. Validado
  com `Escola Teste Multisseriada → Turma Multi 1-2-3 → Maio 2026`:
  21 dias `empty` (Seg-Sex) + 10 `not_expected` (Sáb/Dom); drill-down do
  dia 04/05 traz 2 slots (Aula 1 + Aula 2) da professora Ricleide.

#### Refactoring sugerido para próximas rodadas (não-bloqueante)
- Splitar `DiaryCalendar.jsx` (~1083 linhas) em sub-componentes em
  `/components/diary-calendar/`.
- Centralizar `axios.get` em `services/api.js` (`calendarAPI`).
- Importar `STATUS_META` diretamente de `design_guidelines.json` em vez de
  duplicar.



### Bolsa Família — Fase 3B: Dashboard Operacional Busca Ativa **[Fev/2026]**

Painel **operacional** (não decorativo) que responde "Onde agir primeiro?"
Owner-driven com 4 linhas de informação progressiva: cards executivos →
distribuição → escolas críticas → casos prioritários.

#### Backend — extensões da Fase 3A
- `list_followup_cases()` agora aceita `category` e `school_id` opcionais.
- `GET /api/bolsa-familia/stats/network/followup?category=&school_id=` —
  filtros propagados; consistência com export.
- `GET /api/bolsa-familia/stats/network/followup/export?category=…` —
  filename sufixado por categoria (`bolsa_familia_busca_ativa_2026_violence.xlsx`).
- `POST /api/bolsa-familia/stats/network/snapshot` — persiste snapshot
  diário em `bf_network_stats_snapshots` (idempotente por data + scope).
- `GET /api/bolsa-familia/stats/snapshots?from_date&to_date&academic_year` —
  série temporal para gráficos de evolução.
- Índice único `(snapshot_date, scope.academic_year, scope.mec_version)` criado.

#### Frontend — `/app/frontend/src/pages/BuscaAtivaDashboard.jsx`
- Banner "Pergunta institucional — Onde devemos agir primeiro?".
- **Linha 1**: 5 cards executivos (`total c/ motivo`, `severity ≥ 5` com ring
  vermelho destacado, `req. acompanhamento`, `top categoria`, `top escola`).
- **Linha 2**: grid de categorias MEC clicáveis. Hover revela botão de
  export pré-filtrado por categoria (1 clique → XLSX da rede social) —
  fluxo institucional Conselho Tutelar/CRAS.
- **Linha 3**: tabela "Top escolas" com link "Abrir" → `/admin/bolsa-familia?school_id=X`.
- **Linha 4**: casos prioritários paginados (25/página), filtro severity_min,
  badge "CRÍTICO" para severity ≥ 5, botão "Baixar filtrados".
- Severidade 5 com **fundo vermelho na linha + badge bold borda red-300**.
- Categorias mapeadas em `CATEGORY_META` (17 categorias × ícone × cor).
- `data-testid` em todos os elementos interativos.
- Rota: `/admin/bolsa-familia/busca-ativa` (roles: admin, secretario,
  diretor, semed3, ass_social_2, gerente).
- Link de acesso adicionado no header da página de Bolsa Família.

#### Tests
- `tests/test_bf_phase_3b.py` — **8 E2E HTTP** (100% verde):
  filter by category VIOLENCE, filter by school, combined filters, export
  com category no filename, snapshot persiste, snapshot idempotente
  (mesmo dia → upsert), snapshot list shape, snapshot payload contém
  agregados reais.
- Suite BF consolidada: **68/68 verde** (10 MEC + 9 canonical + 12 e2e_systemic +
  13 suggestion + 10 network_stats + 6 export + 8 phase_3b). Zero regressões.
- E2E manual: dashboard carregado, 5 cards renderizados, 5 categorias,
  11 casos. Click em "Violência" → 3 casos filtrados + badge "Violência ×".

#### Princípios honrados
- ✅ **Operacional**, não decorativo
- ✅ Severidade nunca escondida — severity 5 com destaque visual forte
- ✅ Paginação obrigatória (PAGE_SIZE = 25)
- ✅ "Baixar planilha" pré-filtrado por categoria (ação em 1 clique)
- ✅ Engine única (`list_followup_cases` para JSON, export, snapshot)
- ✅ Snapshot histórico pronto para evolução temporal (gráficos futuros)

#### Cron externo recomendado (operacional)
```bash
# Roda diariamente às 00:30 (k8s CronJob ou crontab)
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "X-CSRF-Token: $CSRF" \
  "$API/api/bolsa-familia/stats/network/snapshot?academic_year=2026"
```



### Bolsa Família — Fase 3A.1: Export CSV/XLSX para Busca Ativa **[Fev/2026]**

Habilita IMEDIATAMENTE Busca Ativa manual, reuniões pedagógicas, CRAS e
Conselho Tutelar — antes do dashboard visual. Owner spec: secretarias
vivem de planilha; valor operacional alto, custo arquitetural mínimo.

#### Endpoint
- `GET /api/bolsa-familia/stats/network/followup/export?format=csv|xlsx&academic_year&severity_min&limit`
  - **Reusa** `list_followup_cases()` → consistência total com endpoint JSON.
  - Anota `frequency` por caso usando engine canônica (`compute_monthly_valid_absences`
    + cache local para evitar N+1).
  - Headers: `Content-Disposition: attachment`, `X-Total-Cases`, `X-Stats-Version`.

#### CSV
- BOM UTF-8 (Excel abre acentos corretamente).
- Separador `;` (padrão Brasil).
- Bool renderizado como "Sim/Não" (UX para secretaria).

#### XLSX (openpyxl 3.1.5)
- Aba "Busca Ativa".
- Header em destaque (bold branco + fill azul `#1E40AF`).
- `freeze_panes = "A2"` (header sempre visível).
- Auto-width básico (limite 50ch).

#### Colunas (owner spec)
| Coluna | Origem |
|---|---|
| Aluno | `student_name` (lookup `students`) |
| Escola | `school_name` (lookup `schools`) |
| Categoria MEC | `_group.category` |
| Grupo MEC | `_group.name` |
| Subcódigo | `_reason.mec_subcode` |
| Motivo | `_reason.name` |
| Severidade | `_reason.severity_level` |
| Requer acompanhamento | `_reason.requires_followup` → Sim/Não |
| Mês | tracking |
| Ano letivo | tracking |
| Frequência | engine canônica |
| Observações | `tracking.notes` |

#### Tests
- `tests/test_bf_export_followup.py` — 6 E2E HTTP (100% verde):
  CSV headers+format (BOM UTF-8, separador `;`, header PT-BR),
  CSV content (VIOLENCE, 11a, "Sim"), XLSX structure (12 cols, freeze,
  bold), XLSX content, validação `format` (422 p/ valor inválido),
  filtro severity_min=5 OR requires_followup=True.
- Suite BF consolidada: **60/60 verde** (10 MEC + 9 canonical +
  12 e2e_systemic + 13 suggestion + 10 network_stats + 6 export).



### Bolsa Família — Fase 3A: Agregados Institucionais (Network Stats) **[Fev/2026]**

Camada analítica institucional — pré-requisito para Dashboard Busca Ativa.
Owner spec: backend PRIMEIRO, dashboard depois. Pipeline `$facet` única,
versionada, cacheável. Núcleo de inteligência de permanência escolar.

#### Arquitetura
- `services/bf_network_stats.py` — pipeline `$facet` única + função
  `list_followup_cases` (lookup encadeado com denormalizações).
- `GET /api/bolsa-familia/stats/network?academic_year&mec_version` —
  agregados gerais. Cache **in-process TTL 5min** (evita explosão de
  polling do dashboard). Suporta `force_refresh=true`.
- `GET /api/bolsa-familia/stats/network/followup?academic_year&severity_min&limit` —
  casos prioritários para Busca Ativa (severity≥N OR requires_followup=True),
  ordenados por severity desc + updated_at desc, com denormalizações
  (`student_name`, `school_name`, `reason_name`, `category`, `group_name`).

#### Versionamento
- `STATS_VERSION = "v1.0"` — bump em qualquer mudança de shape.
- Toda resposta inclui `stats_version`, `generated_at` (UTC ISO),
  `scope` (academic_year + mec_version aplicados).

#### Pipeline `$facet` — 7 dimensões em uma viagem ao banco
```
{
  total: [{$count}],
  by_category: [{$group _id=category}],
  by_severity: [{$group _id=severity_level}],
  requires_followup: [{$match requires_followup=true}, {$count}],
  severity_5_plus: [{$match severity_level≥5}, {$count}],
  top_schools: [{$group _id=school_id}, {$sort count:-1}, {$limit 10}],
  top_subcodes: [{$group _id=(subcode,name)}, {$sort count:-1}, {$limit 15}]
}
```

#### Princípios honrados
- ✅ **Backend primeiro** — endpoint estável antes do dashboard
- ✅ **Uma query agregada** — não múltiplas queries dispersas no frontend
- ✅ **Apenas agregados** (network) — lista de alunos só em `/followup` com limit
- ✅ **Documentos sem `reason_id` ignorados** — agregados refletem dados estruturados
- ✅ **Cacheável** — TTL 5min in-process
- ✅ **Versionado** — `stats_version: "v1.0"`
- ❌ ZERO lógica no frontend — UI vai consumir pronto

#### Tests
- `tests/test_bf_network_stats.py` — **10 E2E HTTP** (100% verde):
  shape+version, totals (14 docs ignorando o sem reason_id), severity_buckets,
  requires_followup count, top_schools com nomes resolvidos, caching
  funcional (cached=false → true), followup severity_5, sort desc,
  limit enforced, exclusão de docs sem reason_id.
- Suite BF consolidada total: **54/54 verde** (10 MEC + 9 canonical +
  12 e2e_systemic + 13 suggestion + 10 network_stats).

#### NÃO implementado (intencionalmente — owner spec)
- ❌ Dashboard visual (Fase 3B — só após backend estabilizar)
- ❌ Lista completa da rede sem limite
- ❌ Filtros granulares por categoria (próxima evolução de contrato → v1.1)
- ❌ Persistência de snapshots históricos dos agregados



### Bolsa Família — Fase 2: Suggestion Engine Determinística **[Fev/2026]**

Camada de inteligência operacional EXPLÍCITA (sem IA, sem ML, sem scoring
probabilístico). Owner-driven decision: rules engine v1.0 com 2 regras
ativas + 1 hook reservado para Layer 2 futura.

#### Arquitetura
- `services/bf_reason_suggestion.py` — **lógica pura**, ZERO I/O. Recebe
  métricas e índice de reasons; retorna sugestão auditável.
- `GET /api/bolsa-familia/suggest-reason?student_id&school_id&month&academic_year`
  — endpoint que calcula métricas via engine canônica (`compute_monthly_valid_absences`
  + `fetch_medical_days_for_students`), resolve reasons MEC, busca tracking
  atual e delega para a engine pura.

#### Regras v1.0
| Código | Quando dispara | Ação |
|---|---|---|
| `R1_MEDICAL_DAYS_GTE_50PCT` | `medical_days / total_absences_observed ≥ 0.50` | Sugere reason `1a` (Doença/problemas físicos), confidence = proporção observada |
| `R2_TRANSPORT` | **RESERVADO** (depende de `absence_type` granular — Layer 2) | hook deixado pronto |
| `R3_HIGH_SEVERITY` | reason atual selecionado tem `severity_level ≥ 5` | `requires_followup_flag = True` (encaminhar p/ Busca Ativa) |

#### Constantes versionadas
- `SUGGESTION_ENGINE_VERSION = "1.0"` (bump em qualquer mudança de regra)
- `PROPORTION_THRESHOLD = 0.50`
- `SEVERITY_FOLLOWUP_THRESHOLD = 5`

#### Contrato de resposta
```json
{
  "engine_version": "1.0",
  "suggested_reason_id": "uuid-or-null",
  "suggested_reason_subcode": "1a",
  "confidence": 1.0,
  "rules_triggered": [
    {"code": "R1_MEDICAL_DAYS_GTE_50PCT", "value": 1.0, "threshold": 0.5,
     "medical_days": 8, "total_absences_observed": 8}
  ],
  "requires_followup_flag": false,
  "human_explanation": "8 de 8 ausências (100%) têm atestado médico — sugerido '1a — Doença/problemas físicos'.",
  "should_show_suggestion": true,
  "metrics": {"school_days": 20, "valid_absences": 0, "medical_days_count": 8,
              "frequency_percentage": 100.0}
}
```

#### Princípios honrados
- ✅ Determinística (mesma entrada → mesma saída) — coberto por teste
- ✅ Auditável (rules_triggered + human_explanation sempre preenchidos)
- ✅ Conservadora (sem ausências observadas → sem sugestão)
- ✅ `should_show_suggestion=false` quando reason atual já é o sugerido
- ❌ ZERO IA, ZERO ML, ZERO LLM, ZERO scoring composto

#### Tests
- `tests/test_bf_reason_suggestion.py` — 13 unit (100% verde):
  R1 em 100%, em 50% (inclusivo), abaixo de 50%, sem ausências, sem reason 1a;
  R3 dispara em sev=5, não dispara em sev=2, não dispara sem reason atual;
  R1+R3 combinados; should_show=false quando já selecionado;
  determinismo; contract shape; constants lock.
- Suite consolidada BF: **44/44 verde** (10 MEC + 9 canonical + 12 e2e_systemic + 13 suggestion).
- E2E validado via curl: atestado de 8 dias → response com `suggested_reason_subcode: "1a"`, `confidence: 1.0`, rule e explanation corretos.

#### NÃO implementado (intencionalmente — owner spec)
- ❌ Score composto / ranking probabilístico
- ❌ Múltiplas sugestões simultâneas
- ❌ Frontend integration (próxima rodada — só após observar uso real)
- ❌ Persistência de log de sugestões aceitas/rejeitadas



### Bolsa Família — Layer 1 P0 Fix: Frequência Válida Canônica **[Fev/2026]**

Correção crítica isolada: o módulo Bolsa Família mantinha **engine paralela**
de contagem de faltas que NÃO descontava atestados médicos nem aplicava
defesa em profundidade para `dependency_id`. Resultado: alunos com atestado
podiam aparecer com baixa frequência indevidamente no relatório oficial.

**Decisão arquitetural do owner:** apenas Layer 1 nesta rodada — fix isolado,
centralização em fonte única, ZERO refatoração de schema/UX. Layers 2
(`absence_type` granular) e 3 (suggestion engine MEC) ficam P1/P2 para
rodada arquitetural dedicada.

#### Fonte única de verdade
- Nova função `services/attendance_utils.compute_monthly_valid_absences(
  attendance_docs, medical_days_by_student, student_ids)` aplica as regras
  canônicas Fev/2026 (alinhadas ao `compute_attendance_buckets` e ao PDF
  de frequência da turma):
  - Atestado médico **vence** o status original → NÃO conta como falta.
  - Status `J` (justificado pelo professor) → NÃO conta como falta.
  - `dependency_id` em registro → ignorado (defesa P0 em profundidade).
  - Aceita aliases legados (`absent`, `ausente`, `falta`, `A`).
- Wrapper assíncrono `fetch_medical_days_for_students(db, student_ids,
  academic_year)` busca em batch os `medical_certificates` do ano e
  retorna `{student_id: Set[YYYY-MM-DD]}`. Desacoplado do I/O.

#### Refatoração `routers/bolsa_familia.py`
- Engine paralela REMOVIDA (eliminada lógica duplicada nas linhas 339 e 600).
- `list_bolsa_familia_students` e `generate_bolsa_familia_pdf` agora consomem
  `compute_monthly_valid_absences` → consistência garantida com declaração
  de frequência, relatório de turma e boletim.
- Fórmula final do BF: `((dias_letivos - faltas_VÁLIDAS) / dias_letivos) * 100`
  onde `faltas_válidas` exclui atestados, J e dependência.

#### Tabela de aceite (4 casos obrigatórios validados)
| Cenário                            | Antes (bug)  | Depois (canônico) |
|------------------------------------|--------------|-------------------|
| 20 dias, 5 faltas comuns           | 75% ✓        | **75%** ✓         |
| 20 dias, 5 atestados               | 75% ❌       | **100%** ✓        |
| 20 dias, 5 justificadas            | 100% ✓       | **100%** ✓        |
| 20 dias, 3 faltas + 2 atestados    | 75% ❌       | **85%** ✓         |

#### Tests
- `tests/test_bolsa_familia_frequency_canonical.py` — 9 unit (100% verde):
  4 casos obrigatórios do owner + 5 defesas (dependency ignorado, filtro
  de student_ids, split por mês, records vazios/inválidos, aliases legados).
- Suite consolidada relacionada: 45/45 verde (BF MEC + canonical +
  attendance PDF + atestado + bimestre + filter course). Zero regressões.

#### Backlog explícito (NÃO implementado nesta rodada)
- ❌ `absence_type` granular (COMMON / SCHOOL_ACTIVITY / TRANSPORT / JUDICIAL / FAMILY / DISCIPLINARY)
- ❌ Campo `counts_for_frequency` configurável por registro
- ❌ `attachment_id` em registros de frequência
- ❌ Suggestion engine BF ↔ Motivos MEC (sugerir reason_id automaticamente
  baseado em padrão de absence_type)
- ❌ UI nova de tipos de ausência no diário



### Bolsa Família — Integração Motivos Oficiais MEC v4.2 **[Fev/2026]**

Refatoração arquitetural transformando o módulo Bolsa Família de "input text livre
de motivo" para **dado institucional estruturado compatível com Sistema Presença MEC**.
Pré-requisito para o futuro Núcleo de Busca Ativa Escolar.

#### Schema (novas coleções)
- `attendance_frequency_reason_groups`: 25 grupos oficiais MEC v4.2
  `{id, mec_code, name, category, mec_version, source, active, sort_order, created_at, updated_at}`
- `attendance_frequency_reasons`: 58 submotivos (57 ativos + 1 legacy "24z")
  `{id, group_id, mec_group_code, mec_subcode, name, severity_level, requires_followup,
  legacy, mec_version, source, active, created_at, updated_at}`
- `bolsa_familia_tracking` refatorado:
  - Adicionado: `reason_id` (FK) + `notes` (texto livre opcional)
  - Mantido: `motive_legacy` (preserva dados pré-refatoração — auditoria/PDFs antigos)

#### Seed institucional versionado
- `/app/backend/seeds/mec/attendance_frequency_reasons.v4.2.json` — fonte da verdade
  com `version: "4.2"`, `source: "Sistema Presença MEC"`, 25 grupos + 58 submotivos.
- `/app/backend/seeds/seed_mec_frequency_reasons.py` — upsert idempotente
  (chave natural: `mec_code` para grupos, `mec_subcode` para submotivos).
- Plugado em `startup/seeds.run_all_seeds`.

#### Índices Mongo (criados em `startup/indexes.py`)
- `attendance_frequency_reason_groups`: `id` unique, `(mec_code, mec_version)` unique,
  `(active, sort_order)`
- `attendance_frequency_reasons`: `id` unique, `(mec_subcode, mec_version)` unique,
  `(group_id, active)`, `(mec_group_code, mec_subcode)`
- `bolsa_familia_tracking`: `(school_id, academic_year, month, student_id)` lookup,
  `reason_id` sparse

#### Endpoints (em `routers/bolsa_familia.py`)
- `GET /api/bolsa-familia/reason-groups?mec_version=4.2`
- `GET /api/bolsa-familia/reasons?group_id&mec_version&include_legacy=false`
- `GET /api/bolsa-familia/reasons/grouped` — shape pronto para Combobox UI
- `PUT /api/bolsa-familia/tracking` — aceita `{reason_id, notes, motive_legacy?}`.
  Valida `reason_id` (422 se inválido). Mantém compatibilidade com payload legacy `motive`.
- `PUT /api/bolsa-familia/tracking/bulk` — mesma validação, pré-carrega ids válidos
  em 1 query para evitar N+1.
- `GET /api/bolsa-familia/students/{...}` agora retorna `reason_id + notes + motive_legacy`
  por mês.
- `GET /api/bolsa-familia/pdf/{school_id}` — PDF resolve `reason_id` para texto
  `{mec_subcode} - {name} — {notes}`; fallback para `motive_legacy` em registros antigos.

#### Frontend
- `/app/frontend/src/components/ReasonCombobox.jsx` — Combobox shadcn Command com
  agrupamento visual + busca por nome / código MEC (3a, 11a) + navegação por teclado.
- `/app/frontend/src/pages/BolsaFamilia.js` refatorado:
  - Coluna "Motivo Oficial MEC" (Combobox) + coluna "Observações" (texto livre).
  - **Política de visibilidade**: freq ≥ 75% → combobox desabilitado com mensagem
    "Frequência ≥ 75% — motivo não obrigatório". Freq < 75% → combobox obrigatório
    com borda âmbar. Freq null → opcional habilitado.
  - Banner informativo do MEC, contador de "registros < 75% sem motivo" no header.

#### Decisões arquiteturais (decisão owner)
- ✅ Motivo PRINCIPAL único + observações complementares (NÃO múltiplos motivos).
- ✅ `motive_legacy` preservado para auditoria/PDFs antigos (compatibilidade retroativa).
- ✅ PDF reflete UI sem persistência (NÃO snapshot verificável agora — operacional).
- ✅ `severity_level` / `requires_followup` são metadados de backend (reservados para
  Busca Ativa Escolar futura — não exibidos na UI principal).
- ✅ Reuso do submotivo `24z - Não classificado (legado)` para match futuro de
  registros pré-refatoração via job assíncrono (não bloqueia P0).

#### Tests
- `/app/backend/tests/test_bolsa_familia_mec.py` — 10 E2E HTTP (100% verde):
  groups=25, reasons=57 (sem legacy) / 58 (com legacy), filtro por group_id, shape
  agrupado, save com reason_id, 422 para reason_id inválido, compat motive legacy,
  bulk com mix válido/inválido, novo shape no list.


### Verifiable Documents MVP — Autoridade Verificável **[Fev/2026]**

Transforma o SIGESC em **autoridade verificável de emissão documental**:
qualquer terceiro (universidade, empresa, secretaria, auditor, responsável)
verifica autenticidade/integridade/validade/revogação/substituição sem login.

#### Backend `services/verifiable_docs_service.py`
- **`verification_token`** UUID hex 32 chars (opaco) gerado em toda emissão.
  Distinto do `code` humano (`SIGESC-XXXX-XXXX`). É o que vai no QR.
- `resolve_either(db, identifier)` — resolve transparentemente por code OU token.
- `resolve_token(db, token)` — busca direta por token UUID.
- `add_signature(db, code_or_token, *, role, full_name, signed_by_user_id)`
  — empilha assinatura institucional. Signatures NÃO mutam `document_hash_sha256`
  (hash congelado na emissão; assinaturas geram hashes derivados separados).
- `supersede_document(db, *, old, new, user)` — marca `old` com
  `superseded_by_document_id=new.code` + `superseded_at`. Estado distinto
  de revogação: documento permanece consultável publicamente como histórico.
- `backfill_verification_tokens(db)` — preenche `verification_token` em docs
  pré-existentes; idempotente; rodado no startup do FastAPI.
- Schema enriquecido: `schema_version="1"`, `template_version`, `document_type`
  (alias canônico de `type`), `student_id`, `school_id`, `render_job_id`,
  `file_id`, `signatures: []`, `superseded_by_document_id`.
- `build_portal_response(doc)` — 5 estados (`valido | substituido | revogado |
  expirado | invalido`) com `assinaturas[]` LGPD-safe (apenas role + full_name +
  signed_at; ZERO user_id/email/CPF/matrícula).
- Indexes: `verification_token` UNIQUE sparse, `student_id` sparse, `school_id` sparse.

#### Router `routers/verifiable_docs.py`
- `GET /api/public/verify/{identifier}` — público, rate-limited 20/min, aceita
  CODE (`SIGESC-XXXX-XXXX`) OU TOKEN (UUID hex 32). LGPD-safe.
- `POST /api/documents/{code}/signatures` — `{role, full_name}`. Apenas
  super_admin/admin/secretario/diretor.
- `POST /api/documents/{code}/supersede` — `{new_code | new_token}`. Apenas
  super_admin/admin/secretario.
- Endpoints existentes preservados (list, get, revoke, ensure-for-snapshot).

#### Resolução de colisão de rota
`dependency_completions.public_verify` (registrado primeiro) agora **delega**
para `verifiable_docs_service.resolve_either` quando o identificador não
corresponde a uma completion — mantém ambos contratos coexistentes.

#### QR / PDF
- `pdf/verification_footer.py` agora aceita `verification_token` opcional;
  quando presente, QR carrega URL CURTA `/v/{token}` (owner spec). Code
  humano permanece visível no rodapé para digitação manual.
- `services/school_doc_templates._validity_footer` lê `context["verification_token"]`
  e injeta no QR.
- `routers/school_documents.get_pdf` propaga `verification_token` do `vdoc`.

#### Frontend
- Nova rota pública `/v/:token` — reusa `VerifyPublic.jsx` (zero duplicação).
- `VerifyPublic` reconhece tanto code (`/verificar/:code`) quanto token
  (`/v/:token`); normalização client-side aceita ambos formatos.
- Card de resultado renderiza:
  - Estado `substituido` (badge azul + RefreshCw) com referência ao sucessor.
  - Bloco "Assinaturas Institucionais" com lista de role + full_name + data
    (LGPD-safe — backend filtrou).
  - 5 estados visuais: valido (verde), invalido (vermelho), revogado (âmbar),
    expirado (âmbar), substituido (azul).

#### Tests
- `tests/test_verifiable_docs_mvp.py` (10 E2E HTTP):
  - Verifica por code + token, LGPD safety, identifier desconhecido,
    add_signature (sucesso + LGPD-safe + 400 sem campos), supersede
    (sucesso + 400 mesmo doc + 404 desconhecido), formato UUID hex token.
- **142 verde + 1 skipped** na suite consolidada (verifiable_docs_mvp +
  school_documents_delete + dep_completions + bulletin + render_jobs +
  closure + lens + isolation P0). Zero regressões.

#### Backlog explícito (NÃO implementado)
- ❌ ICP-Brasil / certificado A1/A3
- ❌ Assinatura criptográfica pesada (X.509)
- ❌ Blockchain
- ❌ Timestamp authority externa
- ❌ Watermarking complexo / antifraude sofisticado



### Passo 5 — Boletim Online MVP **[Fev/2026]**

Read-model pedagógico do boletim — escopo MÍNIMO autorizado pelo owner:
"validar modelo pedagógico antes de transformar em documento oficial".

#### `utils/bulletin_builder.py` (lógica pura)
- `build_student_bulletin(db, student_id, academic_year, mantenedora_id)`
  → consome `compute_composite_closure(...)` (NUNCA o diário vivo).
- Para cada período do closure, lê `db.grades` filtrando por `class_id` (imutável
  cf. ACADEMIC_EVENT_CONTRACT §6.1) com `with_regular_only` — registros de
  dependência ficam em lista paralela `dependency_components`.
- Frequência por segmento via `attendance.records[]` filtrado pela janela do período.
- Bimestres atribuídos ao período pelo `assign_bimesters_to_periods` (já validado
  no Passo 3) — frontend destaca quais bimestres "fecham" em cada turma.
- Read-only puro: NÃO persiste nada, NÃO calcula média final cross-period
  (responsabilidade do Histórico Escolar Fase 4).

#### Router `routers/bulletins.py`
- **Único endpoint canônico**: `GET /api/students/{student_id}/bulletin?academic_year=YYYY`
- READ-ONLY ABSOLUTO — POST/PUT/DELETE não definidos (405).
- Permissões: super_admin, admin*, gerente, secretario, diretor, coordenador,
  apoio_pedagogico, professor, semed*. Aluno só vê o próprio boletim;
  responsável só vê alunos vinculados.
- Tenant-scoped via `apply_tenant_filter`.

#### Shape canônico do payload
```json
{
  "bulletin_version": "1",
  "student": {id, full_name, registration_number, dependency_mode},
  "academic_year": YYYY,
  "primary_school": {id, name},
  "primary_class": {id, name, grade_level, education_level},
  "is_composite": true|false,
  "composite_segments": [
    {
      "period_index": N,
      "class": {...}, "school": {...},
      "period_start", "period_end",
      "source": "origin"|"destination"|"sole",
      "governing_event_id", "governing_event_type", "governing_effective_date",
      "bimesters_owned": [1,2,...],
      "components": [{
        "course_id", "course_name", "atendimento_programa", "optativo",
        "is_dependency": false,
        "bimesters_owned_by_this_period": [1,2,...],
        "grades": {b1, b2, b3, b4, rec_s1, rec_s2, recovery, final_average, status},
        "absences_in_period": N
      }],
      "attendance_summary": {total_records, present, absent, frequencia_pct, absences_by_course}
    }
  ],
  "dependency_components": [...],
  "warnings": [...]
}
```

#### Frontend `pages/BulletinViewer.jsx` em `/admin/bulletins`
- READ-ONLY puro: sem botões de edição, sem PDF, sem print, sem download,
  sem assinatura, sem QR, sem hash visível.
- Busca de aluno via `useStudentSearch` (autocomplete server-side existente).
- Seletor de ano letivo.
- Cabeçalho: nome, matrícula, escola/turma vigente, badge `Composto/Simples`,
  modo de dependência (se aplicável).
- Por segmento: nome da turma, escola, intervalo de datas, source badge
  (origem/destino/única), tipo de evento, bimestres "donos", tabela de
  componentes com B1..B4 destacados quando o bimestre é "fechado por esta turma"
  (cinza claro caso contrário), recuperações, média, faltas e resumo de frequência.
- Seção paralela de componentes em dependência (faixa âmbar) — não contamina regular.
- Acessível para super_admin, admin*, gerente, secretario, diretor, coordenador,
  apoio_pedagogico, professor, semed*.

#### Backlog explícito (NÃO implementado conforme orientação do owner)
- ❌ PDF, HTML institucional, QR, hash visível, assinatura, snapshot de boletim
- ❌ render_jobs (camada Fase 6)
- ❌ CSS print (UX ainda não validada — adiar)
- ❌ Gráficos, analytics, comparativos, badges excessivos, timeline, IA, exportação
- ❌ Edição/mutação/ações administrativas
- ❌ Cache `composite_periods_summary` (otimização adiada — owner classificou "antes da dor")

#### Tests
- `tests/test_bulletin_builder.py` (7 unit) — segmento sole, transferência com
  notas filtradas por class_id, atribuição de bimestres, dependência paralela,
  aluno desconhecido, frequência ignorando dependency_id, shape canônico.
- `tests/test_bulletin_e2e_http.py` (6 E2E HTTP) — shape canônico, 404, 401/403,
  422 ano fora do range, campos obrigatórios em segmentos, POST não permitido (405).
- **139/139 pytests verdes** na suite consolidada (bulletin + render_jobs +
  closure + lens + dep_completions + isolation P0 + diary phase 2). Zero regressões.



### Passo 4 — Document Render Jobs (escopo mínimo) **[Fev/2026]**

Fila de geração de documentos PDF com persistência, idempotência e retry —
ESCOPO ENXUTO autorizado pelo owner. Sem broker/worker distribuído/pipeline
paralelo nesta V1.

#### `utils/render_jobs.py` (lógica pura + registry)
- `compute_idempotency_key(source_snapshot_id, document_type, template_version,
  render_engine_version)` → SHA-256 determinístico (64 chars).
- `compute_next_retry_at(retry_count)` → ISO timestamp aplicando backoff
  exponencial fixo `(30s, 2min, 10min)` (`MAX_RETRIES = 3`).
- `register_render_handler(document_type, fn)` — registry in-process
  (handlers do Boletim/Histórico se plugarão aqui em fases posteriores).
- `ensure_indexes(db)` — idempotency_key UNIQUE, status+next_retry_at,
  source_snapshot_id+document_type, mantenedora_id, requested_at desc.

#### `services/render_worker.py` (single-process loop)
- `run_worker_loop(db, stop_event)` — task asyncio iniciada no startup do FastAPI
  (`server.py`), poll a cada 5s. Pode ser desabilitado via env
  `DISABLE_RENDER_WORKER=true` (útil em testes).
- `_claim_next_job(db)` — atomic `find_one_and_update` (status pending +
  next_retry_at <= now), ordenando por requested_at ASC (FIFO).
- Handler ausente → `failed` IMEDIATO sem retry (`NO_HANDLER_REGISTERED`).
- Handler levanta exceção → `retry_count++` com `next_retry_at` agendado;
  após `MAX_RETRIES` → `failed` permanente.
- Sucesso → `completed` com `generated_file_id`, `pdf_hash_sha256`,
  `duration_ms` no audit_trail.
- Shutdown limpo via `stop_event` no `@app.on_event("shutdown")`.

#### Router `routers/render_jobs.py`
- `POST /api/render-jobs` — cria job (idempotente). Resposta:
  `{id, status, idempotent_hit, handler_registered, job}`. Header
  `force_reissue:true` no payload marca o anterior como `superseded` (se ainda
  pending/processing) e cria novo job com idempotency_key sufixada `#rN`.
- `GET /api/render-jobs/{id}` — status + audit_trail completo.
- `GET /api/render-jobs?source_snapshot_id&document_type&status&page&page_size` —
  lista paginada (max 100/page) ordenada por requested_at desc.
- `POST /api/render-jobs/{id}/retry` — admin+ força retry de job `failed`
  (zera retry_count, retorna a `pending`). HTTP 409 se job já `completed`
  (use `force_reissue` em POST) ou `processing`.

#### Schema `db.document_render_jobs` (V1 mínimo)
```
{
  id, idempotency_key (UNIQUE), document_type, source_snapshot_id,
  source_collection, template_version, render_engine_version,
  render_options, payload_hash,
  status: pending|processing|completed|failed|superseded,
  retry_count, max_retries=3, next_retry_at,
  generated_file_id, generated_file_size_bytes, pdf_hash_sha256,
  generated_at, started_at, completed_at, failed_at, error_message,
  requested_by_user_id, requested_at, request_ip, request_user_agent,
  mantenedora_id, school_id,
  audit_trail: [{action, at, ...}]
}
```

#### Tests
- `tests/test_render_jobs.py` (10 unit) — idempotency_key determinístico,
  tabela de backoff conforme contrato, sucesso, retry+sucesso, failed
  permanente após MAX_RETRIES, NO_HANDLER_REGISTERED, fila vazia,
  jobs com retry futuro são pulados, FIFO por requested_at.
- `tests/test_render_jobs_e2e_http.py` (9 E2E HTTP) — create pending,
  idempotente, get status, list paginado, 422 INVALID_DOCUMENT_TYPE,
  force_reissue cria novo, retry de failed, 404 desconhecido, 401/403 sem auth.
- **126/126 pytests verdes** na suite consolidada (render + closure + lens
  + dep_completions + isolation P0 + diary phase 2). Zero regressões.

#### Backlog explícito do owner (NÃO tocar nesta V1)
- ❌ Worker distribuído / Kafka / RabbitMQ / SQS
- ❌ Pipeline paralelo, prioridade dinâmica, dead-letter queue sofisticada
- ❌ Cache multicamada de PDF
- ❌ Endpoints `/file` (download) e `/public/render-jobs/{token}/file` —
  reservados para fase do Boletim/PDF (handlers ainda não existem)
- ❌ Observabilidade dedicada do canal `render_jobs` — backlog

#### Next-up (mantém ordem do owner)
1. **Boletim Online** — consome `compute_composite_closure(...)` direto,
   sem PDF. Alto valor percebido com pouco código.
2. **PDF institucional** — registra handler `bulletin` em `register_render_handler`,
   integra com snapshot + verifiable_docs (QR/hash/assinatura).
3. **Histórico Escolar** — só após boletim estabilizar.



### Fase 3 — Fechamento Temporal Composto (Passo 3) **[Fev/2026]**

Núcleo do fechamento pedagógico: aluno movimentado tem fechamento **composto**
— sequência de janelas onde cada turma é dona apenas do seu intervalo.

#### `utils/temporal_closure.py` (lógica pura, read-model)
- `compute_temporal_periods(db, student_id, academic_year, mantenedora_id)` →
  lista cronológica e contígua de períodos `{period_index, class_id, course_id,
  school_id, period_start, period_end, source: origin|destination|sole,
  governing_event_id, governing_event_type, governing_effective_date}`.
- Algoritmo: breakpoints = `{year_start, *each effective_date, year_end+1}`;
  para cada segmento, governante via `pick_governing_event` da lente temporal
  (precedência §15: reclassificacao > progressao_parcial > remanejamento > transfer).
- Funde períodos consecutivos com mesma turma + mesmo evento (idempotência visual).
- `compute_class_window_for_student(...)` retorna envelope `{envelope_start,
  envelope_end, segments}` ou `None` se a turma nunca foi dona do aluno.
- `assign_bimesters_to_periods(bimester_calendar, periods)` atribui cada
  bimestre ao período cujo intervalo contém a DATA FINAL do bimestre
  (regra de "fechamento" semântica, não proporcional).
- `compute_composite_closure(...)` agrega tudo em shape canônico
  `{closure_version: "1", periods, bimesters, is_composite}` para Boletim
  e Histórico futuros consumirem.

#### Router `routers/closure.py` (somente leitura V1)
- `GET /api/closure/student/{sid}/composite?academic_year=Y` — fechamento completo.
- `GET /api/closure/student/{sid}/window?academic_year=Y&class_id=C` — janela
  de uma turma; HTTP 404 `NO_WINDOW_FOR_CLASS` se nunca foi dona.
- `GET /api/closure/class/{cid}/students?academic_year=Y` — alunos com janela
  na turma (origem ou destino), unindo enrollments + academic_events.
- `GET /api/closure/student/{sid}/periods?academic_year=Y` — endpoint enxuto
  só com a lista de períodos.
- Permissões: super_admin, admin, gerente, secretario, diretor, coordenador,
  apoio_pedagogico, professor, semed*. Tenant-scoped via `apply_tenant_filter`.

#### Invariantes obeídos
- Closure é read-model **derivado** — nunca persiste janelas em coleção própria.
- Eventos `pending` ou `superseded` NUNCA contam como governantes.
- Precedência §15 idêntica à `resolve_student_ownership` (single source of truth).
- Bimestres órfãos (data fora de qualquer período) recebem `period_index=None`
  sem quebrar o payload — caso patológico legítimo (aluno saiu antes).

#### Contrato `ACADEMIC_EVENT_CONTRACT.md` §21 (NOVO)
Documenta princípio, algoritmo, atribuição de bimestres, endpoints e invariantes.

#### Tests
- `tests/test_temporal_closure.py` (11 unit) — sole, transfer simples,
  pendente/superseded ignorados, múltiplos eventos, precedência, atribuição
  de bimestres, envelope, órfão, shape canônico.
- `tests/test_closure_e2e_http.py` (8 E2E HTTP) — todos os endpoints +
  401 sem auth + 404 aluno desconhecido.
- **107/107 pytests verdes** na suite consolidada (closure + lens + dep_completions
  + isolation P0 + diary phase 2). Zero regressões.



### Dependência de Estudos — Fase 1 **[Fev/2026]**

**Diretriz arquitetural OBRIGATÓRIA — ver `/app/docs/STUDENT_DEPENDENCY.md`**

- **Princípio**: dependência é **entidade acadêmica própria** (NÃO matrícula simplificada). Modelagem como enum `dependency_mode` (não 2 booleanos) elimina estados inválidos.
- **Modelo**: `Student.dependency_mode: Literal['none', 'with_dependency', 'dependency_only']` + coleção `student_dependencies` com `origin_academic_year` (ano de origem da reprovação) + status (`active|completed|failed|cancelled`).
- **Endpoints**: `/api/student-dependencies` (POST/PUT/DELETE), `/student/{id}` (lista), `/student/{id}/summary` (contadores), `/class/{cid}/course/{coid}` (alunos em dep para diário Fase 2).
- **Validações**:
  - Aluno deve ter `dependency_mode != 'none'`.
  - Mantenedora deve permitir o modo (`aprovacao_com_dependencia` ou `cursar_apenas_dependencia`).
  - Limite de componentes lendo da mantenedora.
  - Duplicidade impedida por índice único parcial `(student_id, course_id, origin_academic_year)` quando `status=active`.
  - Tenant scope obrigatório.
- **Permissões**: manage = `super_admin, admin, admin_teste, gerente, secretario, diretor`. View = manage + coordenador, apoio_pedagogico, professor, semed*.
- **Frontend**: `<StudentDependencySection />` em `/app/frontend/src/components/StudentDependencySection.jsx`. Plugado na aba "Info. Complementares" do StudentsComplete. Renderiza radio dinâmico (opções dependem das flags da mantenedora) + card resumido + lista + modal de vincular componente (turma + curso + ano de origem).
- **Auditoria**: `audit_service.log` em create/update/delete com `collection='student_dependencies'`.
- **Tests**: 7 pytests cobrindo permissões, limite, duplicidade, summary, modos não habilitados.
- **Roadmap**: Fase 2 = diário; Fase 3 = boletim online + PDF + ficha; Fase 4 = fechamento anual + histórico.

### Fase 3 — Academic Events + Lens Temporal **[Fev/2026]**

Núcleo de governança temporal pedagógica. Implementa o passo 1 da sequência
do owner (`academic_events → observability → fechamento → render_jobs → boletim → PDF → histórico`).

#### `db.academic_events` (CRUD + supersession)
- 4 tipos: `transfer | remanejamento | reclassificacao | progressao_parcial`.
- Fluxo §10: rationale ≥30 chars + role autorizado + `X-Academic-Event-Confirm: true` em supersedes.
- Endpoints: `POST /` (cria pending), `POST /{id}/approve`, `POST /{id}/reject`, `POST /{id}/supersede`,
  `GET /{id}`, `GET /student/{student_id}`.
- Eventos NUNCA deletados — supersession cria novo + marca antigo como `superseded` com `superseded_by_event_id`.
- Validação: `ORIGIN_EQUALS_DESTINATION` (422), `INVALID_TRANSITION` (409), `CONFIRMATION_REQUIRED` (428).

#### `utils/academic_event_lens.py` — autoridade ÚNICA
- `resolve_student_ownership(db, student_id, class_id, course_id, target_date, mantenedora_id)` retorna
  `{decision_version: "1", editable, visible, owner_teacher_id, source: "origin|destination|neutral",
  sync_mode: "origin_authoritative|isolated|neutral", historical_cutoff_date, blocked_reason,
  governing_event_id, governing_event_type, governing_effective_date}`.
- **Timezone institucional** (campo `mantenedoras.timezone`, default `America/Sao_Paulo`).
  `_to_date()` resolve qualquer entrada (str ISO, datetime UTC/naïve, date) no tz correto antes de comparar.
- **Precedência fixa V1**: `reclassificacao > progressao_parcial > remanejamento > transfer`.
  Tiebreaker: `effective_date` mais recente; depois `created_at` mais recente.
- `pick_governing_event(events)` ignora `pending` e `superseded`.
- `annotate_items_with_lens(items, ...)` — anota `_locked, _inherited, _lock_reason,
  _governing_event_id, _governing_event_type, _historical_cutoff_date` em listas de items SEM filtrar
  (cf. §16: rastreabilidade preservada SEMPRE — `visible: true` não muda).
- `record_lock_audit(...)` grava em `db.academic_event_audit` com payload_hash, IP, user_agent,
  reason_code, target_resource — sem PII.

#### Integração nos endpoints
- `POST /api/grades` e `POST /api/grades/batch` chamam lens antes de gravar; HTTP 409
  `ACADEMIC_EVENT_LOCK` + audit log + reason_code.
- `POST /api/attendance` valida lens por record (cada aluno pode estar bloqueado independentemente);
  usa `attendance.date` como `target_date` (não a data de hoje).
- `GET /api/diary/class/{cid}/course/{coid}` enriquece cada item com flags da lens — frontend
  reflete badges sem decidir localmente (§19).

#### Snapshots ganharam reservas para invalidação documental
`dependency_completions` agora inclui placeholders mutáveis (excluídos do hash):
- `invalidated_by_event_id`, `invalidated_at`, `invalidation_reason`, `supersedes_document_id`.
- Cascade automática reservada para Fase 3+ (quando alterações em registros pré-effective_date
  forem implementadas via origin_authoritative sync).

#### Contratos atualizados/criados
- **`ACADEMIC_EVENT_CONTRACT.md`** §15-19 adicionados:
  §15 Precedência fixa V1 (não configurável), §16 Princípio de Persistência Pedagógica
  (rastreabilidade NUNCA removida), §17 Supersession + Timezone institucional, §18
  ACADEMIC_EVENT_LOCK formato canônico de audit, §19 Frontend não infere lock localmente.
- **`RENDER_JOBS_CONTRACT.md`** **NOVO CONGELADO V1**: 12 seções normativas para `db.document_render_jobs`
  (PDF é consequência do snapshot, nunca fonte; pipeline `pending→processing→completed|failed`;
  retry exponencial; idempotência; reemissão fiel; retenção 7 anos; integração com snapshots
  imutáveis; templates versionados; observabilidade dedicada). Implementação reservada para passo 4.

#### Tests (Iteration 74 — testing_agent_v3_fork)
- **12/12 pytests** novos (`test_academic_event_lens.py`)
- **140/140 suite consolidada** verde (12 lens + 17 completions + 40 P0 + 19 Fase 2 + 11 pre + 9 obs + 26 deps + 6 autocomplete)
- **9/9 E2E HTTP verdes** (rationale<30→422, ORIGIN_EQUALS_DESTINATION, create→approve, supersede(428|200), POST grade bloqueada, POST attendance bloqueada, audit gravado, diário anotado sem filtrar)
- **Zero issues** reportados.



### Fase 2.5 — Snapshots Documentais Imutáveis + Contrato de Eventos Acadêmicos **[Fev/2026]**

Pré-requisito jurídico para Boletim (Fase 3) e Histórico (Fase 4). Owner pediu
"verdade documental imutável ANTES de PDF" — esta rodada entrega exatamente isso.

#### `db.dependency_completions` (append-only)
- Hook em `PUT /api/student-dependencies/{id}` cria snapshot automaticamente em
  transições `active → completed | failed | cancelled`. Idempotente (não duplica).
- **Snapshots capturados** (imutáveis): `original_course_name_at_completion`,
  `original_curriculum_version`, `original_academic_year`, `original_class_id`,
  `workload_hours`. Sobrevivem a reorganização curricular futura.
- **`cancelled` exige `status_reason`** (HTTP 422 `CANCELLATION_REASON_REQUIRED`).
  Cancelado vira `data_quality=incomplete` e `document_status=cancelado_administrativamente`
  no público (não compõe boletim padrão).

#### Hash documental imutável `/app/backend/utils/document_hash.py`
- `document_hash_sha256` calculado UMA vez na criação. NUNCA recalculado.
- Excluem do hash: `signatures[]`, `verification_token`, `revoked_at`,
  `revoked_reason`, `superseded_by_document_id`, `audit_trail[]`,
  `document_hash_sha256` (não entra em si mesmo), `_id`.
- Cada assinatura tem **`signature_hash_sha256` próprio** referenciando
  `signed_document_hash` (o original) — adicionar 2ª assinatura NÃO invalida a 1ª.
- `verify_document_hash()` detecta tampering pós-emissão.

#### Endpoints implementados
- `GET /api/dependency-completions/student/{student_id}` — lista snapshots do aluno.
- `GET /api/dependency-completions/{id}` — snapshot completo com audit_trail.
- `POST /api/dependency-completions/{id}/sign` — assinatura institucional;
  - HTTP 409 `DATA_QUALITY_INSUFFICIENT` se snapshot é `partial`/`incomplete`
  - HTTP 409 `DOCUMENT_REVOKED` se já revogado
  - HTTP 409 `ROLE_ALREADY_SIGNED` (anti-duplicidade)
  - super_admin pode assinar via `X-Sign-As-Role: diretor|secretario`
- `POST /api/dependency-completions/{id}/revoke` — exige `rationale` ≥ 30 chars,
  marca `revoked_at` SEM alterar `document_hash_sha256`.
- `GET /api/public/verify/{verification_token}` — **endpoint sem auth**;
  mapeia `completion_result` → `document_status` jurídico (`valido`,
  `valido_reprovado`, `cancelado_administrativamente`, `revogado`,
  `nao_encontrado`); NÃO expõe nome do aluno, CPF ou enum interno;
  signatures sanitizadas (apenas role + nome + signed_at).
- `POST /api/admin/dependency-completions/backfill?dry_run=true|false` —
  super_admin only, idempotente, calcula `data_quality` híbrido (complete/partial/incomplete).

#### Índices
- `verification_token` UNIQUE (criado no startup) — evita colisão silenciosa em retries.
- `(dependency_id, completion_academic_year)`, `(student_id, issued_at desc)`, `mantenedora_id`.

#### Versionamento documental
- `document_version: "1.0.0"` (layout/legenda)
- `history_schema_version: "1"` (shape de dados)
- `template_version`, `render_engine_version` — placeholders preenchidos quando o PDF for gerado (Fase 3).

#### Contrato `ACADEMIC_EVENT_CONTRACT.md` **CONGELADO V1**
14 seções normativas cobrindo `transfer | remanejamento | reclassificacao |
progressao_parcial`. Princípios:
- Movimentações **NÃO removem** o aluno da turma de origem.
- Lente temporal: pré-`effective_date` editável pela origem (read-only no destino com badge "herdado");
  pós-`effective_date` exclusivo do destino (origem bloqueada com marcador "Aluno movimentado em DD/MM").
- **NÃO duplicar registros fisicamente** — usa read-model temporal (`utils/academic_event_lens.py` quando implementado).
- Audit log obrigatório para tentativas bloqueadas (HTTP 409 `ACADEMIC_EVENT_LOCK`).
- Eventos NÃO deletáveis — mudança = supersession (novo evento com `supersedes_event_id`).
- Fluxo §10 obrigatório para alterações: rationale ≥ 30 chars + role autorizado +
  `X-Academic-Event-Confirm: true` + auditoria + snapshot before/after.
- Implementação codificada para futura rodada (P2/P3) — apenas contrato congelado nesta.

#### Atualizações nos contratos existentes
- `HISTORICO_ESCOLAR_CONTRACT.md` §14: regras de imutabilidade + assinatura.
- `DIARY_API_CONTRACT.md` §31: `dependency_completions` é fonte documental;
  `student_dependencies` permanece como fonte operacional.

#### Tests (Iteration 73 — testing_agent_v3_fork)
- **17/17 pytests internos** + **128/128 suite consolidada** + **9/9 E2E HTTP** verdes.
- Cobertura: hash determinístico, hash imutável após múltiplas assinaturas, signature_hash isolado, hash detecta tampering, hook idempotente, cancelled exige reason, data_quality híbrido, document_status mapping (não expõe enum), verification_token único, revoke não altera hash, public/verify revogado.
- **Zero issues** reportados.



### P0 — Blindagem Pedagógica + P1a + P1b + P2 + Contrato Histórico **[Fev/2026]**

Cinco entregas coesas em uma única rodada para fechar a maturidade do subdomínio
"Dependência" antes da Fase 3.

#### P0 — Dependência NÃO contamina cálculo regular
- **Helper canônico** `/app/backend/utils/grade_dependency_filters.py`:
  - `regular_only_filter()` / `regular_only_aggregate_match()` / `with_regular_only()` — filtros Mongo
  - `is_regular_grade()` / `is_regular_attendance_record()` / `keep_regular_only()` — defesa Python (última barreira)
  - Docstring crítico explicando POR QUÊ não remover o helper.
- **Aplicado em** `routers/analytics.py`: 6 pipelines de notas + 3 pipelines attendance (após `$unwind: $records`) protegidos via Mongo match.
- **Aplicado em** `routers/attendance.py /report/class`: defesa Python no loop de cálculo de %.
- **3 pytests críticos** (em `test_dependency_isolation_p0.py`):
  - `test_dependency_grade_not_affect_regular_average`
  - `test_dependency_attendance_not_affect_regular_frequency`
  - `test_dependency_student_not_counted_twice_in_reports`

#### P1a — Centralização React `/frontend/src/features/dependency/`
- `dependency.constants.js` — `DEPENDENCY_STATUS`, `DEPENDENCY_TYPE`, `DEPENDENCY_DISPLAY_LABEL`, `DEPENDENCY_SECTION_TITLE`.
- `dependency.utils.js` — funções puras: `isDependencyItem`, `getDependencyId`, `splitRegularAndDependency`, `shouldShowDependencyDivider`, `resolveDependencyPayloadField`, `isActiveStatus`, `isDependencyOnly`, `hasParallelDependency`. **Sem state. Sem hooks. Sem context. Sem HOC.**
- `DependencyBadge.jsx` — componente único do badge âmbar.
- `DependencyDividerRow.jsx` — componente único do divisor visual em tabelas.
- `index.js` — API pública. Outros componentes importam APENAS daqui.
- `GradesTable.jsx` e `LancamentoTab.jsx` refatorados para consumir o feature exclusivamente; JSX inline duplicado removido.

#### P1b — Enums centralizados backend `/app/backend/utils/dependency_enums.py`
- `DEPENDENCY_STATUS_VALUES = ("active", "completed", "failed", "cancelled")`
- `DEPENDENCY_TYPE_VALUES = ("none", "with_dependency", "dependency_only")`
- `Literal` types `DependencyStatus` e `DependencyType` (compatíveis com Pydantic).
- `normalize_dependency_status()` / `normalize_dependency_type()` aceitam aliases (case-insensitive, `with-dependency`, `withDependency`, `Com_Dependencia`, `ATIVO`, `Concluído`, etc.) → retornam canônico ou `ValueError` ruidoso.
- `validate_*` exigem valor não-vazio.
- `is_active_status()` helper defensivo.

#### P2 — Métricas pedagógicas no canal `diary`
- `record_diary_load()` agora aceita `school_stage` e gera contadores
  `dependency_by_course__<id>` e `dependency_by_stage__<x>`.
- `diary_loader` resolve `school_stage` via 1 query opcional (cache leve da turma).
- `GET /api/admin/observability/diary` separa explicitamente:
  - `snap.technical` — DevOps/SRE (latency, queries, cache_hit, payload size).
  - `snap.pedagogical` — `regular_total`, `dependency_total`, `dependency_ratio_pct`,
    `dependency_by_course`, `dependency_by_school_stage`, `excess_dep_loads`,
    `avg_dependency_ratio_pct`.
- Reservados (não implementados): `dependency_approval_rate`, `dependency_dropout_rate` — Fase 4.

#### Contrato `/app/docs/HISTORICO_ESCOLAR_CONTRACT.md` **CONGELADO V1**
13 seções normativas cobrindo: princípio de "vida acadêmica REAL",
versionamento (`document_version` + `history_schema_version`), regras imutáveis
(nunca sobrescrever reprovação, cronologia real, carga horária preservada,
matriz curricular versionada, snapshots `*_at_issue`), shape canônico v1,
formato textual obrigatório por linha, regras técnicas de PDF (renderer único,
pipeline canonical→html→pdf, QR de verificação, metadados embutidos),
reemissão fiel de históricos antigos, 10 cenários de teste obrigatórios,
roteiro de implementação Fase 4.

#### Atualização do contrato do Diário
`/app/docs/DIARY_API_CONTRACT.md` ganhou §27 (Dependência não contamina cálculo regular),
§28 (Métricas pedagógicas), §29 (Enums centralizados), §30 (Centralização frontend).

#### Tests
- 111/111 pytests verdes (incluindo 40 do P0 + 19 da Fase 2 + 11 pre-fase + 26 dependencies + 9 observability + 6 autocomplete).
- Iteration 72 (testing_agent_v3_fork): 98/98 pytests + 4/5 E2E HTTP verdes (1 endpoint `/analytics/general` inexistente, substituído por endpoints válidos `/overview`, `/by-subject`, etc., todos 200). Frontend `/admin/grades` e `/admin/attendance` carregam sem erros bloqueantes. Imports do feature confirmados.
- Issue minor (excess_dep_loads em `pedagogical`) corrigido pós-iteration 72.
- Baseline comparison: zero regressão (queries=3, payload=3678 bytes, ratio 1.00x).



### Dependência de Estudos — Fase 2 (Diário Escolar) **[Fev/2026]**

**Contrato CONGELADO em `/app/docs/DIARY_API_CONTRACT.md` v1** (atualizado com 5 novas seções:
divisor fora do array, baseline comparison, anti-spoof, filtro auto de inativas, dep_ratio).

- **Endpoint canônico**: `GET /api/diary/class/{class_id}/course/{course_id}?academic_year=YYYY` retorna
  `{contract_version:1, items:[...], meta:{regular_count, dependency_count, has_dependencies,
  dependency_ratio_pct, total, load_duration_ms}, warnings?:[...]}`. Sem item `is_divider` fake no
  array — o divisor é decisão do frontend a partir de `meta.has_dependencies` + flag `is_dependency`
  no primeiro item da seção.
- **Loader central** `/app/backend/utils/diary_loader.py`:
  - **Anti-N+1**: 3 queries Mongo (enrollments + student_dependencies + students). Validado em pytest.
  - Ordenação `db.students.find().collation({locale:'pt', strength:1})` server-side + chave de fallback
    em Python equivalente a `localeCompare('pt-BR')`.
  - Anti-duplicidade: aluno com enrollment ativo NÃO aparece como dep, mesmo com `student_dependencies`
    ativo no mesmo (turma, componente).
  - Fonte da verdade: `student_dependencies.status='active'`. Backend NUNCA usa `student.dependency_mode`.
  - `record_diary_load(...)` instrumenta cada carga com `dependency_ratio_pct`, `excess_dep`,
    `regular_total`, `dependency_total`, latency.
  - Warnings emitidos no payload: `EXCESS_DEPENDENCY_LOAD` (>30 deps) e `DEP_GREATER_THAN_REGULAR`.
- **Anti-spoof** `/app/backend/utils/dependency_validator.py`: toda escrita de `attendance` ou `grade`
  com `dependency_id` passa por `validate_dependency_link()` que valida 5 invariantes
  (existence, status=active, student match, class match, course match, tenant match) → 422 com
  `detail.code` em `DEPENDENCY_COHERENCE_{NOT_FOUND,INACTIVE,STUDENT_MISMATCH,CLASS_MISMATCH,
  COURSE_MISMATCH,TENANT_MISMATCH}`. Plugado em `POST /api/grades`, `POST /api/grades/batch`,
  `POST /api/attendance`.
- **Modelos atualizados**: `GradeBase` e `AttendanceRecord` ganharam `dependency_id: Optional[str] = None`.
  Persistido em `db.grades` e `db.attendance.records[]`.
- **Endpoints existentes integrados**: `GET /api/grades/by-class/{cid}/{coid}` e
  `GET /api/attendance/by-class/{cid}/{date}` agora injetam alunos em dep ATIVA ao final, marcados
  com `student.is_dependency=true`, `student.dependency_id`, `student.dependency_type`,
  `student.origin_academic_year`, `student.display_label='Dependência'`. UI existente preservada.
- **Frontend** (badge âmbar + divisor visual, sem decisão pedagógica):
  - `GradesTable.jsx` e `LancamentoTab.jsx` renderizam `<tr data-testid="dependency-divider-row">`
    antes do primeiro item com `is_dependency=true` e `<span data-testid="dependency-badge-{id}">
    Dependência</span>` ao lado do nome do aluno.
  - `Grades.js` e `Attendance.js` enviam `dependency_id` no save quando aluno é dep.
- **Baseline anti-regressão** `/app/backend/scripts/compare_diary_baseline.py`:
  - `--record` grava `/app/baselines/diary_baseline.json` com payload size, p95/p99 latency, queries.
  - `--compare` compara contra baseline com threshold (default 1.5x). Exit 1 em regressão crítica.
  - Baseline atual: 3 queries, 3678 bytes, p95=2.18ms, 10 items.
- **Snapshot observability** (`GET /api/admin/observability/diary`): super_admin only, agora inclui
  `avg_dependency_ratio_pct` e `excess_dep_loads` derivados dos buckets.
- **Telemetria**: canal `diary` com `record_diary_load` registra cada carga (regular, dep, ratio,
  latency, warnings) em sliding window de 15min.
- **Fixture E2E** `fixture_dependency_diary_v1` (idempotente):
  10 alunos / 4 deps ativas / 1 cancelada / 1 concluída / 2 componentes (Mat + PT).
- **Tests**:
  - `/app/backend/tests/test_diary_phase2.py` — 19 cenários (14 do contrato + 5 de anti-spoof + meta
    + ordering + anti-N+1 + warnings + label imutável). 100% verde.
  - Suite consolidada: 71/71 pytests passando (Fase 1 + Pré-Fase 2 + Fase 2 + observability +
    autocomplete + dependencies).
  - Iteration 71 (testing_agent_v3_fork): backend + frontend E2E HTTP no preview URL — 9/9 verdes,
    zero issues.
- **NÃO tocado nesta fase** (cf. exigência §10 do owner): fechamento anual, recuperação, conselho de
  classe, histórico escolar, boletim final/PDF — preservados para Fases 3 e 4.



### Arquitetura de Busca (Autocomplete server-side) **[Fev/2026]**

**Diretriz arquitetural OBRIGATÓRIA — ver `/app/docs/SEARCH_ARCHITECTURE.md`**

- **Princípio**: frontend NUNCA carrega lista completa para filtrar local.
- **Endpoint canônico**: `GET /api/students/autocomplete?q=...&limit=10[&school_id&class_id&status]`
  - Prefix-first sobre índice composto `(mantenedora_id, nome_busca)`.
  - Fallback contains restrito: somente quando `len(q) >= 4` E prefix retornou < 3 hits.
  - **Cache server-side TTL 5s** (tenant-aware, key=`tenant|q_norm|filters_hash`, instrumentado para `cache_hit_pct`).
  - CPF mascarado (`***.456.***-01`) — nunca CPF cru.
  - Rate limit 30 req/min/usuário.
- **Hook canônico frontend**: `useStudentSearch(query, options)` — debounce 300ms, AbortController, cache tenant-aware TTL 30s, mínimo 2 chars.
- **Observabilidade arquitetural**: `GET /api/admin/observability/autocomplete`
  - Super_admin only; audit log; no-cache headers; rate limit dedicado (5/min).
  - Janela deslizante 15min em buckets de 1min; sem PII (queries via SHA1 truncado da q normalizada).
  - p95 incremental via histogram buckets (sem sort on-demand).
  - Métricas: requests_total, avg/p95 latency, fallback_pct, cache_hit_pct, empty_pct, query_length_distribution, top_queries (anonimizadas), top_tenants, rate_limited_requests, cache_memory_estimate_kb.
  - **Modo instance-local**: payload sinaliza `replica_aware: false` (Fase 2 = Redis ou Mongo capped).
- **Migração inicial**: `AssocialDashboard` (caso piloto). Pendente: BolsaFamilia, VaccineDashboard, Grades, Enrollments, StudentsComplete, Promotion, AnalyticsDashboard, Students, Guardians.
- **Roadmap evolutivo**: Fase 2 = tokens (`nome_busca_tokens`) quando `fallback_pct > 30%` na telemetria. Fase 3 = Atlas/ElasticSearch só se necessário.
- Tests: `/app/backend/tests/test_students_autocomplete.py` (18 casos).

### Hardening + Refactor de Arquitetura **[06/Fev/2026]**

**1. CORS Hardening (segurança)**:
- Removido fallback `'*'` (incompatível com `allow_credentials=True`).
- Whitelist explícita via `CORS_ORIGINS` (lista por vírgula). Aviso forte se não configurado.
- **[Fev/2026 — fix produção]** Adicionado suporte a `CORS_ORIGIN_REGEX` para múltiplos subdomínios
  (ex.: `https://.*\.aprenderdigital\.top`). Necessário em prod (Coolify) com domínios não previstos
  inicialmente. Validado contra ataques (`evil.aprenderdigital.top.attacker.com`, `http://`).
- Métodos e headers explícitos (`Authorization`, `Content-Type`, `X-CSRF-Token`).
- Validado: origem permitida → 200 OK; origem maliciosa → 400 Bad Request.

**2. Documentação**:
- `/app/README.md`: arquitetura, env vars, setup, scripts CLI, convenções, testes.
- `/app/backend/README.md`: estrutura, endpoints principais, regras críticas, performance, segurança.

**3. Refactor `server.py` (857 → 619 linhas, -28%)**:
- Pacote `/app/backend/startup/`:
  - `indexes.py` — todos os `create_index` (130 linhas extraídas).
  - `multi_tenant.py` — bootstrap inicial + self-heal idempotente.
  - `seeds.py` — AEE templates, BNCC Computação, init de serviços externos.
- Comportamento e ordem de execução **preservados exatamente**.

**4. Auditoria de dependências**:
- Script `/app/backend/scripts/audit_dependencies.py` lista os 27 imports diretos
  de terceiros (vs 153 no requirements.txt). Os ~120 restantes são transitivos.
- Mantido `requirements.txt` intacto para evitar quebras (recomendação: refazer
  em venv limpo numa janela de manutenção).

**5. models.py (2924 linhas)** — modularização adiada (alto risco):
  - 175 classes em 37 arquivos importando com `from models import *`.
  - Backlog: criar pacote `models/` com submódulos por domínio + `__init__.py`
    que reexporta tudo (compat). Refactor para janela dedicada.

### Carga Horária Derivada — Fonte Única de Verdade **[05/Fev/2026]**

- **Refatoração arquitetural**: CH do servidor deixa de ser informada manualmente e passa a
  ser **derivada** de `Σ alocações + Σ substituições vigentes`. Fallback de 40h dividido pelas
  lotações ativas quando não há nenhum registro.
- **Calculator central** (`/app/backend/utils/carga_horaria_calculator.py`):
  - `calcular_carga_horaria_servidor(db, staff_id, *, modo)` — total geral.
  - `calcular_carga_por_lotacao(db, staff_id, school_id, *, modo)` — por escola.
  - `calcular_carga_horaria_servidor_breakdown(...)` — detalhamento para UI.
  - Modo contextual: `'atual'` (substituições vigentes hoje) e `'periodo'` (intervalo/ano letivo).
- **Endpoints atualizados**:
  - `GET /api/staff` enriquece cada item com `carga_horaria_calculada`.
  - `GET /api/staff/{id}` retorna `carga_horaria_calculada` no servidor + `carga_horaria_calculada` em cada lotação ativa.
  - `GET /api/staff/{id}/carga-horaria` (novo) retorna breakdown completo (por escola, fallback, qtd alocações).
- **Folha de pagamento** (`hr.py`): geração de pré-folha agora usa `calcular_carga_por_lotacao(modo='atual')`
  como fonte única (substitui `school_assignments.carga_horaria` manual + fallback legado).
- **Frontend** (3 telas):
  - `StaffModal`: campo "Carga Horária Total Calculada" (readonly, vindo de `carga_horaria_calculada`)
    substitui o texto antigo "definida em Gerenciar Lotações".
  - `LotacaoModal`: campo "CH Semanal" agora é readonly (`auto`) com tooltip explicativo;
    cards de lotações existentes exibem `Xh/sem (calc.)`.
  - `AlocacaoModal`: removido alerta bloqueante "Não é possível salvar"; resumo simplificado
    (Já Alocada + Nova Alocação + Total após salvar) com mensagem informativa "Sem limites manuais".
- **Auditoria + Testes**:
  - Script `/app/backend/scripts/audit_carga_horaria.py` compara manual vs calculado em todos os
    servidores ativos. Gera relatório JSON. Validado em preview: 0 divergências.
  - Suite pytest `/app/backend/tests/test_carga_horaria_calculator.py` com 11 casos cobrindo
    fallback 40h, divisão entre lotações, ignore_workload, substituições vigentes/expiradas.


### Substituição Multi-Turma/Multi-Componente **[05/Fev/2026]**
- Refatorado `SubstituicaoSection.js` para paridade completa com `AlocacaoModal` de "Nova Alocação":
  suporte a **N turmas × M componentes** (cartesian product) em uma única operação.
- UX: botões `+`/`−` com chips 🎓 (amarelo) para turmas e 📖 (roxo) para componentes; opção
  "TODOS (N componentes)" para adicionar em lote; preview da lista de combinações com regente
  detectado e CH por linha.
- Filtros defensivos: Escola usa `professorSchools` (apenas lotações ativas); componentes
  filtrados por nível de ensino comum das turmas; dedupe de componentes já alocados ao substituto
  em qualquer turma selecionada; reset automático ao mudar nível de ensino.
- CH semanal auto-detectada por combinação via regente existente; campo override manual
  (`auto (regente)`) aplica-se a todas as combinações.
- Save loop: `POST /teacher-assignments/substitutions` uma vez por combinação, com contagem
  de sucesso/falha (`4 cadastrada(s), 0 falharam`).
- Todos os `data-testid` adicionados: `subst-add-turma-btn`, `subst-add-comp-btn`,
  `subst-turma-chip-{id}`, `subst-comp-chip-{id}`, `subst-preview-list`.


### Busca Sugestiva + Accent-Insensitive em Toda a UI **[04/Mai/2026]**
- Novo helper `frontend/src/utils/textSearch.js` com `normalizeForSearch()` (NFD + lowercase + remove cedilha) e `highlightSegments()` (realça trecho casado).
- **Declarações Escolares** (`/admin/declaracoes`): substituiu lista pré-carregada com filtro local por **autocomplete sugestivo via backend** a partir do **3º caractere**, debounced 250ms, accent + case insensitive (usa `nome_busca`). Highlight do trecho casado, navegação por teclado (↑ ↓ Enter Esc), botão limpar (X), spinner durante busca, mensagem "Continue digitando" quando < 3 chars.
- **Filtros locais aplicados ao normalizeForSearch** (paralelo): `Events.js`, `Staff.js` (lotacoes/alocacoes), `Announcements.js`, `MessageLogs.js`, `VaccineDashboard.js`, `AssocialDashboard.js`, `PreMatriculaManagement.jsx`. Agora `joao` acha `João`, `concei` acha `Conceição`.
- Validado E2E: `joa` → `JOAO SANTOS` com highlight ✅, `concei` → 1 sugestão ✅, hint < 3 chars visível ✅.


**Sintoma**: PDFs de Matrícula/Frequência/Escolaridade já tinham código + QR, mas Histórico Escolar e Certificado de Conclusão eram emitidos SEM código nem QR — não podiam ser validados pelo portal público.

**Origem**: as rotas `GET /api/documents/historico-escolar/{id}` e `GET /api/documents/certificado/{id}` chamavam diretamente `generate_*_pdf` sem criar `snapshot` antes. Os geradores em `pdf/historico_escolar.py` e `pdf/certificado.py` também não tinham slot para receber `verification_code`.

**Fix**:
- Novo helper `pdf/verification_footer.py` com `build_verification_flowables()` (Platypus) e `draw_verification_footer_on_canvas()` (canvas direto). Usa `segno` (já no requirements) e produz a mesma caixa visual usada nas declarações: código + QR + URL portal + validade.
- `pdf/historico_escolar.py`: aceita kwargs `verification_code` e `valid_until`; injeta o rodapé de verificação no final do story.
- `pdf/certificado.py`: aceita kwargs `verification_code` e `valid_until`; desenha o rodapé via canvas no rodapé inferior (paisagem A4). Também tornou os `.upper()` resilientes a `None` (era falha "'NoneType' object has no attribute 'upper'" em alunos sem todos os campos).
- `routers/documents.py`: ambas as rotas agora chamam `snapshot_service.create_snapshot()` ANTES de gerar o PDF, com `analysis_type="historico"` ou `"certificado"`, validade default 10 anos. O `verification_code` retornado é injetado no PDF e persistido no `verifiable_documents` com `expires_at` correto.

**Validação E2E**:
- `GET /api/documents/historico-escolar/{id}` → PDF 13 KB com `SIGESC-9PWX-6KZ3` extraível via pypdf ✅
- `GET /api/documents/certificado/{id}?academic_year=2025` → PDF 127 KB com `SIGESC-XEPG-3AW3` extraível ✅
- `GET /api/public/verify/SIGESC-XEPG-3AW3` → `status=valido tipo=certificado emitido_em=2026-05-05` ✅
- Catálogo da página `/admin/document-validator` agora reflete corretamente todos os 9 tipos sendo emitidos com código + QR.


- Nova rota autenticada: `/admin/document-validator` (`pages/DocumentValidator.jsx`)
- Botão no Menu de Administração → Gestão Institucional → "Validar Documentos" (visível para super_admin, admin, secretario, diretor, coordenador, auxiliar_secretaria)
- **Catálogo dos 9 tipos de documentos verificáveis** do SIGESC (mantido em sync com `backend/services/verifiable_docs_service.DOC_TYPES`):
  1. Plano de Ação Automático (`plano_acao`) → /admin/plano-acao
  2. Relatório Executivo Mensal (`relatorio_mensal`) → /admin/relatorios-mensais
  3. Declaração de Matrícula (`matricula`) → /admin/students
  4. Declaração de Frequência (`frequencia`) → /admin/students
  5. Declaração de Escolaridade (`escolaridade`) → /admin/students
  6. Histórico Escolar (`historico`) → /admin/promotion
  7. Certificado de Conclusão (`certificado`) → /admin/promotion
  8. Ata / Documento Administrativo (`ata`)
  9. Documento Institucional genérico (`generico`)
- Cada card mostra ícone, descrição, módulo emissor e link "Ir →"
- **Validador embutido**: campo `SIGESC-XXXX-XXXX` que consulta `/api/public/verify/{code}` e exibe status (válido/inválido/revogado) com metadados LGPD-safe (tipo, emitido em, emitido por, escopo, hash truncado)
- **Atalho para o portal público externo** (URL copiável + abrir em nova aba) para compartilhar com vereadores/conselheiros/cidadãos
- Seção "Como funciona" explicando snapshot imutável + SHA-256 + HMAC + QR + revogação


- Helpers em `backend/text_utils.py`: `strip_accents`, `normalize_for_search` (lowercase + sem acentos), `normalize_for_sort` (lowercase preservando acentos), `compute_name_indexes(doc, primary_field)`.
- **Routers atualizados** (`students`, `staff`):
  - **Create/Update** preenchem automaticamente `nome_normalizado` e `nome_busca` a partir de `full_name` (students) / `nome` (staff).
  - **GET com `?search=`** usa `$or`: caminho rápido via `nome_busca` indexado + fallback regex `accent_insensitive_regex` no campo original (cobre registros não migrados).
- **Endpoint `/api/staff` ganhou param `search`** (não existia antes).
- **Validado**: criar `Maria José da Conceição` → `nome_busca = "maria jose da conceicao"` → busca por `maria`, `JOSÉ`, `conceicao` retorna o mesmo registro. Idem para students.

### Bug Fix Crítico — Remoção do CAPS Automático **[04/Mai/2026]**
**Sintoma**: nomes próprios e textos longos foram salvos em CAIXA ALTA + sem acentuação correta no banco, corrompendo dados pedagógicos (planos, observações, conteúdos).

**Origens removidas (3 fontes simultâneas)**:
1. **CSS global** em `frontend/src/index.css` — `text-transform: uppercase` em todo `<input>` e `<textarea>` REMOVIDO. Mantida apenas a classe utilitária opt-in `.input-uppercase` para casos legítimos (códigos BNCC, UF).
2. **`SpellCheckTextarea.jsx`** — `textTransform: uppercase` default REMOVIDO. Agora aceita `data-uppercase` como opt-in (era `data-no-uppercase` como opt-out).
3. **Backend** `format_data_uppercase()` removido de **TODOS** os routers de escrita: `students, staff, schools, classes, courses, learning_objects, users, guardians, auth` E `aee` (autorizado pelo proprietário). Imports remanescentes do `text_utils.py` foram limpos. Função fica disponível em `text_utils.py` mas sem callers — **não usar em código novo**.

**Política nova (arquitetura limpa)**:
- **Banco** armazena dado conforme digitado pelo usuário (capitalização correta, com acentos).
- **PDFs** continuam aplicando `.toUpperCase()` apenas na **renderização** (norma documental institucional brasileira).
- **Comparações case-insensitive** preservadas (legítimas, não persistem).

**Migração reversa de dados existentes**:
- Script `/app/backend/scripts/normalize_names_back.py` com:
  - Backup automático (`backup_<col>_<timestamp>` via `$out`) antes de cada execução com `--apply`
  - Função `title_case_name()` com regras BR: preposições minúsculas (`da, de, do, das, dos, e, em`), siglas conhecidas em UPPER (`AEE, BNCC, EJA, SEMED, ETI, …`), algarismos romanos (`I, II, III…`), hífens, apóstrofos
  - Adiciona `nome_normalizado` (lowercase preservando acentos) + `nome_busca` (lowercase + sem acentos NFD) + `nome_migrado: true` + timestamp
  - Cria índice composto `{mantenedora_id: 1, nome_busca: 1}` para busca eficiente e tenant-safe
  - `bulkWrite` em batches de 1000 (performance)
  - **Default `--dry-run`**, escreve só com `--apply`
  - Coleções: `students, staff, schools, classes, courses, users, mantenedoras` (apenas campos NOMINAIS — não toca em descrições, observações, planos AEE)
  - **AEE NÃO é migrado em massa** — dados antigos do AEE permanecem como estão (acordo arquitetural)

**Comando para o proprietário aplicar em produção**:
```bash
# 1. Sempre: dry-run primeiro
python /app/backend/scripts/normalize_names_back.py --dry-run

# 2. Após revisar o relatório, aplicar:
python /app/backend/scripts/normalize_names_back.py --apply

# 3. Restringir a uma coleção (se preciso):
python /app/backend/scripts/normalize_names_back.py --apply --collection students
```

**Validação**:
- Backend curl: POST `/api/classes` com `"Turma Teste de CapitalizaçÃO"` persiste exatamente como enviado ✅
- Frontend smoke: `getComputedStyle(input).textTransform = 'none'`, input aceita "Teste minúsculo Acentuação" e exibe como digitado ✅
- Dry-run no preview: 58 docs marcados para atualizar (students, schools, classes, courses, users, mantenedoras), 3 sem mudança — siglas (AEE, SEMED), preposições (da/de) e romanos (I, II) preservados corretamente ✅

**Migração aplicada no ambiente preview [05/Mai/2026]** — em 3 fases supervisionadas:
- Fase 1 (`courses` + `users`): 36 docs migrados, backups `backup_*_20260505T105357Z`
- Fase 2 (`students` + `staff`): 10 docs migrados, backups `backup_*_20260505T105647Z`
- Fase 3 (`schools` + `classes` + `mantenedoras`): 14 docs migrados, backups `backup_*_20260505T105804Z`
- **Total**: 60 docs migrados em 7 coleções; dry-run final confirma 0 pendentes
- Validação end-to-end: login + busca `search=maria` retornou `Maria Silva` (busca accent-insensitive funcionando) ✅
- **Próximo passo pendente**: rodar o mesmo script em produção (Coolify) quando o proprietário decidir

**Ferramentas operacionais** [05/Mai/2026]:
- `/app/Makefile` — atalhos: `make migrate-dry-run | migrate-names | migrate-names-yes | migrate-status | migrate-rollback TS=<timestamp>`
- `/app/backend/scripts/run_migration.sh` — runner shell com dual-gate (dry-run obrigatório antes de --apply), prompts Y/n por fase, healthcheck pós-migração, logging em `/var/log/sigesc/migracao_nomes_<TS>.log` e rollback global por timestamp
- Em produção (Coolify): após "Save to Github" + deploy, basta entrar no terminal do container backend e rodar `make migrate-names` (ou `make migrate-names-yes` para CI)

### Normalização de Conteúdo Textual — Fila de Revisão [05/Mai/2026]
**Princípio**: nome ≠ texto. Conteúdo (observações, descrições, pareceres) usa
SENTENCE CASE (não Title Case) e exige revisão humana antes de gravar — o
script gera sugestões e enfileira; admin aprova caso a caso.

**Fluxo**:
1. `make content-dry-run` → relatório read-only
2. `make content-scan` → enfileira sugestões em `content_review_queue` (NÃO grava)
3. Admin revisa em `/admin/content-review` (Aprovar / Rejeitar / Editar / Lote)

**Whitelist atual** (campo a campo):
- `students.observations`
- `student_history.observations`
- `enrollments.observations`
- `staff.observacoes`
- `learning_objects.content` (Conteúdo/Objeto de Conhecimento)
- `learning_objects.pratica_pedagogica` (Práticas Pedagógicas)
- `learning_objects.observations`
- (futuros: `classes.descricao/observacoes` quando schema for ampliado)
- (FASE 2 futuro com filtro restritivo): `learning_objects.methodology`, `learning_objects.evidencia_aprendizagem`
- ❌ NÃO incluído: `learning_objects.resources` (lista de materiais — risco semântico)

**Heurísticas defensivas** (FUNÇÃO `should_skip_text`) — Mai/2026 (refinadas v2):
- 🚫 Algarismos romanos I/II/III/IV/V/VI/.../XX (cobre "MATERNAL I", "PRÉ I", "AULA V")
- 🚫 Lista por vírgula em CAPS — bloqueia APENAS se média de palavras por segmento ≤ 1.5 (lista de materiais como "CADERNO, LÁPIS, BORRACHA")
- ✅ Frases pedagógicas com vírgulas estruturais convertem normalmente ("INTERPRETAÇÃO DE TEXTO, LEITURA E ESCRITA, PRODUÇÃO DE TEXTO" → "Interpretação de texto, leitura e escrita, produção de texto")
- 🚫 Estrutura pedagógica enumerada: ATIVIDADE/AULA/ETAPA/OBJETIVO/UNIDADE/MÓDULO/CAPÍTULO/SEÇÃO + número
- ✅ Casos validados: 11/11 testes passam (CADERNO/LÁPIS bloqueia ✅, INTERPRETAÇÃO DE TEXTO converte ✅)

### Blindagem na entrada (POST/PUT) — Mai/2026
**Princípio**: prevenir ruído contínuo na fila. Antes de gravar, se um campo
whitelistado vier em CAPS narrativo → converter para sentence case usando as
mesmas regras (mesma whitelist + mesmas heurísticas defensivas).

**Util**: `/app/backend/utils/text_normalize.py`
- `normalize_input_text(value)` — single field
- `normalize_input_fields(payload, collection)` — payload completo

**Routers instrumentados** (POST + PUT):
- `students.py` — campo `observations`
- `staff.py` — campo `observacoes`
- `enrollments.py` — campo `observations`
- `student_history.py` — campo `observations`
- `learning_objects.py` — campos `content`, `pratica_pedagogica`, `observations`

**Validação E2E**:
- PUT `/api/students/{id}` enviando `"ALUNO APRESENTA BOM DESEMPENHO EM 14:30. NECESSITA DE ATENDIMENTO AEE."` → gravado como `"Aluno apresenta bom desempenho em 14:30. Necessita de atendimento AEE."` ✅
- Texto com heurística (lista, romano, estrutura) preserva original ✅
- Coleções fora da whitelist intactas ✅

### Botão "Ver contexto" — Mai/2026
- Endpoint: `GET /api/admin/content-review/{id}/context`
- Frontend: modal que mostra todos os campos textuais do registro original, destacando o campo da sugestão pendente em amarelo
- Validação: modal abre, mostra 3 campos textuais (content, pratica_pedagogica, observations), campo destacado tem pin "📍 campo da sugestão" + sugestão embebida ✅

### Higienização Textual — Fase 1 (FORMATAÇÃO determinística) [05/Mai/2026]
**Princípio**: módulo SEPARADO de `content_review` ("nome ≠ caixa ≠ formatação"). Apenas regras
determinísticas, ZERO ortografia, ZERO IA, sempre via fila com revisão humana.

**Regras (Fase 1)**:
1. Espaços múltiplos → 1
2. Espaço antes de pontuação → remove
3. Falta espaço após pontuação (antes de letra) → adiciona (preserva 1.500/14:30)
4. Múltiplas quebras de linha (3+) → 2
5. Capitalização inicial
6. Pontuação final em frases ≥3 palavras
7. Padronização de siglas (aee → AEE etc)
8. Palavras stopword duplicadas (de de → de)

**Pulagem defensiva**: texto vazio/curto, em CAIXA ALTA (vai pro content_review), com romanos
ou estrutura enumerada (preserva).

**Arquivos**:
- Script: `/app/backend/scripts/text_improvement.py` (--dry-run, --scan, --clear-pending)
- Router: `/app/backend/routers/text_improvement.py` (super_admin/admin/admin_teste)
- Página: `/app/frontend/src/pages/TextImprovement.jsx` (rota `/admin/text-improvement`)
- Coleção MongoDB: `text_improvement_queue` (status + applied_rules)
- Make: `make text-dry-run | text-scan | text-clear-pending`
- Dashboard: novo atalho "Higienização Textual" (violeta) no grupo Administração

**Validação E2E [05/Mai/2026]**:
### Higienização Textual — Fase 2 (ORTOGRAFIA via pyspellchecker) [05/Mai/2026]
**Princípio**: ortografia 100% determinística (lib `pyspellchecker` + dict PT-BR de 414k palavras),
ZERO IA, sempre via fila com confidence ≥0.75. Mesma fila/UI da Fase 1, distinguidas pelo campo `tipo`.

**Pipeline ampliado**: cada doc/campo pode gerar 0..2 sugestões (uma de formatação + uma de ortografia).

**Detector** (`scripts/text_improvement.py::detect_spelling_issues`):
- Tokeniza palavras alfabéticas
- Pula: <4 chars, siglas (PRESERVED_ACRONYMS), tokens UPPER, nomes próprios (capitalizada no meio da frase), palavras com dígito, palavras já no dicionário
- Sugestão = `spell.correction(palavra)` com `confidence = 1 - levenshtein(orig, sug)/len(orig)`
- Aplica todas as correções com confidence ≥ 0.75
- Preserva caixa do original

**Vocabulário extra** (termos pedagógicos comuns):
- siglas educacionais (BNCC, AEE, SEMED, EJA, PCD, TEA, TDAH, FUNDEB, PNAE, LGPD…)
- termos comuns: remanejado, rematriculado, multisseriada, alfabetizado, autoavaliação, psicomotor…
- nomes/locais: araguaia, floresta, tocantins…

**UI estendida** (`pages/TextImprovement.jsx`):
- Badge laranja "✏️ Ortografia" + confiança em %
- Diff visual das correções: `palavra ❌ → sugestão ✅ (XX%)`
- Filtro por tipo (Todos / Formatação / Ortografia)
- Texto com correções aplicadas mostrado no painel "Sugestão"

**Validação E2E**: 6 typos genuínos detectados com confidence 78-92% (Necessitra→Necessita, atendimnto→atendimento, profesora→professora, interpretaçao→interpretação, discussao→discussão, Avaliacao→Avaliação). Falsos positivos (Remanejado→Remunerado) eliminados após adicionar termos ao vocabulário extra ✅


**Regras de preservação** (script `normalize_content.py`):
- Siglas (AEE, BNCC, SEMED, TEA, ETI, B1-B4, CNPJ, CPF, RG, NIS, PCD, LGPD, etc.)
- Citações entre aspas simples ou duplas
- Datas (`dd/mm/aaaa`), horas (`hh:mm`), percentuais (`85%`), números
- Sentence case: 1ª letra após `.` `!` `?` ou início → maiúscula; restante minúsculo

**🛑 NUNCA toca em**: BNCC, learning_objects, módulo AEE (bloqueado), planos/objetivos AEE, conteúdos programáticos.

**Arquivos**:
- Script: `/app/backend/scripts/normalize_content.py`
- Router: `/app/backend/routers/content_review.py` (super_admin/admin/admin_teste)
- Página: `/app/frontend/src/pages/ContentReview.jsx` (rota `/admin/content-review`)
- Coleção MongoDB: `content_review_queue` (status: pending/approved/rejected/edited)
- Endpoints: `GET /api/admin/content-review`, `/stats`, `POST /:id/approve`, `/:id/reject`, `/:id/edit-and-approve`, `/bulk-approve`
- Dashboard: novo atalho "Revisão de Conteúdo" no grupo Administração

**Validação end-to-end [05/Mai/2026]**:
- 5 docs de teste enfileirados em `students.observations`
- ✅ APPROVE: doc original atualizado com `content_migrated: true`
- ✅ REJECT: status `rejected`, doc intocado
- ✅ EDIT-AND-APPROVE: admin refinou texto antes; doc gravou texto editado
- ✅ Frontend renderiza cards lado a lado, badges, filtros, bulk-select
- ✅ Siglas preservadas (`AEE`, `B1`, `BNCC`, `TEA`, `SEMED`, `ETI`)
- ✅ Datas/horas/percentuais preservados (`14:30`, `85%`, `15/03/2026`)
- ✅ Citações preservadas intactas

### Bug Fix — "Erro ao salvar plano AEE" (CSRF) **[04/Mai/2026]**
- **Root cause**: `pages/DiarioAEE.js` usa raw `fetch` (não axios) e o objeto `headers` só carregava Authorization+Content-Type. A `CSRFMiddleware` (server.py:788) rejeitava todo POST/PUT/DELETE em /api/aee/* com 403 "CSRF token inválido ou ausente". Resultado: nenhum plano/atendimento/modelo AEE conseguia ser salvo, editado, excluído ou duplicado pelo frontend.
- **Fix**: helper `readCsrfToken()` lê o token de `sessionStorage('sigesc_csrf_token')` (setado pelo response do `/auth/login`) com fallback para cookie `sigesc_csrf`, injetando-o como header `X-CSRF-Token` em todas as escritas do Diário AEE.
- **Tests**: `/app/backend/tests/test_aee_csrf_fix.py` (5 cenários: 403 sem CSRF, 201 com CSRF, e2e create+get+delete).
- **Status**: 100% backend + 100% frontend (validado pelo testing agent — iteration_70).

### Sprint G4.1 — Upload Direto de Logotipo **[04/Mai/2026]**
- Drag & drop + click-to-select de imagens (PNG, JPG, SVG, WebP) no `BrandingPanel.jsx`
- Validação client-side: tipo `image/*`, máx 2MB
- Backend: reutiliza `POST /api/upload?file_type=branding` (FTP externo + fallback local), aceita SVG agora (`.svg` adicionado em `ALLOWED_EXTENSIONS`)
- Após upload, URL pública é injetada em `form.logo_url` automaticamente e refletida tanto no slot do dropzone quanto no preview card em tempo real
- "ou colar URL manualmente" disponível como fallback (collapsible) para quem prefere link externo
- Botão X para remover logo selecionado antes de salvar

### Sprint G4 — Live Preview de Branding Multi-Tenant **[04/Mai/2026]**
**UX para super_admin configurar identidade visual de cada tenant em tempo real.**
- Backend: `routers/tenant_admin.py` — `PUT /api/tenant/branding` aceita {name, slogan, logo_url, primary_color, secondary_color}, valida hex `#RRGGBB`, super_admin pode passar `X-Mantenedora-Id` para editar tenant alvo (admin/gerente/secretario só editam o próprio tenant). Retorna o snapshot atualizado.
- Modelos novos: `BrandingUpdatePayload` + helper `_is_hex_color`.
- Frontend: `components/branding/BrandingPanel.jsx` + tabs em `pages/TenantAdmin.jsx`.
- **Live Preview real**: ao editar cores, aplica `--brand-primary` / `--brand-secondary` em `document.documentElement` em tempo real, refletindo no preview card (header gradient, botão, tags, tiles). Restaura CSS vars originais ao desmontar (proteção contra "saiu sem salvar").
- Após salvar, dispara `tenant-changed` para o `BrandingContext` recarregar e refletir mudança nos Layouts globalmente.
- Validação cliente: hex inválido → toast com erro; tenant não selecionado → toast.
- Tests: `/app/backend/tests/test_branding_g4.py` (8 cenários backend) + Playwright (5 fluxos E2E).
- Status testagem: 100% backend (8/8) + 100% frontend (5/5).

### Sprint G3 — Relatório Executivo Mensal **[03/Mai/2026]**
**Produto dentro do produto**: secretário/gestor recebe TODO MÊS um diagnóstico forensicamente auditável da rede que força DECISÃO (não descreve).
- Backend:
  - `services/monthly_report_service.py`: agregação mensal por mantenedora (escolas, alunos, frequência, cobertura curricular, alertas, aulas lançadas) + Claude Sonnet 4.5 com prompt forçando JSON estruturado (resumo executivo, ranking Top5/Bottom3, diagnóstico causal, 3 ações prioritárias com prazo e responsável, indicador de risco baixo/médio/alto, evidências numéricas)
  - `_stub_report()` fallback determinístico se IA indisponível — relatório SEMPRE pode ser gerado
  - Snapshot imutável (G1.5: hash SHA256 + HMAC) + Verifiable Document (G1.6: código `SIGESC-XXXX-XXXX`) com **validade de 30 dias** do link público
  - Idempotente por `(mantenedora_id, year, month)` via index unique → chamadas repetidas retornam o mesmo snapshot
  - `services/monthly_report_email.py`: gerador HTML/text de email-gatilho (não relatório passivo) com assunto que força ação: `[AÇÃO URGENTE] X escolas em risco alto — janeiro/2026`
  - `services/monthly_report_scheduler.py`: APScheduler dia 1º 06:00 UTC para cada mantenedora ativa, gera relatório do mês ANTERIOR e envia gatilho aos gestores (admin/gerente/secretario com email cadastrado)
  - Router `routers/monthly_reports.py`: POST `/generate`, GET listagem, GET `/{id}`, GET `/{id}/pdf?mode=executive|auditor` (reusa `snapshot_pdf`), POST `/{id}/send-email`
  - Index unique em `monthly_reports` por `(mantenedora_id, year, month)`
- Frontend: `pages/MonthlyReports.jsx` em `/admin/relatorios-mensais` (super_admin/admin/gerente/secretario)
  - Painel de geração (mês/ano com regerar via force=true)
  - Cards por mês com pílula de risco (alto/médio/baixo), KPIs principais, código SIGESC visível
  - Expansão inline mostra Resumo Executivo, Top5/Bottom3 com score 0-100, Diagnóstico Causal, 3 Ações Prioritárias com prazo e impacto
  - Botões: PDF Executivo · PDF Auditor · Enviar Email · Verificar publicamente
  - Modal de envio de email com lista de destinatários
- Email-gatilho: assunto adaptativo (`[AÇÃO URGENTE]` para risco alto, `[Atenção]` para médio, `[OK]` para baixo) + lista de bottom3 + 3 ações com prazo/responsável + código de verificação institucional
- Cron mensal idempotente: dia 1º 06:00 UTC para todos os tenants ativos
- Tests: `/app/backend/tests/test_monthly_reports.py` (18 cenários: validação período, sanitização IA, stub fallback, agregação, idempotência, validade 30 dias)

### Sprint G1.7 — Emissão de Declarações Escolares **[03/Mai/2026]**
- 3 tipos: Matrícula (90d), Frequência (30d), Escolaridade (180d)
- Backend: `services/school_docs_service.py` + `services/school_doc_templates.py`
  - PDF gerado via `reportlab` com cabeçalho oficial + QR Code dinâmico (`segno`)
  - Cada emissão gera código `SIGESC-XXXX-XXXX` (G1.6) e está em `verifiable_documents`
  - Status dinâmicos: válido / expirado (data) / revogado
  - Log de emissão em `school_documents_log` com `student_id`, tipo, finalidade, emitido_por, IP
- Router `routers/school_documents.py`: POST emit, GET list, POST revoke, GET PDF
- Frontend: `pages/SchoolDocuments.jsx` em `/admin/declaracoes`
- Tests: `/app/backend/tests/test_school_documents.py` (13 cenários)


### Fase 1 - Multi-Tenancy base
- `super_admin` desbloqueado em todas as rotas
- `mantenedora_id` injetado em todos os modelos
- CRUD de Mantenedoras com Wizard de Onboarding (CSV)

### Fase 2 - Isolamento e UX
- Row-Level Security em todas as collections (`students`, `classes`, `staff`, etc)
- `TenantSwitcher` + `TenantSyncBoundary` (remount sem reload)
- Remoção completa da coleção legacy `db.mantenedora`

### Permissions & UX polish
- Matriz de permissões: removida coluna ADMIN, SEMED renomeado (Tutor/Analista/Administração)
- Proteção do super_admin primário (sem botão de deleção)
- Admins podem enviar mensagens sem conexão mútua
- Modo Silencioso customizável (bipes de mensagens)
- Secretaria exibida no header
- **[22/Fev/2026]** TenantSwitcher reposicionado para a esquerda do header, agrupado visualmente com o bloco Mantenedora/Secretaria (melhor hierarquia visual)

### Boletim Virtual do Aluno  **[24/Fev/2026]**
- Nova rota `/aluno/boletim` (role=`aluno`) com redirect automático no login
- Backend: `GET /api/student/me/report-card` — identificação escola/aluno, notas b1..b4, recuperação por bimestre, recuperação final, média geral e situação
- Detecção automática de **turmas por CONCEITO** (Educação Infantil / 1º Ano / 2º Ano): exibe b1..b4 como **sigla real do conceito** (OD/DP/ND/NT para EI ou C/ED/ND para 1º-2º ano), com cor + tooltip descritivo + legenda. Sem recuperação, sem média numérica.
- Demais anos: 4 bimestres agrupados em 2 semestres (1º Sem: B1+B2, 2º Sem: B3+B4) com recuperação por bimestre + recuperação final
- Fund II (6º–9º) e EJA 3ª/4ª etapa → faltas por componente curricular
- Alertas: `> 25%` faltas → aviso vermelho; `≥ 95%` presença → parabéns verde
- Seed idempotente de conta de teste: `python backend/scripts/seed_test_student.py` (aluno@sigesc.com / aluno123)
- Testes: `/app/backend/tests/test_student_portal.py` (9 cenários, 100% pass)

### Ajustes finos **[24/Fev/2026]**
- Boletim online: conceitos exibidos como siglas reais (OD/DP/ND/NT e C/ED/ND) com legenda, cor e tooltip — não mais convertidos em nota numérica
- Cadastro/Editar/Visualizar Aluno → Info. Complementares → Deficiências / Transtornos: adicionada opção **"Transtorno do Desenvolvimento da Linguagem (TDL)"**
- PDF Detalhes da Turma: turmas com Tipo de Atendimento = **AEE** agora listam os alunos vinculados via `students.atendimento_programa_class_id`, `planos_aee` e `atendimentos_aee` (mesma lógica do endpoint JSON)

### Ação de Vínculo: Reclassificar **[24/Fev/2026]**
- Nova ação **"🎓 Reclassificar"** em Editar Aluno → Turma/Observações → Vínculo com Turma (entre Progredir e Cancelar)
- Semelhante à Progressão mas com motivo específico (avaliação de conhecimento, Art. 23 da LDB)
- Backend: `action_type='reclassificacao'`, `enrollment.status='reclassified'`, `action_hint='reclassificacao'` roteado em `/api/students/{id}` PUT
- Endpoint `POST /api/students/{id}/copy-data` aceita `copy_type='reclassificacao'` (copia só frequência, não as notas)
- **Bloqueio de diário** (turma origem e destino) funcionando para todas as 4 ações (Remanejado, Transferido, Progredido, Reclassificado):
  - Origem: bimestres cujo início é > `action_date` → `blocked_after_action`
  - Destino: bimestres cujo fim é < `enrollment_date` → `blocked_before_enrollment` (agora com `enrollment_date` sempre populado = data da ação)
  - `action_type_map` atualizado em `grades.py`, `attendance.py` e `class_details.py` (inclui `reclassificacao`)
  - Filtros de enrollment inativa atualizados para incluir `reclassified`

### Ferramenta: Criar Usuários de Alunos em Lote **[24/Fev/2026]**
- Backend: endpoint `POST /api/admin/student-users/bulk-create` (super_admin only) com service em `/app/backend/services/student_account_service.py` — pré-carga em 3 queries + `insert_many` em lotes de 500 (10k alunos em ~10s)
- Script CLI: `python backend/scripts/create_student_users_bulk.py` (dry-run + `--apply`)
- **UI em Ferramentas de Administração** (`/admin/tools`): novo card "Criar Usuários dos Alunos (em lote)" com:
  - Botão "Ver Prévia" (dry-run) → 4 KPIs (avaliados / a criar / já possuem / ignorados) + tabela Aluno/E-mail/Senha
  - Expansor com lista de alunos ignorados e motivo
  - Botão "Criar N usuário(s)" → diálogo de confirmação → "Confirmar Criação"
  - Mensagem de sucesso com contador de inseridos
- Regra: e-mail = `{primeironome}{ultimosobrenome}{MM}@sigesc.com`, senha = `DDMMAAAA`, `must_change_password=true`
- Idempotente: pode rodar quantas vezes quiser — cria apenas quem falta
- Testes: 5/5 pytest em `test_student_bulk_users.py` + 100% frontend (iteration_63)

### Portal do Aluno — Dashboard e Layout **[24/Fev/2026]**
- Nova rota `/aluno` com `AlunoDashboard.jsx` — dashboard do aluno
- Login de aluno agora cai em `/aluno` (Dashboard.js também redireciona `role=aluno` → `/aluno`)
- `/aluno` e `/aluno/boletim` renderizados **dentro do `<Layout>`** (barra superior com logo SIGESC, mantenedora/secretaria, nome do usuário e logout; footer com © 2026 Gutenberg Barroso + link Aprender Digital)
- Boletim exibe turno em português via `SHIFT_LABEL`
- Link "Início" no Boletim aponta para `/aluno`
- PDF **Detalhes da Turma** — turmas AEE agora exibem `Série/Etapa: -` (não o `grade_level`)
- Dashboard do Aluno com **3 cards**:
  - 🎓 **Boletim** (card principal) → `/aluno/boletim`
  - 📅 **Próximos Eventos** — consome `/api/student/me/upcoming-events` (calendário letivo da escola, até 5 eventos futuros, com data relativa Hoje/Amanhã/em X dias/DD-MM-YYYY)
  - 📣 **Avisos** — consome `/api/student/me/announcements` (avisos direcionados, não lidos em negrito + badge vermelho com contador)
- **Bug fix (announcements.py)**: `get_announcement_target_users` agora usa `class_ids` (plural) em vez de `class_id` (singular) — estava quebrado desde sempre pelo modelo `AnnouncementRecipient` só declarar a chave plural. Agora avisos direcionados a turmas realmente chegam aos professores/responsáveis/alunos da turma.
- Testes: 15/15 pytest (`test_student_portal.py` + `test_class_details_pdf_aee.py` + `test_student_dashboard_widgets.py`)

### AEE - Acesso universal do Super Admin (Feb 2026)
- **Backend** (`/app/backend/routers/aee.py`): `ROLES_AEE_WRITE` agora inclui `super_admin`, `admin_teste` e `gerente`; `ROLES_AEE_VIEW` inclui `semed` (além de `semed1/2/3`). Resolve 403 em `GET /api/aee/estudantes`, `/planos`, `/atendimentos` e `/diario`.
- **Frontend** (`/app/frontend/src/pages/DiarioAEE.js`): `fetchData()` refatorado com helper `safeFetchJson()` que valida `response.ok` antes de invocar `.json()` e captura falhas de rede isoladamente. Elimina o crash `TypeError: Failed to execute 'json' on 'Response': body stream already read` quando qualquer endpoint retorna HTTP não-2xx.
- Validação: curl com Super Admin retorna 200 em todos os endpoints AEE; smoke screenshot confirma listagem de estudantes carregando sem erro de console.

### AEE - Salvar Plano AEE corrompendo enums (Feb 2026)
- **Backend** (`/app/backend/text_utils.py`): adicionados `dias_atendimento`, `prazo` e `tipo` à lista `LOWERCASE_FIELDS`. O helper `format_data_uppercase()` estava convertendo valores Literal para MAIÚSCULAS (ex.: `"segunda"` → `"SEGUNDA"`), causando `pydantic.ValidationError` → HTTP 500 → CORS error em produção (proxy Coolify removia headers em respostas 500). Validação: POST `/api/aee/planos` retorna 201 e mantém enums em minúsculas, com texto livre (descrições) em MAIÚSCULAS.
- **Frontend** (`/app/frontend/src/components/PlanoAEEModal.js`): `handleSave()` agora converte `carga_horaria_semanal` de string vazia para `null` via helper `toIntOrNull()`. Resolve HTTP 422 → "Erro ao salvar plano".

### Code Quality - Onda 1 (Feb 2026)
- **MD5 → SHA-256** em `/app/backend/utils/cache.py` (cache TTL) e `/app/backend/pdf/utils.py` (cache de logotipos em disco/memória).
- **Console silencer em produção** — novo `/app/frontend/src/utils/silenceLogsInProduction.js` importado em `index.js`. Anula `console.log/debug/info` quando `NODE_ENV === 'production'`, mantendo `warn/error`.
- **Hardcoded test credentials** — bulk refactor (35 arquivos em `tests/` e `scripts/`) substituindo literais (`@Celta2007`, `aluno123`, etc.) por `os.getenv("SIGESC_TEST_*_PASSWORD", "<default>")`. Permite override via env em CI sem quebrar execução local.
- **React keys estáveis** em StudentsComplete (authorized_persons com `_key` UUID-like, documents_urls com URL como key), SchoolsComplete (5 ocorrências, agora usando IDs/nomes únicos), TutorialDiarioAEE (4 ocorrências, usando títulos de itens estáticos).
  - **Edit flow protegido**: `handleEdit` injeta `_key` em `authorized_persons` carregados do backend (Pydantic ignora extras silenciosamente, então `_key` não persiste — recriado a cada abertura).
  - **Save flow protegido**: `handleSubmit` faz strip do `_key` antes de POST/PUT (limpeza defensiva).
  - **Validação E2E (Playwright)**: abrir aluno → adicionar 2 pessoas → digitar `PESSOA_PRIMEIRA`/`PESSOA_SEGUNDA` → remover a primeira → resultado: `['PESSOA_SEGUNDA']` (correto). 0 React key warnings, 0 console errors. Confirma reconciliação React correta.
  - **Defesa em profundidade no backend** (Feb 2026): `AuthorizedPerson` model tem `ConfigDict(extra="ignore")` explícito; novo `tests/test_authorized_persons_sanitization.py` (2 testes, ambos passando) garante via PUT e POST que `_key` é silenciosamente descartado e nunca chega ao MongoDB. Estratégia: sanitização (não rejeição) — se um cliente legado enviar `_key`, a API ainda funciona.
- **Itens descartados após análise:** `is None`/`is True`/`is False` na codebase são **semanticamente corretos** (distinguem `None` de `False`), e o reviewer flaggeou erroneamente.

### Code Quality - Onda 2 (Hook Dependencies, Feb 2026)
**Estratégia: 1 arquivo por vez, parar para teste manual entre cada um.**

#### useStaff.js ✅ (commitado)
- Função `extractErrorMessage` movida do escopo do hook para escopo de módulo (linha 10). Era recriada a cada render, causando referência stale nos 4 useCallback que a usavam mas não a incluíam nas deps.
- Solução cirúrgica: 1 mudança resolveu os 4 callbacks flagados. Mais correta que adicionar nas deps (que recriaria callbacks a cada render).
- Validação E2E: aba Lotações + edição de servidor + Salvar → toast verde. 0 errors/warnings/loops. `extractErrorMessage` testado com mocks (Pydantic array, string, vazio, sem response) — todos os caminhos OK.

#### VaccineDashboard.js ✅ (commitado)
- Diagnóstico real diferente do reviewer: as deps arrays dos 4 useEffects estavam corretas (setters e module imports são inerentemente estáveis).
- **Bug latente real encontrado:** `localStorage.getItem('accessToken')` lido a cada render → token NÃO se atualizava reativamente em renovações automáticas. As 7 chamadas axios diretas usariam token stale após renovação até algum setState forçar re-render.
- Fix (1 linha): `const { user, logout, accessToken: token } = useAuth();` substituiu o read de localStorage. Token agora reativo.
- Validação: cards KPI populados, 0 errors/warnings/loops.

#### Grades.js ✅ (a aguardando teste manual em produção)
- **Confirmado: useMemo `gradesContextValue` (linha 629) era inútil** — 6 funções (`loadGradesByClass`, `handleSelectStudent`, `handleClearSearch`, `updateLocalGrade`, `saveGrades`, `updateStudentGrade`) eram recriadas a cada render e estavam no deps array → memo invalidava sempre.
- **8 mudanças aplicadas:** 7 funções envolvidas em `useCallback` com deps mínimas + `showAlert` adicionalmente.
- **Bonus de imutabilidade** em `updateLocalGrade` e `updateStudentGrade`: trocados de `[...gradesData]` (captura no closure) e mutação in-place para **functional setState** (`setGradesData(prev => ...)`) com spread imutável. Elimina:
  - Risco de média stale em digitações rápidas (race condition)
  - Mutação acidental do prevState (anti-pattern React)
  - Permite remover `gradesData` e `studentGrades` das deps dos callbacks (eram instabilizadores).
- **Os 3 riscos antecipados pelo usuário:**
  - 🚨 Cálculo errado: blindado (cálculo agora dentro do functional setState)
  - 🚨 Stale data: blindado (functional setState garante estado mais recente)
  - 🚨 useMemo inútil: resolvido (callbacks estáveis fazem o memo realmente cachear)
- Smoke E2E passou (0 errors/warnings/loops). Teste com digitação real pendente — banco preview tem turma sem alunos. **Aguarda validação manual em produção.**

#### Attendance.js ✅ (validar manualmente em produção)
- **2 funções com bonus de imutabilidade** (`updateStudentStatus`, `markAll`) — functional setState (`setAttendanceData(prev => ...)`) elimina stale data quando professor clica rápido em Falta/Presente. Multi-aula path do `markAll` aninha `setAulaStatuses(prevStatuses => ...)` em `setAttendanceData(currentData => ...)` para acessar `students` sem capturar attendanceData no closure.
- **9 funções envolvidas em useCallback** com deps mínimas: `checkDate`, `showAlertMessage`, `loadMedicalCertificates`, `hasActiveCertificate`, `getCertificateInfo`, `loadClassReport`, `generateBimestrePdf`, `loadAlerts`, `navigateDate`.
- **2 funções NÃO foram tocadas** (`loadAttendance`, `saveAttendance`): usam `isMultiAula` que é declarado depois delas no componente — envolver em useCallback geraria TDZ error em runtime. Mantidas como funções normais.
- **Divergência semântica aceita**: removido `if (!attendanceData) return;` global em `updateStudentStatus`/`markAll`. Sem impacto prático (UI bloqueia interação quando attendanceData é null).
- **App.js linha 315**: adicionado `super_admin`, `admin_teste`, `gerente` à `allowedRoles` da rota `/admin/attendance` (mesmo padrão de outras rotas já corrigidas).
- Smoke test passou: página carrega, navegação entre 5 abas funciona, 0 React warnings/loops/runtime errors.

### Token blacklist & revoke-all on logout (Feb 2026, Onda 2 follow-up)
**Descoberta crítica via pytest do contrato de auth (`test_token_refresh_contract.py`):** `auth_utils.token_blacklist` existia mas **nunca funcionou em produção** — bug de datetime aware vs naive engolido silenciosamente por `try/except` em `is_token_revoked`. Logout não revogava nada. Mantinha access_tokens válidos até expirarem (15min).

**Fix multi-arquivo (escopo mínimo, defesa em profundidade):**
- `auth_utils.create_access_token`: adicionado `iat` numérico (segundos epoch) — permite revogação via marker `revoke_all_before`.
- `auth_utils.is_token_revoked`: normaliza timezone do `revoke_all_before` (Motor sem `tz_aware=True` retorna datetime naive) antes de comparar com `token_issued` (aware) — eliminava o TypeError silencioso que causava fail-open.
- `auth_middleware.get_current_user`: consulta `token_blacklist.is_token_revoked()` após decode JWT, com `jti` (futuro) e `user_id+iat` (agora). Tokens emitidos ANTES do fix (sem iat) ignoram check de revoke_all — apenas expiração natural.
- `routers/auth.logout`: chama `revoke_all_user_tokens(user_id, reason='user_logout')` em adição ao revoke do refresh_token. Em ambiente educacional (multi-device, salas compartilhadas), logout invalida TODAS as sessões — comportamento mais seguro.
- `routers/auth.refresh`: consulta blacklist antes de emitir novo token (fecha o buraco onde refresh_token escapava após logout).
- `server.py`: `token_blacklist.set_db(db)` movido para top-level (defesa em profundidade contra falha silenciosa do startup event).

**Pytest suite (11/11 verdes):**
- `test_token_refresh_contract.py`: contrato completo de auth incluindo:
  - Token antigo continua válido após refresh (anti-stale-auth — protege o cenário motivador do VaccineDashboard)
  - 10 chamadas paralelas com tokens antigo+novo: 100% sucesso
  - Logout invalida access_token de TODOS os devices do mesmo usuário
  - Refresh token bloqueado após logout
  - Type confusion (access usado como refresh) → 401

**Trade-off aceito:** logout em device A invalida sessão em device B. Em ambiente educacional, isso é **feature** (evita rastros em PCs compartilhados de escola) — não bug.

#### Split App.js ⏸️ (Onda 2 item g — pendente)

### Forçar Logout Remoto (Feb 2026)
- **Backend** (`/app/backend/routers/admin.py`): novo endpoint `POST /api/admin/sessions/revoke/{user_id}` (somente `super_admin`). Invoca `token_blacklist.revoke_all_user_tokens()`, remove do tracker `active_sessions`, registra audit log e notifica via WebSocket o cliente alvo (`type: force_logout`). Bloqueia auto-revogação (400) — usar `/api/auth/logout` para a própria sessão. Adicionado `import logging` + `logger = logging.getLogger(__name__)` que estavam faltando.
- **Frontend** (`/app/frontend/src/pages/OnlineUsers.js`): nova coluna "Ações" com botão `Forçar Logout` (apenas para super_admin, oculto na própria linha — substituído por "Você"). Modal de confirmação com nome/email do alvo + aviso sobre invalidação de tokens (web/mobile). Toast de feedback (success/error) com auto-dismiss em 5s.
- **Permissão de rota**: `App.js` linha 361 — `super_admin` adicionado a `allowedRoles` de `/admin/online-users`.
- **Validação E2E (8/8 curl + Playwright):**
  - super_admin lista 2 online → POST revoke do aluno (200 + payload com nome/email) → aluno tenta `/api/auth/me` → 401 (token revogado)
  - super_admin tentando revogar a si mesmo → 400 ("Use /api/auth/logout para encerrar sua própria sessão")
  - revoke de UUID inexistente → 404
  - aluno (sem permissão) tentando revogar → 401 (já estava revogado pelo step anterior)
  - UI: modal abre, exibe alvo, botão Cancelar funcional
- **Trade-off educacional**: revogação invalida sessões de TODOS os devices do alvo (mesmo padrão do logout próprio) — feature, não bug, em ambiente de salas compartilhadas.

### Notificação em tempo real de Force Logout (Feb 2026)
- **Frontend** (`/app/frontend/src/components/notifications/NotificationBell.js`): aproveita a conexão WebSocket já montada no Layout. Adicionado handler para `data.type === 'force_logout'` que exibe modal "Sessão encerrada" com a `data.message` enviada pelo backend (`"Sua sessão foi encerrada pelo administrador"`).
- **Modal**: ícone `ShieldAlert`, título, mensagem, aviso de segurança e botão único "Ir para o login" (`data-testid="force-logout-notice-confirm"`).
- **Saída segura**: clique limpa localStorage diretamente (`accessToken`, `refreshToken`, `userData`, `lastActivityTime`) e usa `window.location.replace('/login')` — hard reload para resetar todo estado React, WebSockets e timers (semanticamente correto: sessão foi forçosamente encerrada). Evita travamento do `await logout()` no axios interceptor que tenta refresh com tokens revogados.
- **Validação E2E (Playwright)**: aluno logado → super_admin revoga via API → modal aparece em ~3s → clique → redirect `/login` + localStorage limpo. ✅

### 🚨 Fix Crítico: Vazamento Cross-Tenant em designar_gerente (Feb 2026)
**Bug confirmado em produção:** gerente designado para Mantenedora B continuava vendo dados da Mantenedora A.

**Causa raiz** (`/app/backend/routers/mantenedoras.py`): o endpoint `POST /api/mantenedoras/{mid}/gerente` apenas executava `$set: {role, mantenedora_id}`, sem:
1. Revogar tokens ativos do usuário designado → JWT antigo continuava válido com `mantenedora_id` da mantenedora antiga, e `apply_tenant_filter` retornava dados da mantenedora errada (o filtro confia no payload do JWT, não no DB).
2. Limpar `school_links`/`school_ids` que apontavam para escolas de outras mantenedoras → `verify_school_access` permite gerente em qualquer school da lista, criando bypass adicional.

**Fix multi-camada:**
- **Sanitização de school_links**: filtra para manter apenas escolas cuja `mantenedora_id == mid` (escolas estranhas são removidas em silêncio, contagem retornada no payload).
- **Revogação de tokens**: `token_blacklist.revoke_all_user_tokens(user_id, reason='designar_gerente_to_mantenedora_{mid}')` força relogin → próximo JWT terá `mantenedora_id` correto.
- **Audit log**: `action='designar_gerente'` registra old/new role, mantenedora_id e contagem de school_links antes/depois.
- **Resposta enriquecida**: agora inclui `school_links_kept` e `school_links_removed_cross_tenant` para feedback ao admin.

**Validação (curl + pytest, 100% verde):**
1. User era admin de Floresta (mantenedora_id=A no DB+JWT) → vê 9 alunos da Floresta com seu token
2. Super_admin promove para gerente de Pau Darco (B): resposta `{"school_links_removed_cross_tenant": 1, "school_links_kept": 0}`
3. Token antigo → **HTTP 401 "Token revogado"** ✅
4. Re-login: JWT novo tem `mantenedora_id=B`, `school_ids=[]`
5. `/api/students` → 0 alunos (Pau Darco está vazia) ✅ (antes: 9 alunos da Floresta)
6. `/api/schools` → apenas escolas de Pau Darco ✅
- **Pytest**: `tests/test_designar_gerente_security.py::test_old_token_revoked_after_designar_gerente` PASSED.

### Congelamento de origem + Migração de dados (Feb 2026)
**Regra de negócio (uniformizada para frequência e notas):**
- **Turma de origem**: a partir da data da ação (transferência, remanejamento, progressão, reclassificação), o **bimestre que contém a `action_date` E todos os posteriores ficam bloqueados para edição**. Notas/células com data anterior à ação permanecem visíveis (read-only); notas em bimestres totalmente posteriores são retornadas como `null`; células de frequência com `date >= action_date` aparecem em branco no PDF.
- **Turma de destino**: cópia uniforme — frequência E notas migram em **TODAS as 4 ações** (antes só remanejamento copiava notas). Cada registro copiado recebe `migrated_from_class_id` (id da turma origem) e `migrated_at` (timestamp ISO). Edição dos registros migrados é restrita a **admin / admin_teste / super_admin / gerente / secretario**; professor regular vê os valores em read-only com badge "Migrado".
- **Histórico legado**: ações anteriores ao fix permanecem editáveis livremente (regra vale apenas para ações futuras, sem migração retroativa).

**Backend:**
- `students.py copy_student_data_to_new_class`: removido o branch `if copy_type == 'remanejamento'` que limitava a cópia de notas; agora copia em qualquer `copy_type`. Cada record (`attendance.records[]`) e cada documento `grades` recebe `migrated_from_class_id` + `migrated_at`. Permissão expandida: super_admin/gerente também podem invocar (necessário para o fluxo do bug de tenant que revoga tokens). Idempotente — não sobrescreve registros já existentes no destino.
- `grades.py _ensure_can_edit_migrated_grade()`: helper aplicado em `POST /grades`, `PUT /grades/{id}` e `POST /grades/batch` — bloqueia (403) edição de grade com `migrated_from_class_id` para roles fora da lista autorizada.
- `grades.py load_grades_by_class`: `blocked_after_action` passou de `b_start > action_date` para `b_end >= action_date` (inclui bimestre que contém a data). Bimestres com `b_start > action_date` retornam `b1..b4=null` no payload (mantém B1=8.5 visível, B2..B4=None) + recovery/rec_s1/rec_s2/final_average zerados quando o bimestre referenciado está totalmente após a ação.
- `attendance.py _block_if_changing_migrated_attendance()`: ao salvar uma sessão de frequência, registros com `migrated_from_class_id` são preservados intactos para roles não autorizadas; para roles autorizadas, a flag de migração é mantida ao atualizar o status (auditável).
- `attendance_ext.py get_attendance_bimestre_pdf`: busca `student_history` por turma para alunos inativos; durante a montagem do attendance_by_date pula registros com `att.date >= action_date` → célula em branco no PDF.
- `auth_middleware.verify_school_access`: cross-tenant guard — se `active_tenant` ≠ `school.mantenedora_id`, retorna 403 "Escola pertence a outra mantenedora" (fecha bypass mencionado no fix anterior; gerente não pode mais usar `GET /schools/{id}` para ler escola de outra mantenedora mesmo via school_links residuais).

**Frontend:**
- `Grades.js canEditStudentGrade()`: adicionado parâmetro `gradeRecord` — retorna `false` se `gradeRecord.migrated_from_class_id` e user fora da lista autorizada.
- `GradesTable.jsx`: badge âmbar "Migrado" ao lado do nome do aluno; tooltip nos campos explicando "Nota migrada da turma de origem — apenas secretário, gerente ou super administrador podem editar".

**Pytests** (`tests/test_freeze_origin_and_migration.py` + `tests/test_freeze_migration_extra.py`, 7/7 passing):
1. `copy-data` marca todos os registros com `migrated_from_class_id` (3 attendances + 1 grade copiados).
2. `load_grades_by_class` na origem retorna `blocked_after_action=[1,2,3,4]` para aluno remanejado em 10/03/2026, e `b1=8.5` (visível), `b2=b3=b4=null`.
3. Professor tentando PUT/POST/batch em grade migrated → 403.
4. Super_admin pode editar grade migrated; flag `migrated_from_class_id` é preservada após update.
5. PDF de frequência por bimestre retorna 200 (turma destino e turma origem com action_date).
6. Cross-tenant guard: gerente Mant A com school_link residual → 403 'Escola pertence a outra mantenedora'.

### Fix Race Condition em revoke_all_user_tokens (Feb 2026)
**Bug descoberto pelo testing agent durante a validação:**
- `auth_utils.create_access_token` grava `iat` como inteiro de segundos (`int(now.timestamp())`)
- `revoke_all_user_tokens` gravava `revoke_all_before` como datetime com microssegundos
- Quando re-login ocorria no mesmo segundo da revogação, `token_issued (.000) < revoke_before (.872)` → novo token incorretamente classificado como revogado → 401

**Fix em `auth_utils.revoke_all_user_tokens`**: grava `revoke_all_before` no FINAL do segundo (`microsecond=999999`):
- Tokens com `iat` no mesmo segundo da revogação OU anteriores → revogados ✅
- Tokens emitidos a partir do próximo segundo → válidos ✅
- Trade-off: re-login imediato após revoke precisa aguardar virada do segundo (~1s). Em produção UI o fluxo passa por tela de login + digitação (>1s), tornando isso transparente.

**Validação**: 19/19 testes pytest passando incluindo `test_designar_gerente_security`, `test_token_refresh_contract` (11 cenários de auth) e os 7 de freeze/migration.

### "A" de Atestado no PDF de Frequência (Feb 2026)
**Regra de negócio:** dias amparados por atestado médico (registrados pelo secretário em `medical_certificates`) devem renderizar a letra **'A'** nas colunas correspondentes do PDF de frequência, **substituindo qualquer status (P/F/J)** que o professor tenha lançado. Atestado conta como **presença** nos totais (não-falta).

**Backend:**
- `/app/backend/routers/attendance_ext.py get_attendance_bimestre_pdf`: após buscar attendances, varre `medical_certificates` no intervalo do bimestre e monta `medical_days_by_student[student_id] = set(['YYYY-MM-DD'])`. Cada `students_attendance[i]` recebe a chave `medical_days` com a lista ordenada de datas amparadas por atestado.
- `/app/backend/pdf/frequencia.py`: ao iterar `attendance_days`, antes de aplicar `status_map → P/F/J`, verifica `day_only in medical_days` → renderiza **'A'** e incrementa `presencas` (atestado é presença justificada).
- Regra é completamente data-driven: o atestado pode ter sido inserido **antes ou depois** do registro de frequência pelo professor; no momento da geração do PDF, o atestado vence.

**Pytest** (`tests/test_attendance_pdf_atestado.py`): cria turma + aluno + 2 sessões (P em 09/03 e F em 10/03) + atestado cobrindo 09/03 a 12/03 → gera PDF e valida que o texto extraído contém 'A' (independente do status original lançado pelo professor). PASSED.

### Propagação da regra "A" nos relatórios sintéticos (Feb 2026)
**Uniformização**: a regra "atestado vence sobre P/F/J" agora é aplicada também:
- **Relatório de turma** (`GET /api/attendance/report/class/{class_id}`): `student_stats` reclassifica células como `medical` quando data ∈ `medical_days[sid]`; `attendance_percentage = (present + justified + medical) / total * 100`.
- **Cálculo individual** (`GET /api/attendance/student-attendance/{student_id}`): adicionado bucket `medical` e desconto de faltas cobertas por atestado antes do cálculo da porcentagem.
- **Boletim e Ficha Individual** (`pdf/boletim.py` via `routers/documents.py`): no loop que calcula `faltas_regular` e `faltas_por_componente`, datas com 'F' que estão em `medical_days_set` deixam de contar como falta (atestado vence). Resultado: a coluna "Faltas" do boletim e o `total_geral_faltas` ficam alinhados com o PDF de frequência da turma.
- **Declaração de Frequência** (`pdf/declaracoes.py` via `routers/documents.py`): `total_faltas -= faltas_cobertas_por_atestado` antes de calcular `frequency_percentage`.

**Helper centralizado**: `/app/backend/services/attendance_utils.py` expõe:
- `fetch_medical_days_for_student(certs, candidate_dates)` → set de YYYY-MM-DD cobertos por atestado, opcionalmente filtrado pelo calendário letivo.
- `classify_with_atestado(date, raw_status, medical_days)` → status efetivo ('A'/'P'/'F'/'J'/'L').
- `compute_attendance_buckets(records, medical_days)` → P/F/J/L/A/total.
- `attendance_percentage(buckets)` → (P+J+A)/total × 100.

**Pytest adicional**: `test_class_summary_excludes_certificate_days_from_absences` valida que `/api/attendance/report/class/{class_id}` retorna `absent=0`, `medical=2`, `attendance_percentage=100.0` para um aluno com 2 sessões (P+F) ambas cobertas por atestado. 10/10 pytest verde.

### Cabeçalho institucional no PDF de Frequência (Feb 2026)
**Antes**: brasão minúsculo (1.05×0.7cm, quase invisível) e cabeçalho mostrava apenas o nome da escola + período.

**Depois** (`pdf/frequencia.py`):
- Brasão **aumentado para 2.2cm** (proporção quadrada).
- Bloco institucional ao lado do brasão: **Nome da mantenedora** (10pt bold) → **Secretaria** (8pt itálico) → **Slogan** (7pt cinza, opcional) — usa o mesmo padrão do boletim/declaração para consistência visual.
- Coluna direita centralizada: **nome da escola** (linha 1) + **título "FREQUÊNCIA - Xº BIMESTRE DE YYYY"** + **período** (linha 2).
- Linha vertical sutil entre brasão e bloco institucional.
- Fallback gracioso: se a mantenedora não tem brasão, layout colapsa para 2 colunas (institucional + escola/título).

**Validação**: `test_attendance_pdf_renders_A_for_certificate_days` estendido para verificar a presença de "PREFEITURA"/"FLORESTA" e "EDUCAÇÃO" no texto extraído do PDF. Validação manual com curl em escola real (`ESCOLA TESTE MULTISSERIADA`) gerou PDF de 5MB com cabeçalho correto. 7/7 pytest verde.

### Diário AEE: persistência completa do Plano e Atendimento (Feb 2026)
**Bug**: vários campos preenchidos no formulário do Plano AEE não eram salvos. Reabrir o plano para edição mostrava os campos vazios.

**Causa raiz**: o frontend (`PlanoAEEModal.js`) coletava 13 campos que **não existiam** em `PlanoAEEBase`. Por causa de `extra="ignore"`, o Pydantic descartava silenciosamente todos esses campos no save, sem erro visível.

**Campos adicionados ao `PlanoAEEBase` + `PlanoAEEUpdate`**: `escola_origem_nome`, `data_elaboracao`, `periodo_vigencia`, `linha_base_situacao_atual/potencialidades/dificuldades/comunicacao`, `indicadores_progresso`, `frequencia_revisao` (Literal mensal/bimestral/trimestral/semestral), `criterios_ajuste`, `combinados_professor_regente`, `adaptacoes_por_componente`.

**Outros fixes:**
- `carga_horaria_semanal` mudou de `int` (minutos) para `Optional[str]` — frontend envia "4 horas", "240 min".
- `text_utils.LOWERCASE_FIELDS` recebeu `frequencia_revisao` (mesmo bug que `dias_atendimento`).
- Frontend (`PlanoAEEModal.js handleSave`): não converte mais `carga_horaria_semanal` em int.

**Pytests** (`tests/test_aee_full_save.py`, 2/2 passing):
1. `test_plano_aee_saves_and_returns_all_fields`: cria plano com 13 novos campos → GET retorna todos preservados → PUT atualiza 3 campos → GET valida atualização e preservação dos outros.
2. `test_atendimento_aee_full_save_and_edit`: atendimento completo com todos os campos → `duracao_minutos` calculado (60 min) → PUT recalcula (90 min) → demais campos preservados.

**Validação total**: 12/12 pytest verde.

### Validação E2E: Professor → Plano AEE via Modelo (Apr 2026)
**Pergunta do usuário**: "Os Planos AEE a partir de um modelo podem ser criados, salvos e visualizados pelo professor?"

**Resultado**: SIM ✅. Fluxo validado ponta-a-ponta com conta `professor.teste@sigesc.com` (role efetivo `professor`):
1. `GET /api/aee/templates` — 8 modelos institucionais visíveis.
2. `POST /api/aee/planos/from-template` — cria plano em rascunho (HTTP 201) com `professor_aee_id` correto.
3. `GET /api/aee/planos/{id}` — leitura permitida (`check_aee_access`).
4. `PUT /api/aee/planos/{id}` — atualização permitida (`check_aee_write_access`).
5. `GET /api/aee/planos/{id}/pdf` — PDF gerado (HTTP 200, ~5MB).
6. `GET /api/aee/planos` — lista filtrada automaticamente por `professor_aee_id == current_user.id`.
7. UI: Tab "Modelos" + botão "Novo a partir de Modelo" visíveis (`canEdit = role !== 'semed3'`).

### Permissões finais da Biblioteca de Modelos AEE para Professor (Apr 2026)
**Regra institucional SEMED**: Professor recebe TODAS as ações da Biblioteca **EXCETO exclusão** de modelos ou planos.

**Backend (`/app/backend/routers/aee.py`)**:
- `delete_template` agora retorna 403 quando `current_user.role == 'professor'` (mesmo para templates próprios).
- `delete_plano_aee` já não permitia professor (lista de roles autorizadas inclui apenas admins/secretário/coordenador/auxiliar/apoio_pedagogico/super_admin/gerente).

**Frontend (`/app/frontend/src/pages/DiarioAEE.js`)**:
- Nova flag `canDelete = canEdit && !isProfessor`.
- Botão "Excluir Modelo" e "Excluir Plano" agora renderizam apenas quando `canDelete === true`.

**Validação curl** (8 cenários, todos verde):
- Professor cria template: 200 ✅
- Professor exclui próprio template: 403 ✅
- Professor exclui template institucional: 403 ✅
- Professor exclui plano: 403 ✅
- Professor duplica template institucional: 200 ✅
- Professor edita template duplicado: 200 ✅
- Admin exclui templates (cleanup): 200 ✅

**Validação UI screenshot**:
- Aba Modelos: 8 templates listados, ações apenas {duplicar, editar} — sem ícone de lixeira.
- Aba Planos: ações {visualizar, editar, duplicar, novo atendimento} — sem ícone de lixeira.

## Current Backlog

### Importador de Currículo — Extração V2 estruturada por tabela (May 2026) ✅
**Problema reportado**: descrições extraídas vinham com "ruído de colunas" (texto de "Propostas de Atividades" vazando em "Habilidades"), porque pdfplumber `extract_text()` lê em ordem de layout físico, misturando colunas.

**Solução V2** (`services/curriculum_extractor.py` reescrito):
- Passou a usar `page.extract_tables()` em vez de `extract_text()`.
- Detecta automaticamente a estrutura de cabeçalho do DCM:
  - Linha 0: `[EIXOS ESTRUTURANTES, COMPONENTE, ETAPA, ANO, BIMESTRE]`
  - Linha 1: valores (ex.: LÍNGUA PORTUGUESA, 3º, 1º)
  - Linha 2: sub-headers `[OBJETOS, HABILIDADES, PROPOSTAS, Nº DE]`
- Identifica a coluna "HABILIDADES" e extrai SOMENTE ela, eliminando vazamento.
- Agora preenche **automaticamente**: `ano`, `bimestre`, `componente_codigo`, `etapa`, `eixo_estruturante` diretamente dos cabeçalhos da tabela.
- Trade-off: ~10 códigos perdidos em páginas com estrutura atípica (138 vs 148 antes), mas **qualidade massivamente superior**.

**Fix complementar**: `routers/curriculum_import.py` agora propaga `bimestre` e `eixo_estruturante` do extractor → `CurriculumImportItem` → `CurriculumSkill` no commit.

**Re-importação concluída**: 138 habilidades de LP extraídas do DCM Floresta do Araguaia, todas com `ano` E `bimestre` preenchidos. Exemplo validado:
```
EF03LP01 | Ano: 3 | Bimestre: 1
Descrição: "Ler e escrever palavras com correspondências regulares contextuais entre grafemas e fonemas – c/qu; g/gu; r/rr; s/ss; o (e não u) e e (e não i) em sílaba átona em final de palavra – e com marcas de nasalidade (til, m, n)."
```
Distribuição balanceada: 4 anos × 4 bimestres com 1-9 habilidades cada.

### Importador de Currículo PDF → Extração → Revisão → Importação (May 2026) ✅
**Pipeline completo** para escalar ingestão de BNCC/DCM com qualidade.

**Backend**:
- `services/curriculum_extractor.py`: regex `E[FIM]\d{2}[A-Z]{2}\d{2}[A-Z]?` + pdfplumber. Deduplica por código (mantém descrição mais longa), classifica etapa por ano (1-5 iniciais, 6-9 finais), suporta códigos de faixa (EF15, EF89, etc.) marcando `ano=None` e `ano_range="15"`.
- `routers/curriculum_import.py`: 7 endpoints (upload, list, get, update item, bulk-status, commit, cancel). Todos super_admin via Matriz `nav-curriculum-button`.
- Models `CurriculumImportBatch` + `CurriculumImportItem` com status workflow: `pending → edited/approved/rejected → imported/duplicate`.
- Commit cria componente novo se necessário, verifica duplicidade em tempo real (caso outro batch tenha importado), preserva itens já imported entre re-uploads do mesmo PDF.

**Frontend** (`pages/CurriculumImport.jsx` em `/admin/curriculo/importar`):
- Card de upload (file + select componente + select fonte).
- Lista dos lotes recentes (cards clicáveis).
- Tabela revisional com: filtros por status (pending/approved/rejected/imported/duplicate/edited), busca por código/descrição, seleção múltipla, edição inline (código/descrição/ano), ações em lote (aprovar/rejeitar/reset), botão "Importar N aprovadas" (commit).
- Menu do Dashboard ganhou entrada "Importar Currículo (PDF)" com testId `nav-curriculum-import-button` (super_admin).

**Pytest** (`tests/test_curriculum_import.py`, 3/3 verde em 106s):
1. `test_full_pipeline` — upload do DCM real (148 LP) → edit item → bulk-approve 3 → commit (3 inserted, 1 component created) → re-upload marca 3 como duplicate.
2. `test_upload_rejects_non_pdf` — .txt rejeitado 400.
3. `test_commit_without_approved_returns_400` — commit sem aprovar → 400 com mensagem.

**Teste real com PDF do usuário**: `DOCUMENTO-CURRICULAR-DO-MUNICIPIO-DE-FLORESTA DO ARAGUAIA.pdf` → 148 habilidades de Língua Portuguesa extraídas. Qualidade: códigos BNCC 100% corretos, descrições capturadas (algumas com ruído de layout de colunas — revisão inline resolve).

### Sprint B parcial — Campo Habilidade BNCC/DCM em LearningObjects (May 2026)
**Componente novo** (`/app/frontend/src/components/SkillPicker.jsx`):
- Combobox multi-select com busca remota (`/api/curriculum/skills?q=...`), debounce 300ms.
- Filtro automático por `ano` da turma (extrai dígito de `grade_level`) e por `componenteCodigo` opcional.
- Chips removíveis (X) com badge da fonte (BNCC/Computação/DCM/Municipal), código + descrição, e botão `+` para inserir descrição no campo Conteúdo.
- Cache local das habilidades selecionadas para não refazer queries.
- Cobre retrocompatibilidade: registros antigos sem `skill_codigos` continuam funcionando.

**Backend**:
- `LearningObjectBase/Create/Update/Model` agora têm `skill_codigos: List[str] = []`.
- Mongo persiste array de códigos BNCC; pytest `tests/test_learning_objects_skills.py` (2/2 verde) valida CRUD + retrocompatibilidade.

**Frontend**:
- `services/api.js` ganhou `curriculumAPI` (components, skills, methods, stats, CRUD).
- `pages/LearningObjects.js` integra o `SkillPicker` ANTES do textarea Conteúdo, propaga `skill_codigos` em `formData` e nas operações de load/save/reset.

**Validação E2E (testing agent, iteration_68)**: render, busca remota debounced, dropdown, chips, contador "X selecionada", botão `+` para inserir descrição — todos OK.

### Módulo de Currículo BNCC/DCM — Sprint A (May 2026) ✅
**Catálogo curricular vivo**: SIGESC agora indexa Componentes, Habilidades (com código BNCC tipo `EF03MA02`) e Metodologias.

**Models** (`models.py`):
- `CurriculumComponent` — Língua Portuguesa, Matemática, Computação, Estudos Amazônicos (DCM Floresta do Araguaia), etc. Campo `eixo_estruturante` para os 4 eixos do DCM ("Linguagem e suas Formas Comunicativas", etc.). `etapa` ∈ infantil/anos_iniciais/anos_finais/eja/medio. `fonte` ∈ BNCC/BNCC_COMPUTACAO/DCM_FA/MUNICIPAL.
- `CurriculumSkill` — `codigo` único (ex.: EF03MA02), `descricao`, `ano` (1-9), `bimestre` (1-4 — DCM organiza por bimestre), `objeto_conhecimento`, `unidade_tematica`, `metodos_recomendados[]`.
- `CurriculumMethod` — biblioteca de metodologias reutilizáveis (Sequência didática, Resolução de problemas, etc.).

**Router** (`/api/curriculum/`):
- `GET /components`, `GET /skills?componente_id&ano&bimestre&fonte&etapa&q&limit&offset`, `GET /skills/{codigo}`, `GET /methods`, `GET /stats`.
- `POST/PUT/DELETE` em components/skills/methods restritos a super_admin via `nav-curriculum-button` (Matriz de Permissões).
- Soft-delete de componente com skills vinculadas (não destrói dados); hard-delete se vazio.
- Atualização de código de componente repropaga `componente_codigo` em skills.

**Seed** (`seeds/seed_computacao_bncc.py`):
- BNCC complementar de Computação (Resolução CNE/CP nº 1/2022) — 41 habilidades cobrindo os 3 eixos (Pensamento Computacional, Mundo Digital, Cultura Digital) × Educação Infantil + Anos Iniciais (1º-5º) + Anos Finais (6º-9º).
- 8 metodologias-base (Programação em blocos, Robótica, etc.).
- Idempotência forte via IDs determinísticos (`hashlib.sha1`) — rodar 2x não duplica.
- Executa automaticamente no startup do FastAPI (`@app.on_event("startup")`).

**Pytest** (`tests/test_curriculum_sprint_a.py`, 8/8 verde):
1. `test_stats_after_seed` — totais corretos (41 skills BNCC_COMPUTACAO).
2. `test_get_skill_by_codigo` — EF03CO01 retorna skill + componente aninhado.
3. `test_filter_skills_by_ano` — `?ano=4` retorna 4 habilidades.
4. `test_text_search` — `?q=algoritmo` encontra resultados.
5. `test_get_skill_404_unknown` — código inexistente → 404.
6. `test_component_crud_super_admin` — POST/PUT/DELETE completo.
7. `test_seed_idempotency` — segunda execução não duplica.
8. `test_skills_pagination` — limit/offset funcionam.

**Próximo (Sprint B)**: página `/admin/curriculo` (UI editável) + combobox "Habilidade BNCC" no `LearningObjects.js` que pré-preenche o conteúdo a partir do código.

### Migração Total para Inline + Atalho Alt+Enter (May 2026)
- **17 campos restantes** migrados de `SpellCheckButton` (modal) para `SpellCheckTextarea` (sublinhado inline): ActionPlans (descrição), PreMatricula (observações), StudentsComplete (8 campos), DiarioAEE atendimento (3) + templates (4).
- **Atalho Alt+Enter** dentro de palavra sublinhada aplica automaticamente a 1ª sugestão (estilo Google Docs). Implementado via `handleKeyDown` em `SpellCheckTextarea.jsx`.
- Popover de sugestões agora mostra dica visual "Alt+Enter aplica a 1ª sugestão" no rodapé.
- **Validação E2E (testing agent, iteration_67)**: Alt+Enter testado com sucesso em /avisos (typed "otimo" → Alt+Enter → "ótimo" no valor final). 4 cenários verdes, demais confirmados via código-fonte. Zero regressões.

### Corretor Ortográfico PT-BR — Sublinhado Inline (May 2026)
**Feedback do usuário**: "O erro não é destacado direto no texto, tipo sublinhada a palavra com erro."

**Solução**: novo componente `SpellCheckTextarea` (`/app/frontend/src/components/SpellCheckTextarea.jsx`) substitui o `<textarea>` nativo com técnica de **overlay espelhado**:
- Uma `<div>` absoluta atrás do textarea, com o mesmo `className` (padding, font, line-height), renderiza o texto quebrado em `<span>`s. Spans de erro recebem `underline decoration-wavy` com cores por tipo (rosa=ortografia, âmbar=gramática, azul=estilo, violeta=pontuação).
- Textarea fica visível por cima com `spellCheck={false}` (para não duplicar com o corretor nativo do browser).
- Overlay recebe `textTransform: uppercase` inline para alinhar com a regra global do SIGESC (`index.css` L107-122).
- Scroll do textarea é espelhado no overlay.
- Debounce de 800ms após cada edição; chamada a `/api/spellcheck` é abortada se o usuário continuar digitando (AbortController).
- **Popover de sugestões**: ao posicionar cursor dentro de uma palavra sublinhada (`onClick`/`onKeyUp`), abre popover com a mensagem + 4 melhores sugestões. Clique em "Aplicar" substitui o trecho e reexecuta o check.
- Badge vermelho no canto superior direito mostra contagem total de erros `[data-testid=spellcheck-indicator]`.

**Migração** (textareas nativos → SpellCheckTextarea):
- `pages/Announcements.js` — Conteúdo
- `pages/LearningObjects.js` — Conteúdo e Observações
- `components/PlanoAEEModal.js` — helper local `SpellTextField` encapsula label + SpellCheckTextarea em 11 campos livres

**Validação E2E (testing agent, iteration_66)**: 100% dos 2 cenários testados verdes. Confirmado: indicador aparece, sublinhados ondulados renderizam sob as palavras erradas com alinhamento pixel-perfect mesmo com `text-transform: uppercase`, popover abre ao clicar/posicionar cursor na palavra, sugestão é aplicada e valor final correto. `pointer-events-none` no overlay preserva 100% das interações do textarea (digitação, cursor, scroll).

**Trade-offs**:
- O componente `SpellCheckButton` (modal com lista completa) continua disponível para uso secundário onde inline não faz sentido (ex.: forms compactos, quando user quer "revisar tudo de uma vez"). Os 17 campos migrados na rodada anterior ainda usam o botão — se você quiser trocar todos para o overlay inline, é 1 rodada de search_replace.

### Corretor Ortográfico PT-BR (LanguageTool, May 2026)
**Feature**: corretor ortográfico + gramatical em português (Brasil), 100% gratuito, integrado a 3 telas de alta escrita.

**Backend** (`/app/backend/routers/spellcheck.py`):
- `POST /api/spellcheck` — proxy autenticado para `https://api.languagetool.org/v2/check`.
- Env opcional `LANGUAGETOOL_URL` permite apontar para self-host futuro sem mudar código.
- Body: `{text: str, language: "pt-BR"}`. Limites: texto ≤ 20k chars, 20 req/min por IP (limite da API pública).
- Normaliza payload: `matches: [{message, offset, length, replacements: [str], rule_id, category, issue_type, context}]`.
- Tratamento de 429/504/502 com mensagens amigáveis em PT-BR.
- Desabilita regras pedantes (`WHITESPACE_RULE`, `UPPERCASE_SENTENCE_START`) para reduzir ruído em textos escolares.

**Frontend** (`/app/frontend/src/components/SpellCheckButton.jsx`):
- Componente reutilizável com dois modos: `compact` (ícone) ou botão com label "Revisar".
- Modal lista cada sugestão com: badge do tipo (Ortografia/Gramática/Estilo), contexto com trecho em destaque, mensagem explicativa, botões "Aplicar" por sugestão, botão "Ignorar", e "Aplicar todas as principais" (1ª sugestão de cada erro).
- Após cada aplicação, re-executa o check — offsets sempre consistentes.
- Integração pronta: basta passar `text` + `onApply(newText)`.

**Integrações**:
- `pages/Announcements.js` — campo Conteúdo.
- `pages/LearningObjects.js` — Conteúdo/Objeto e Observações.
- `components/PlanoAEEModal.js` — 11 textareas (Situação Atual, Potencialidades, Dificuldades, Comunicação, Barreiras, Objetivos, Recursos, Indicadores, Orientações Sala Comum, Combinados, Adequações, Adaptações) via helper local `LabelWithSpell`.

**Pytest** (`tests/test_spellcheck.py`, 4/4 verde): detecta erros conhecidos ("vai na" → "à", "otimo" → "ótimo"), retorna vazio para texto correto, exige autenticação, rejeita texto vazio (422).

**Custo operacional**: R$ 0 até 20 req/min por IP. Se a prefeitura crescer, basta subir container LanguageTool no Coolify e apontar `LANGUAGETOOL_URL`.

### Matriz de Permissões — Camada Dinâmica no Backend (Apr 2026)
**Problema**: a Matriz (`/admin/permission-matrix`) controlava apenas a visibilidade do menu no frontend. Usuários podiam burlar a UI e chamar as APIs via curl.

**Solução**: helper `AuthMiddleware.require_permission(db, item_key, default_roles)` em `auth_middleware.py` consulta `permission_overrides` a cada requisição:
- Override `visible=True`  → libera (mesmo se papel fora dos defaults).
- Override `visible=False` → bloqueia com 403 "Acesso negado pela Matriz de Permissões".
- Sem override → fallback para `require_roles(default_roles)`.
- **`super_admin` sempre passa** (evita lock-out acidental).

**Routers migrados** (testId do Dashboard → endpoint):
- `nav-analytics-button` → `routers/analytics.py` (detail endpoints via `_require_admin_tier`)
- `nav-semed-panel-button` → `routers/pmpi.py` (Painel do Secretário)
- `nav-pmpi-engine-button` → `routers/pmpi_engine.py`
- `nav-action-plans-button` → `routers/action_plans.py`
- `nav-mec-button` → `routers/mec_integration.py` (5 rotas)
- `nav-audit-logs-button` → `routers/audit_logs.py` (5 rotas)
- `nav-online-users-button` → `routers/admin.py` (online-users, sessions/revoke)
- `nav-admin-tools-button` → `routers/admin.py` (migrate-*, cleanup-*)
- `nav-logs-button` → `routers/admin_messages.py` (4 rotas, log de conversas)
- `nav-hr-payroll-button` → `routers/hr.py` (24 rotas via replace_all)
- `nav-bolsa-familia-button` → `routers/bolsa_familia.py` (3 rotas)
- `nav-diary-dashboard-button` → `routers/diary_dashboard.py` (via `check_access`)
- `nav-mantenedora-button` → `routers/mantenedoras.py` (create/delete/designar_gerente)

**UI** (`PermissionMatrix.js`): coluna `super_admin` agora é read-only (badge verde "sempre visível") para refletir a lógica do backend e evitar confusão. Rodapé atualizado com aviso.

**Pytest suite** (`tests/test_permission_matrix_backend.py`, 4/4 passing):
1. `test_super_admin_bypasses_matrix_deny` — super_admin ignora override deny.
2. `test_default_deny_without_override_returns_403` — papel fora do default → 403.
3. `test_override_grants_access_to_non_default_role` — override True libera.
4. `test_override_denies_default_role` — override False bloqueia default-allow.

### Bug fix Apr 2026: Plano AEE criado via Modelo invisível para Professor
**Sintoma**: Professor clicava em "Novo a partir de Modelo", recebia mensagem de sucesso, mas o plano não aparecia na lista. Para super_admin aparecia normalmente.

**Causa raiz**: Em `create_plano_from_template`, quando a turma AEE do aluno (`atendimento_programa_class_id`) tinha `teacher_assignment` ativo, o código sobrescrevia `professor_aee_id` com `staff.id`. Mas o filtro `list_planos_aee` para professor compara com `current_user.id` (user.id ≠ staff.id) → plano sumia.

**Fix**:
1. `create_plano_from_template` agora resolve o **user.id** vinculado ao staff (via email match em `db.users`). Só substitui `professor_aee_id` se houver usuário linkado; caso contrário mantém `current_user.id`.
2. Filtro de professor em `list_planos_aee`, `get_diario_aee`, `get_diario_aee_pdf`, `list_estudantes_aee` agora usa `$or: [{professor_aee_id: uid}, {created_by: uid}]`. Garante visibilidade de planos antigos (criados antes do fix com staff.id) E continuará vendo planos onde foi explicitamente designado.

**Validação curl** (6 cenários):
- Cria plano via modelo: `professor_aee_id = user.id` ✅
- Lista planos: aparece (1/1) ✅
- PUT plano: 200 ✅
- Diário Consolidado: aparece ✅
- Plano histórico (`prof_aee_id=staff_id_fake`, `created_by=user.id`): visível via $or ✅

### Hot fix Apr 2026: Plano criado via Modelo continuava sumindo no UI mesmo após backend OK
**Sintoma**: backend agora retornava o plano corretamente para professor (filter $or), mas no UI a lista ainda mostrava 0 linhas após criar via Modelo.

**Causa raiz**: filtro **frontend** (`filteredPlanos` em `DiarioAEE.js`) restringe planos por `selectedTurma` (turma AEE auto-selecionada do professor). Quando o aluno escolhido no modal "Aplicar Modelo" pertencia a outra turma AEE, o plano era criado mas o `filteredPlanos` o escondia.

**Fix frontend** (`handleApplyTemplate` em `pages/DiarioAEE.js`): após sucesso da chamada `/from-template`, antes de chamar `fetchData()`, realinha `selectedTurma` para a `atendimento_programa_class_id` do aluno escolhido (ou limpa se o aluno não tem turma AEE). Garante que o novo plano apareça na lista filtrada do professor instantaneamente.

**Validação UI**: rows_before=0 → criar via UI → rows_after=1, plano "ANA OLIVEIRA - Deficiência Intelectual - Rascunho" visível imediatamente.

### P1
- Regras de cálculo de carga horária prevista na folha de pagamento (aguarda regras de negócio do usuário)
- **Módulo de Currículo (BNCC/DCM)** — Sprint A: models `CurriculumSkill`/`CurriculumMethod`/`CurriculumComponent` + router CRUD `/api/curriculum/` + seed idempotente "Computação". Sprint B: página `/admin/curriculo` + combobox "Habilidade BNCC" em `LearningObjects.js`. Sprint C: endpoint de cobertura curricular + widget dashboard coordenador.

### P2
- Carga horária fracionada em componentes curriculares
- Botão "Baixar em segundo plano" (minimizar modal) para PDFs demorados

### P3
- E-mail de confirmação na pré-matrícula
- Avaliar planilhas do Educacenso como modelo de importação oficial

## Key Files
- `/app/frontend/src/components/Layout.js` - header com TenantSwitcher à esquerda
- `/app/frontend/src/components/TenantSwitcher.jsx`
- `/app/frontend/src/components/TenantSyncBoundary.jsx`
- `/app/backend/tenant_scope.py` - RLS
- `/app/backend/routers/mantenedora.py` - endpoint da mantenedora ativa
- `/app/backend/routers/mantenedoras.py` - CRUD multi-tenant

## Credentials
Ver `/app/memory/test_credentials.md` — super_admin primário: `gutenberg@sigesc.com`


---

## 2026-02 — Currículo: Extrator Híbrido validado + Filtro por Bimestre no SkillPicker

### Validação Issue #1 (Extrator Híbrido V3)
- Rodados `pytest backend/tests/test_curriculum_import.py` (3 testes) + `test_curriculum_sprint_a.py` (8) + `test_learning_objects_skills.py` (2): **13/13 PASS**.
- PDF DCM Floresta (4.6MB, 148 habilidades LP): extração agora cobre **148/148 códigos** (138 high-confidence via tabela + 10 fallback regex), **138 com bimestre** capturado dos metadados da tabela.
- **Otimização single-pass**: `_extract_via_tables` agora coleta `extract_text()` por página dentro da mesma passagem que faz `extract_tables()`, e as Fases B (todos códigos) e C (fallback regex) reutilizam esse cache. Resultado: 101s → 36s (≈3× mais rápido).

### Issue #2 — Filtro `bimestre` no SkillPicker (P1)
**Backend** (`/app/backend/routers/curriculum.py`):
- `GET /api/curriculum/skills?bimestre=N` agora aplica filtro inclusivo: retorna habilidades do bimestre `N` **ou** sem bimestre definido (transversais/anuais como BNCC_COMPUTACAO).
- Combinação `q + bimestre` usa `$and` para evitar conflito de `$or`.
- Cobertura: `tests/test_curriculum_skills_bimestre.py` (3 testes) PASS.

**Frontend**:
- `SkillPicker.jsx` aceita prop `bimestre`. Aplica filtro automático quando o usuário **não** está pesquisando texto, com botão inline "Mostrar todos / Filtrar pelo Nº bim.".
- Cada resultado exibe badge `Nº bim.` (destacado em roxo quando casa com o bimestre da turma).
- `LearningObjects.js`: `getBimestreFromDate(selectedDate)` agora consulta primeiro `bimestrePeriods` (calendário letivo configurado pelo secretário), com fallback para janela trimestral por mês. Bimestre detectado é injetado no `<SkillPicker bimestre={...} />`.

### Backlog atualizado
- (P0) Sprint C — Cobertura Curricular: endpoint analytics + widget dashboard Coordenação.
- (P1) Sugestão "habilidades mais usadas na turma" no topo do dropdown (cache).
- (P2) Carga horária zerada folha de pagamento, botão "Baixar em segundo plano" PDFs pesados, CSV estudantes via Resend, tooltips KPI Secretário, refactor `grade_calculator.py`, `App.js` lazy-load, HttpOnly cookies.



---

## 2026-02 — Currículo v2: Arquitetura Multi-Camadas (BNCC + DCM + Municipal)

### Decisões de produto (Sprint A ajustada)
- Máx 3 habilidades por registro de aula (UX + indicadores de cobertura limpos).
- Retrocompat: `skill_codigos` coexiste com `adaptation_ids` por 30 dias + script de migração automático converte por match de código.
- Obrigatoriedade **condicional**: `adaptation_id` obrigatório apenas quando existe ≥1 adaptation para (componente + ano + bimestre). Fluxos sem base DCM permanecem em texto livre.
- Seed BNCC inicial: Computação (41) + núcleo LP/MA vindo do commit dos batches DCM (criado automaticamente na importação).

### Novos modelos normalizados (3NF)
- `bncc_skills`: núcleo nacional canônico, único por `codigo_bncc`. Sem bimestre.
- `curriculum_components`: agora com `escopo` (NACIONAL|MUNICIPAL), `mantenedora_id`, `area_conhecimento`.
- `curriculum_adaptations`: FK → bncc_skills + FK → component + `ano/bimestre/ordem` + `codigo_local` + `descricao_local`. Unique composto `(mantenedora_id, component_id, bncc_skill_id, codigo_local, ano, bimestre)`.
- `curriculum_adaptation_methods`: 1:N com adaptation.
- `learning_objects.adaptation_ids[]` (máx 3) + campos novos `evidencia_aprendizagem` + `pratica_pedagogica`.

### Backend entregue
- `/app/backend/services/curriculum_v2_migration.py` — migração idempotente (índices, backfill escopo em components, BNCC_COMPUTACAO → bncc_skills + adaptations, skill_codigos → adaptation_ids em learning_objects).
- `/app/backend/routers/curriculum_v2.py` — endpoints: `/bncc`, `/adaptations` (catálogo flattened), `/adaptations/{id}` (joined BNCC+methods), `/adaptations/availability` (obrigatoriedade condicional), `POST /v2/migrate`, `/coverage`.
- `/app/backend/routers/curriculum_import.py` — commit reescrito: cria `bncc_skills` (quando código BNCC), cria `curriculum_adaptations` (upsert por slot único), mantém `curriculum_skills` legado 30d.
- `LearningObjectCreate` com validator: máximo de 3 `adaptation_ids`.

### Frontend entregue
- `SkillPicker.jsx` (v2): consome `/api/curriculum/adaptations`, emite `adaptation_ids`, limite de 3 com aviso, badge de bimestre destacado quando bate com o bimestre corrente da turma.
- `LearningObjects.js`: `adaptation_ids` no formData, inferência de `componente_codigo` a partir do nome do curso selecionado, bimestre via `bimestrePeriods` do calendário letivo.
- `api.js`: `curriculumAPI.{bncc, adaptations, adaptationById, adaptationAvailability, createAdaptation, updateAdaptation, deleteAdaptation, runMigration, coverage}`.

### Cobertura de testes (25 PASS)
- `tests/test_curriculum_v2.py` (6): migração idempotente, listar BNCC, listar adaptations flattened, detalhe com join, availability condicional.
- `tests/test_learning_objects_v2.py` (3): criação com adaptation_ids, rejeição 422 para >3, coverage reportando adaptations usadas.
- `tests/test_curriculum_import.py` (3): pipeline PDF→extract→review→commit agora grava em bncc+adaptations+legacy.
- Outros já existentes seguem PASS (19): sprint_a (8), skills_bimestre (3), learning_objects_skills (2), curriculum_import cleanup.

### Próximos passos
- (P0) Script one-shot de migração manual para `adaptation_ids` em massa (rodar em produção com relatório CSV de conversões/faltas).
- (P0) UI `/admin/curriculo` refatorada para CRUD direto de `adaptations` (componentes + filtros mantenedora + ano + bimestre).
- (P0) Widget dashboard Coordenação com `/api/curriculum/coverage` — barras % concluído por componente/ano/bimestre + drill-down em pendências.
- (P1) Cards de "habilidades mais usadas na turma" no topo do SkillPicker (cache em `learning_objects`).
- (P1) Conditional required no handleSave: chamar `/availability` antes de salvar para exibir aviso.




---

## 2026-02 — Sprint B v2: CRUD Adaptações + Validação + Widget Cobertura

### Ordem entregue (conforme diretriz final)
1. 🔴 **UI `/admin/curriculo/adaptacoes`** — CRUD completo
2. 🔴 **Validação obrigatória condicional** — bloqueia salvar sem `adaptation_id` quando há base
3. 🔴 **Widget Cobertura** — thresholds 90/70 + forecasting por ritmo semanal

### UI Adaptações (CurriculumAdaptations.jsx)
- Filtros sticky (Componente/Ano/Bimestre/Busca), tabela paginada 30/pg, modal edição com auto-fill BNCC informativo + campos editáveis, ação Sincronizar BNCC (`/v2/migrate`), integração com importador PDF.
- Delete inteligente: soft-delete se adaptation em uso por `learning_objects`; hard delete caso contrário.

### Validação Obrigatória (LearningObjects.js)
- `handleSave` chama `/api/curriculum/adaptations/availability` antes de submeter quando `adaptation_ids=[]`. Se `required=true` → bloqueia com alerta informativo direcionando à seleção.
- Inferência automática do `componente_codigo` por nome do curso.

### Widget Cobertura (`/admin/curriculo/cobertura`)
**Thresholds ajustados**: ≥90% verde · 70-89% âmbar · <70% vermelho · futuro cinza sem %.
**Forecasting por ritmo semanal (backend)**: projeção linear `pct × total_days/elapsed_days` → No ritmo / Em risco / Não cumpre. Bimestre fechado <90% → Fechado crítico.
**Banner de alerta**: "⚠️ Cobertura crítica detectada: intervenção necessária" quando `closed_critical>0` ou `critical_rows>0`.
**Drill-down**: cada bimestre expande lista de pendências.
**Backend**: `GET /api/curriculum/coverage?academic_year&class_id&component_id` retorna `{totals, rows, bimestre_windows}`.

### Cobertura de testes (26 PASS)
- `tests/test_curriculum_coverage.py` — seed sintético com b1 fechado 10%, b2 em andamento 70%, b3 futuro; valida status e forecast.
- 25 testes anteriores permanecem PASS (import pipeline, v2 CRUD, availability, learning_objects v2, sprint_a, skills bimestre).

### Navegação (Dashboard.js)
Em "Gestão Institucional":
- "Adaptações Curriculares" (super_admin + coordenador)
- "Cobertura Curricular" (super_admin + admin + coordenador + diretor + secretário)

### Próximos passos
- (P1) Cards "habilidades mais usadas na turma" no topo do SkillPicker (cache em aggregation pipeline).
- (P2) Relatório CSV de migração skill_codigos → adaptation_ids para ops.
- (P2) Deprecação oficial de `skill_codigos` após 30 dias.
- (P3) Extração BNCC nacional completa via CSV oficial MEC.


---

## 2026-02 — Sprint C: Feed de Intervenções Necessárias (gestão ativa)

### Diretriz do usuário
"O sistema deixa de ser painel e vira mecanismo de gestão ativa. Controle > estética."

### Arquitetura (híbrido in-app + e-mail, fallback automático)
- **Collection `intervention_alerts`**: um alerta por (school_id, class_id, component_id, ano, bimestre). Campos: `status` (em_risco|nao_cumpre|fechado_critico), `escalation_level` (1|2|3), `first_detected_at`, `last_notified_at`, `last_coverage_pct`, `resolved_at`.
- **Collection `intervention_notifications`**: inbox in-app por usuário, com `link` profundo para o slot em `/admin/curriculo/cobertura?class_id&component&ano&bim`.
- **Detecção semanal**: APScheduler `CronTrigger(day_of_week='mon', hour=7, minute=0, timezone='UTC')` roda `services/intervention_detector.py`.
- **Gatilho**: `status == em_risco || nao_cumpre || (bim fechado && <90%)`.
- **Escalonamento por tempo sem resolver**: 0–1 sem → Nível 1 (coord) · 2–3 sem → Nível 2 (diretor + coord) · ≥4 sem → Nível 3 (secretaria + diretor + coord).
- **Anti-spam**: novo e-mail/in-app só dispara se `last_notified_at > 7 dias`.
- **Fallback automático**: sem `RESEND_API_KEY` → in-app sozinho + warning log. Sistema NÃO trava por dependência externa.
- **Auto-resolução**: se cobertura ≥ 90% na próxima rodada, alerta é marcado como `resolved_at` automaticamente (e sai do feed).

### Backend entregue
- `/app/backend/services/intervention_detector.py` — detecção por turma, upsert idempotente, cálculo de escalonamento, envio híbrido.
- `/app/backend/routers/interventions.py` — endpoints:
  - `GET  /api/intervencoes` — feed ordenado por severidade+antiguidade (escopo por escola se não super_admin)
  - `GET  /api/intervencoes/notifications` — inbox do usuário + contador `unread`
  - `POST /api/intervencoes/notifications/{id}/read` + `/read-all`
  - `POST /api/intervencoes/{id}/resolve` — resolve manual
  - `POST /api/intervencoes/run-detection` — trigger manual (admin/debug)
- Scheduler inicializado no setup_router (singleton).

### Frontend entregue
- **Página `/admin/intervencoes`**: resumo (ativas/críticas/nível 3), lista com badge de status, nível de escalonamento (Coord→Direção→Secretaria), semanas sem resolver, botões "Resolver agora" (link direto com query params) + "✓" (marcar resolvido).
- **Dashboard**: novo item "Intervenções Necessárias" (ícone Siren vermelho) visível para super_admin/admin/coord/diretor/secretário.

### E-mail (Resend)
- Template HTML com assunto "⚠️ Intervenção necessária — Cobertura curricular em risco", corpo curto (Turma + Componente + Bimestre + Status + % cobertura + Previsão), CTA "Resolver agora" com link direto.
- Disparo somente se `RESEND_API_KEY` E `RESEND_SENDER_EMAIL` configurados.

### Testes (3 PASS em `test_interventions.py`)
1. `run-detection` cria alertas `nao_cumpre` com pct=0 e nível 1 — PASS.
2. Idempotência: 2ª rodada não duplica — PASS.
3. Resolve manual: alerta sai do feed ativo, aparece em `include_resolved=true` — PASS.

### E2E manual
- POST `/run-detection` criou 60 alertas para dados reais do sistema.
- Página `/admin/intervencoes` renderiza com resumo 66/66, cards de escalonamento, botão "Resolver agora" linkando ao slot em Cobertura.

### Próximos passos (Sprint D se solicitado)
- 🟠 (P1) Bell icon no header exibindo `/notifications` com badge de unread.
- 🟠 (P1) Plano de ação automático por escola (gerado a partir dos alertas) — fecha ciclo detectar → alertar → orientar → cobrar → medir.
- 🟠 (P1) Ranking de gestores por taxa de resolução (accountability real).
- ⚪ (P2) Cards "habilidades mais usadas na turma" no topo do SkillPicker (UX).
- ⚪ (P3) Deprecação oficial de `skill_codigos` após 30 dias.



---

## 2026-02 — Sprint D: Ranking de Gestão Curricular (accountability real)

### Diretriz do usuário
"Você está criando transparência de desempenho dentro da rede. Se fizer certo, vira ferramenta de gestão oficial."

### Mitigação política aplicada
- **Escopo por papel**: `super_admin/admin/secretario` veem ranking completo. `diretor/coordenador` veem apenas a própria escola (`self`), nunca comparação com pares.
- **Contexto obrigatório exibido**: nº de turmas da escola, nº de alertas recebidos, taxa de resolução ponderada, nível crítico 3 destacado. Evita leitura sem contexto.
- **Transparência do score**: tooltip/legenda oficial explica fórmula e que o ranking considera apenas alertas reais gerados pelo sistema (não subjetividade).

### Score (0–100)
```
score = max(0, min(100,
    max(0, min(100, 100 - avg_resolution_days * 5)) * 0.5
    + resolution_rate * 100 * 0.4
    - active_alerts * 2
))
```

### Peso por nível de escalonamento
`LEVEL_WEIGHT = {1: 1, 2: 2, 3: 3}` — um alerta Nível 3 (secretaria) pesa 3× mais que um Nível 1 (coord) no cálculo de taxa. Evita gestores "esconderem" problemas graves.

### Métricas por escola
- `received` / `resolved` / `active` (recebidos, resolvidos, pendentes)
- `resolution_rate` (% ponderada por nível)
- `avg_resolution_days` (tempo médio entre first_detected_at e resolved_at)
- `critical_level_3` (backlog Nível 3)
- `weighted_score` + `rank`

### Backend (`/app/backend/routers/interventions.py`)
- `GET /api/intervencoes/ranking?period=(7d|30d|60d|90d|all)&only_mine=bool`
- Agrega intervention_alerts por `school_id`, resolve `school.name` + coordenador ativo vinculado.
- Auto-escopo: roles não-admin recebem apenas `self`, `rows=[]`, `full_access=false`.

### Frontend (`/admin/ranking-gestores`)
- Filtro de período (7/30/60/90/todo).
- Cartão "Seu desempenho" para gestor (role limitado).
- Tabela com medalha 🥇🥈🥉 para top 3, fundo vermelho suave para últimos 3 (quando >5 escolas).
- Colunas: #, Escola, Gestor, Turmas, Alertas, Taxa, Tempo médio, Pendentes (com N3 destacado), Score.
- Legenda oficial explicando fórmula.

### Testes (2 PASS em `test_ranking_gestores.py`, 28 total no suite v2+C+D)
1. Ordenação descendente por score: Escola A (5/5 resolvidos, 2d médio) ranqueia acima de Escola B (1/6 resolvidos + 5 ativos + 2 N3) — PASS.
2. Período `all` engloba alertas antigos — PASS.

### Impacto estratégico desbloqueado
- Base para bônus por desempenho (KPI oficial defensável).
- Identificação automática de escolas críticas (últimos 3 vermelhos).
- Relatórios oficiais de gestão pedagógica.
- Intervenção automática mais agressiva (nos baixos scores).

### Próximos passos (Sprint E opcional)
- 🟠 (P1) Plano de ação automático por escola: usando ranking + pendências, gerar checklist priorizado para a escola com menor score.
- 🟠 (P1) Bell icon no header com badge de unread (`/intervencoes/notifications`).
- ⚪ (P2) Exportar ranking em CSV/PDF para reuniões da SEMED.
- ⚪ (P2) Gráfico de evolução mensal do score (linha temporal por escola).



---

## 2026-02 — Sprint E: Plano de Ação Automático (orientação operacional)

### Objetivo (diretriz do usuário)
"Hoje você detecta e cobra, agora precisa **orientar com precisão operacional**. Sem isso, o gestor sabe que está mal, mas não sabe o que fazer primeiro."

### Fecha o ciclo: detectar → alertar → **orientar** → cobrar → medir

### Motor determinístico (regras fixas, não-IA)
5 regras em ordem de prioridade:

| # | Trigger | Ação | Prio | Prazo | Responsável |
|---|---------|------|------|-------|-------------|
| 1 | `coverage_pct < 70%` | Regularizar habilidades pendentes (top 5 da componente pior) | 1 | 7d | coordenador |
| 2 | `level_3_active >= 3` | Intervenção imediata nas turmas críticas | 1 | 3d | diretor |
| 3 | `lancamento_rate < 0.7` | Cobrar regularização de lançamentos no diário | 2 | 5d | coordenador |
| 4 | `resolution_rate < 0.6` (com ≥3 recebidos) | Revisar fluxo de resposta a alertas | 3 | 14d | coordenador |
| 5 | `avg_resolution_days > 5` | Implantar rotina semanal de acompanhamento | 3 | 14d | diretor |

**Limite**: máx. 5 ações. **Ordem**: (prioridade, impacto alto→medio→baixo).

### Estrutura de cada ação
- `ordem`, `prioridade`, `categoria`, `titulo`, `descricao` (com números concretos), `impacto`, `prazo_dias`, `responsavel`, `metrica_sucesso`, `link` (1 clique → ação no sistema).

### Backend (`/app/backend/routers/interventions.py`)
- `GET /api/intervencoes/plano-acao?school_id=&period=(7d|30d|60d|90d|all)`
- Reaproveita dados de: `intervention_alerts`, `curriculum_adaptations`, `learning_objects`.
- Contexto completo retornado: score, classificação (Adequado/Atenção/Crítico), métricas crus.
- Escopo: super_admin/admin/secretario → qualquer escola. Diretor/coord → apenas sua(s) escola(s).

### Frontend (`/admin/plano-acao`)
- Dropdown de escola + filtro de período.
- Header colorido com nome da escola + contexto (cobertura / alertas / N3 / tempo médio / lançamentos) + score grande.
- Cards de ação com prioridade numerada (#1, #2...), badge de impacto, ícone de prazo, responsável, título, descrição operacional com **números reais**, métrica de sucesso destacada, botão "Agir agora" (link direto).
- Estado vazio: badge verde "Nenhuma ação recomendada".
- Legenda com as 5 regras determinísticas.

### Testes (4 PASS em `test_plano_acao.py`, 32 PASS no eixo v2+C+D+E)
1. Plano gera múltiplas categorias (cobertura + N3 + lançamentos).
2. Ação de cobertura tem link para `/admin/curriculo/cobertura` e métrica.
3. Ação de N3 é urgente (prazo ≤3 dias, impacto alto, responsável=diretor).
4. Contexto retornado tem level_3_active=4, received=5, coverage_pct=0, score<60.

### Navegação (Dashboard → Gestão Institucional)
Novo item "Plano de Ação" (ícone Zap amber) para super_admin/admin/secretario/diretor/coordenador.

### Ciclo completo entregue
```
1. /admin/curriculo/cobertura   — diagnóstico
2. /admin/intervencoes          — alertas com escalonamento
3. /admin/plano-acao            — orientação operacional (NOVO)
4. /admin/ranking-gestores      — accountability mensurável
```

### Próximos passos (quando quiser continuar)
- 🟠 (P1) Bell icon no header com badge de unread (`/intervencoes/notifications`).
- 🟠 (P2) Evolução mensal do score por escola (gráfico linha).
- 🟠 (P2) Exportar plano de ação em PDF para reuniões pedagógicas.
- ⚪ (P3) IA gerando descrição adaptativa por histórico (evolução do motor de regras).



---

## 2026-02 — Sprint F: Multi-Tenant Toolkit (auditoria + branding + onboarding)

### Diretriz do usuário
"Vamos blindar as lacunas. SIGESC é multi-tenant — uma só plataforma para N municípios."

### Confirmação de arquitetura
- A infraestrutura `tenant_scope.py` (filtros automáticos `apply_tenant_filter`) **já existia** e é usada nas rotas de currículo, intervenções, action_plans, students, users, etc.
- Sprint F entrega **transparência operacional sobre as lacunas** + **onboarding rápido** + **branding por mantenedora**.

### Backend novo (`/app/backend/routers/tenant_admin.py`)

**Auditoria** — `GET /api/tenant/audit?sample_size=N`
- Mapeia cada coleção crítica (17): `total`, `with_tenant`, `without_tenant`, `coverage_pct`, `sample`, `parent_for_backfill`.
- Resultado real do sistema: schools/classes/courses/students/staff/enrollments/grades/learning_objects/calendar_events/etc → **100% cobertos**.
- Lacunas legítimas: `intervention_alerts` (cross-tenant para BNCC nacional), `curriculum_adaptations` (BNCC_COMPUTACAO), `curriculum_components` (NACIONAL).

**Backfill** — `POST /api/tenant/audit/backfill?dry_run=bool`
- Deriva `mantenedora_id` automaticamente a partir do parent (`school_id` ou `class_id`).
- Modo seguro com `dry_run=true` (padrão): apenas conta o que seria atualizado.
- Modo escrita explícito (`dry_run=false`): aplica e retorna contagem.

**Branding público** — `GET /api/tenant/branding/public?mantenedora_id=&host=`
- Endpoint **sem autenticação** (consumido pelo login screen).
- Resolução: por `mantenedora_id` → por `host`/subdomain (codigo_inep/slug) → primeira mantenedora → fallback default.
- Retorna: `name`, `logo_url`, `brasao_url`, `primary_color`, `secondary_color`, `secretaria`, `slogan`, `exibir_pre_matricula`, `destaque_mensagem`.

**Onboarding wizard** — `POST /api/tenant/onboard`
- Cria nova mantenedora completa em 1 chamada: mantenedora + admin local (role=gerente) + escola inicial opcional.
- Senha temporária `Mudar@2026` com `must_change_password=true`.
- Validação de e-mail único.

### Frontend (`/admin/tenant`)

Página dedicada para super_admin:
- **Banner de status**: amarelo se há órfãos, verde se 100% íntegro.
- **Tabela de auditoria**: coleção por coleção, com barra de progresso colorida (verde/amarelo/vermelho), órfãos destacados, parent disponível para backfill.
- **Botão "Rodar backfill"**: aplica derivação automática de mantenedora_id (com confirmação).
- **Botão "Nova Mantenedora"**: modal wizard com nome + CNPJ + município/estado + cor primária (color picker) + URL logotipo + admin (nome+email) + escola inicial opcional. Mostra senha temporária no toast de sucesso.

### Testes (6 PASS em `test_tenant_admin.py`, 38 PASS no eixo total)
1. Branding público responde sem auth.
2. Audit lista coleções esperadas.
3. Audit protegido (401 sem token).
4. Backfill dry_run não escreve.
5. Onboard cria mantenedora + admin + escola completos.
6. Onboard rejeita e-mail duplicado (409).

### Navegação
Dashboard → Gestão Institucional → "Multi-Tenant" (ícone ShieldCheck verde, super_admin only).

### Status pós-Sprint F
- Schools/classes/courses/students/staff/enrollments/grades/learning_objects: **100% blindados** ✅
- BNCC nacional permanece intencionalmente cross-tenant (compartilhada por todas as redes) ✅
- Onboarding de nova mantenedora: **5 cliques / <2 minutos** ✅
- Branding por mantenedora: dados disponíveis via endpoint público ✅

### Próximos passos (quando quiser)
- 🟠 (P1) Aplicar `branding/public` no LoginScreen (logo + cor + nome dinâmicos).
- 🟠 (P2) Whitelabel completo no header da aplicação (logo no topo, tema CSS vars).
- 🟠 (P2) Bell icon com `/intervencoes/notifications` no header.
- ⚪ (P3) Convite Resend automático para o admin local recém-criado.
- ⚪ (P3) Export LGPD por mantenedora (direito ao esquecimento + portabilidade).



---

## Sprint F final — Branding por domínio (Multi-Tenant) [03/Fev/2026]

- Endpoint `GET /api/tenant/branding/public` resolve o tenant via `Request.headers.host` (sem query param — evita domain spoofing e garante cache HTTP correto).
- CRUD de `tenant_domains` (super_admin only) em `/api/tenant/domains`.
- Hook `useTenantBranding.js` consome o endpoint automaticamente a partir do host atual.
- `Login.js` refatorado para aplicar logo + cores via CSS variables dinamicamente.
- Quando o domínio não está mapeado, fallback para branding padrão SIGESC.
- Status: ✅ Concluído, validado (screenshot), 40/40 testes legados + 7 novos passando.

## Fase 2 — Planos de Ação enriquecidos por IA (Claude Sonnet 4.5) [03/Fev/2026]

### Objetivo
Complementar o motor determinístico de 5 regras fixas com uma camada de IA que:
- Gera **análise executiva** contextual em linguagem natural.
- Produz **insight histórico do gestor** baseado nos últimos 90 dias de alertas (taxa de resolução, tempo médio, categoria mais negligenciada).
- Sugere até 2 **recomendações extras** não cobertas pelas regras.
- Enriquece cada ação determinística com uma **descrição mais humana**.

### Implementação
- **Backend**: `services/plano_acao_ai.py` usando `emergentintegrations` + `EMERGENT_LLM_KEY` + `anthropic/claude-sonnet-4-5-20250929`.
- **System prompt** pedagógico (contexto BNCC/DCM, escopo operacional, 1-clique para ação).
- **Output JSON puro** validado e sanitizado (limits de string, cap de extras em 2).
- **Cache 24h** em coleção `ai_plans` por `(mantenedora_id, school_id, period)`.
- **Graceful fallback**: sem chave / timeout / parse fail → endpoint retorna plano determinístico normalmente, `ai_enriched=false`.
- **Endpoint**: `GET /api/intervencoes/plano-acao?ai=true&force_refresh=true`.
- **Frontend** (`PlanoAcao.jsx`): toggle "IA ligada/desligada", card de análise executiva (gradient indigo), bloco de histórico do gestor, cards de recomendações extras com badge "IA", descrição enriquecida (+ details/summary para a descrição técnica original), botão "Regenerar IA".

### Testes
- `backend/tests/test_plano_acao_ai.py` com 8 cenários, 100% pass:
  1. Fallback sem EMERGENT_LLM_KEY.
  2. Enriquecimento OK com mock.
  3. Cache de 24h (segunda chamada não chama Claude).
  4. `force_refresh=true` bypassa cache.
  5. Validação / cap de extras em 2.
  6. Parse de JSON embrulhado em markdown.
  7. Endpoint default mantém retrocompat.
  8. Endpoint com `ai=true` real usando EMERGENT_LLM_KEY (smoke test E2E).
- Validação visual: screenshot exibe análise executiva, histórico de 90d, 5 ações com badges "IA".

### Status
✅ Concluído, 25/25 testes passando (17 legados + 8 novos), sem regressão.

### Próximos passos (backlog atualizado)
- 🟡 (P2) Selo de Conclusão Curricular em PDF — adiado pelo usuário até gestão ativa virar rotina.
- 🟡 (P2) Refatoração `grade_calculator.py` (dívida técnica).
- ⚪ (P3) CSV de importação com convites automáticos via Resend.
- ⚪ (P3) Isolamento de auth (HttpOnly cookies).
- ⚪ (P3) Tooltips explicativos nos KPIs do Secretário.
- ⚪ (P3) Botão "Baixar em segundo plano" para PDFs pesados.

---

## Sprint G2 — HttpOnly Cookies + CSRF + Session Rotation [03/Fev/2026]

### Objetivo
Migrar autenticação de `localStorage + Authorization: Bearer` (vulnerável a XSS) para **HttpOnly cookies** com CSRF protection via double-submit pattern + rotação de refresh token a cada uso.

### Implementação

**Backend**
- `auth_utils.py` — helpers:
  - `set_auth_cookies(response, access, refresh, csrf)` — seta os 3 cookies
  - `clear_auth_cookies(response)` — clear em logout
  - `generate_csrf_token()` — `secrets.token_urlsafe(32)`
  - Cookies: `sigesc_access` (HttpOnly, 15min, path=/), `sigesc_refresh` (HttpOnly, 7d, path=/api/auth), `sigesc_csrf` (não-HttpOnly, 15min, path=/)
  - Flags: `Secure=True` + `SameSite=Lax` por padrão
- `auth_middleware.py` — `get_current_user`: ordem de leitura `cookie → Bearer → query ?token=`
- `routers/auth.py`:
  - `/login` seta cookies + retorna tokens no body (retrocompat)
  - `/refresh` lê de cookie OU body + **rotaciona jti** (revoga antigo ao emitir novo)
  - `/logout` lê refresh do cookie + clear cookies + blacklist
  - `GET /auth/csrf-token` (novo) emite novo CSRF sem invalidar sessão
- `server.py` — `CSRFMiddleware`:
  - Só valida POST/PUT/PATCH/DELETE em `/api/*`
  - **Só exige CSRF quando auth vem por cookie** (Bearer não é vulnerável a CSRF)
  - Pula endpoints públicos: `/login`, `/register`, `/refresh`, `/forgot-password`, `/reset-password`, `/confirm-email-change`, `/resend-email-change`, `/tenant/branding/public`, `/pre-matricula`
  - Double-submit: `X-CSRF-Token` header == `sigesc_csrf` cookie

**Frontend** (`services/api.js`)
- `axios.defaults.withCredentials = true` (cookies em todas requests)
- Interceptor lê `sigesc_csrf` cookie e injeta `X-CSRF-Token` em POST/PUT/PATCH/DELETE
- Bearer continua sendo enviado (retrocompat — backend dá prioridade ao cookie)

### Testes (`tests/test_auth_cookies.py`) — 9/9 pass
1. Login seta 3 cookies com flags corretas (HttpOnly, Secure, SameSite=Lax)
2. `GET /me` funciona só com cookie (sem Bearer)
3. Retrocompat: `GET /me` continua OK com Bearer header
4. Refresh rotaciona: refresh token antigo vira 401 após 1º uso
5. CSRF bloqueia POST de escrita sem header quando auth via cookie
6. CSRF libera com header correto
7. CSRF não é exigido se auth vem via Bearer
8. Logout limpa cookies e invalida tokens
9. `GET /auth/csrf-token` rotaciona o cookie CSRF

### Validação E2E
- Screenshot do browser: cookies visíveis com flags corretas (`sigesc_access: httpOnly=True, secure=True, sameSite=Lax`)
- Dashboard e PlanoAcao funcionando normalmente após migração
- **Regressão: 34/34 testes passando** (17 legados + 8 IA + 9 cookies)

### Segurança — ganhos concretos
- ✅ Access token imune a XSS (não acessível via JS)
- ✅ Refresh token escopado a `/api/auth/*` (mínima superfície)
- ✅ CSRF double-submit em rotas mutadoras
- ✅ Refresh token rotation (detecção de reuso = compromisso)
- ✅ Secure=True garante cookie só via HTTPS
- ✅ SameSite=Lax mitiga CSRF cross-site

### Próximas evoluções (backlog)
- (P2) Remover suporte a Bearer header após período de transição (2-3 semanas)
- (P3) Idle timeout: auto-refresh do access token antes de expirar via interceptor 401 → `/refresh` → retry
- (P3) Alerta visual quando CSRF falhar (mostrar que sessão precisa ser renovada)


---

## Sprint G1 — Explainability IA + Cache Invalidation Reativa [03/Fev/2026]

### Problema resolvido
Fase 2 entregava análises fortes ("abandono operacional — não há gestor ativo") sem transparência sobre quais dados embasaram a inferência. Risco de "caixa preta opinativa" com consequências políticas em secretarias.

### Implementação

**Backend — `services/plano_acao_ai.py`**
- System prompt reescrito: Claude agora é **obrigado** a produzir campos paralelos de evidências para cada afirmação forte.
- Schema enriquecido:
  - `analise_evidencias: [{metrica, valor, fonte}]` (2-4 itens)
  - `insight_evidencias: [{metrica, valor, fonte}]` (1-3 itens)
  - `recomendacoes_extra[].baseado_em: [{metrica, valor, fonte}]` (1+ item)
- `_sanitize_evidencias()` — valida, trunca strings, remove entradas sem `metrica` ou `valor`.
- `invalidate_ai_plans_for_school(db, school_id)` — nova função para invalidação reativa do cache.

**Cache Invalidation Reativa**
- `POST /api/intervencoes/{alert_id}/resolve` → invalida cache IA da escola após resolver
- `services/intervention_detector.run_intervention_detection()` → coleta `touched_schools` (novo alert OU mudança de nível de escalonamento) e invalida o cache dessas escolas no final.
- Evita o pior cenário: IA gerar análise defasada de 24h enquanto o operacional já mudou.

**Frontend (`PlanoAcao.jsx`)**
- Novo componente `<EvidenceList>` — pills com formato `metrica: valor` em fundo branco com borda indigo.
- Renderiza `analise_evidencias` abaixo da análise executiva.
- Renderiza `insight_evidencias` abaixo do insight histórico.
- Renderiza `baseado_em` em cada recomendação extra da IA.
- Tooltip com `fonte` (caminho literal do payload) no hover de cada pill.

### Testes (`tests/test_plano_acao_evidencias.py`) — 6/6 pass
1. Sanitização filtra entradas inválidas (vazias, tipo errado, sem valor).
2. `max_items` é respeitado no corte do array.
3. Resposta IA enriquecida contém `analise_evidencias`, `insight_evidencias`, `baseado_em`.
4. `invalidate_ai_plans_for_school` remove docs apenas da escola alvo.
5. Endpoint `/resolve` dispara invalidação de cache da escola.
6. Endpoint `/plano-acao?ai=true` retorna schema com arrays de evidências.

### Regressão completa — 40/40 testes passando
- 17 legados + 8 IA + 9 cookies + 6 evidências.

### Validação E2E (screenshot)
Na tela real, a Claude gerou:
- Análise: "A escola registra paralisia operacional total: 66 alertas recebidos nos últimos 30 dias, zero resolvidos, 0% de cobertura curricular e 0% de lançamentos no diário..."
- Pills: "Alertas ativos: 66 · Taxa de resolução: 0.0 · Cobertura curricular: 0.0% · Taxa de lançamentos: 0.0"
- Insight: "...Componente mais negligenciado: CO"

**Cada afirmação agora é auditável.** Se o gestor duvidar de um número, basta bater o olho no pill que referencia a fonte exata no payload.

### Status: ✅ PRODUÇÃO-READY
Base consolidada para Sprint G3 (Relatório Executivo Mensal) — o prompt agora gera output rastreável que pode ser enviado por e-mail para Secretários sem risco reputacional.


---

## Sprint G1.5 — Snapshot + Integridade + Modo Auditor [03/Fev/2026]

### Problema resolvido
G1 entregou **evidência auditável** (rastreabilidade do payload). Faltava **prova defensável**: congelamento imutável dos dados no momento da análise + integridade criptográfica. Sem isso, um relatório de abril poderia "mudar" em maio conforme o estado do sistema evoluísse. Inaceitável para uso institucional (Tribunal de Contas, Conselho Municipal, secretaria).

### Implementação

**Backend — `services/snapshot_service.py`**
- Schema `ai_analysis_snapshots`: `{id, version, mantenedora_id, entity_type, entity_id, analysis_type, payload_snapshot, ai_output, model, public_hash, server_signature, created_at, expires_at, created_by, retention_policy}`
- **Hash público SHA256**: JSON canônico determinístico (sort_keys=True, ensure_ascii=False) sobre payload + output + timestamp + model + version → qualquer alteração invalida.
- **Assinatura HMAC-SHA256**: com `SNAPSHOT_HMAC_SECRET` (gerado automaticamente no .env) → prova de origem, impede forjar snapshots externamente.
- **Retenção configurável por mantenedora**: default 5 anos, mínimo 2 anos (LGPD), opção "forever" opt-in. Index TTL no Mongo (`expires_at_dt`).
- **Access control por scope**:
  - `super_admin` → global
  - `admin/gerente/secretario` → sua mantenedora
  - `diretor` → apenas snapshots de suas escolas
  - `professor/aluno/coordenador` → 403

**Backend — `services/snapshot_pdf.py`**
- Gera PDFs institucionais via `reportlab`:
  - **Executivo**: resumo + análise + evidências (inline) + ações + selo de integridade (hash + HMAC + URL de verificação + timestamp + modelo + versão + criado por)
  - **Auditor**: tudo acima + tabelas completas de evidências em cada recomendação + **Anexo A** com payload_snapshot em JSON canônico para reprodutibilidade externa do hash
- Header institucional SIGESC, paleta indigo (aligned com app theme)

**Backend — `routers/snapshots.py`**
- `GET /api/snapshots` — lista com escopo aplicado por role
- `GET /api/snapshots/{id}` — detalhes completos
- `GET /api/snapshots/{id}/verify` — retorna `{valid, hash_valid, signature_valid, public_hash, recomputed_hash, server_signature, recomputed_signature, model, version, created_at, snapshot_id, entity_id}` — endpoint forense
- `GET /api/snapshots/{id}/pdf?mode=executive|auditor` — binário PDF
- `GET /api/snapshots/retention-policy` — política vigente
- `PUT /api/snapshots/retention-policy` — super_admin/admin altera

**Integração automática**
- `enrich_plan_with_ai` agora aceita `user` e **sempre cria snapshot** após validação da resposta IA, antes de persistir o cache. Resposta do endpoint `/plano-acao?ai=true` inclui `snapshot_id`, `public_hash`, `server_signature`.

**Frontend — `PlanoAcao.jsx`**
- Botão **"🔒 Modo Auditor"** (só visível para roles autorizados: super_admin/admin/admin_teste/gerente/secretario/diretor)
- Modal auditor com:
  - Snapshot atual (ID + hash público + HMAC) em monospace
  - Verificação automática ao abrir → banner verde (Documento íntegro) ou vermelho (comprometido) com hash_valid/signature_valid explícitos
  - Botões **"PDF Executivo"** e **"PDF Auditor (completo)"** com download direto
  - **Histórico de snapshots** (até 10 últimos) com badge "ATUAL" no atual
  - Explicação de como validar externamente + referência ao endpoint `/verify`

### Testes (`tests/test_snapshots.py`) — 17/17 pass
1. Hash determinístico (mesmo input → mesmo hash)
2. Hash muda com qualquer alteração (payload, output, timestamp)
3. HMAC computa corretamente com secret dado
4. HMAC retorna None quando secret ausente
5. `verify_snapshot_integrity` detecta tampering (payload alterado ou secret diferente)
6. `create_snapshot` persiste doc com TTL default (5 anos)
7. `get_scope_for_user` bloqueia professor/aluno
8. `get_scope_for_user` escopa diretor em suas escolas
9. `get_scope_for_user` escopa secretario em sua mantenedora
10. `get_scope_for_user` retorna {} (global) para super_admin
11. `set_retention_policy` rejeita custom < 2 anos
12. `set_retention_policy` aceita "forever"
13. Endpoint `/snapshots` lista para super_admin sem escopo
14. Endpoint `/verify` retorna schema rico com todos os campos
15. Endpoint `/pdf` gera PDF válido (executive < auditor em tamanho)
16. Endpoint `/snapshots` bloqueia professor (403)
17. `enrich_plan_with_ai` cria snapshot automaticamente e retorna metadados

### Regressão completa — 57/57 testes passando
- 17 legados + 8 IA + 9 cookies + 6 evidências + 17 snapshots.

### Validação E2E (screenshot)
Modal auditor renderizado com:
- Snapshot ID `c052267c-162a-47c0-bd02-02a225cde17e`
- Hash público `sha256:3061ea2b7ea4fd1ccd81505e532731429d0cb0...`
- HMAC `hmac-sha256:48d69662901943785...`
- Banner verde: "Documento íntegro e autêntico" · Hash válido: sim · Assinatura válida: sim
- Histórico de 3 snapshots anteriores com timestamps
- Instrução completa de como validar externamente

### Impacto estratégico
Saída de *"sistema com IA"* para *"sistema com evidência verificável + trilha de decisão institucional"*. Cada análise agora pode ser:
- Defendida em reunião pública
- Impressa como PDF com selo de integridade
- Validada por um terceiro sem acesso ao banco
- Usada como justificativa em tribunal de contas

### Status: ✅ PRODUÇÃO-READY
Base consolidada para Sprint G3 (Relatório Mensal) que herdará snapshots desde o dia 1.


---

## Sprint G1.6 — Portal Público de Verificação + Verifiable Documents [03/Fev/2026]

### Problema resolvido
G1.5 entregou **prova auditável** restrita a usuários autenticados. Para transformar isso em argumento de venda institucional (prestação de contas pública, reuniões com conselho, tribunal de contas), era necessário um **portal público sem auth** onde qualquer cidadão pudesse validar um documento impresso sem login — **mas sem expor dados sensíveis (LGPD)**.

### Arquitetura desacoplada (decisão crítica)
Em vez de acoplar a validação ao snapshot de IA, criamos a coleção genérica `verifiable_documents` — qualquer documento institucional pode ser emitido com código público: plano_acao, relatorio_mensal, certificado, declaracao, historico, ata, generico.

### Implementação

**Backend — `services/verifiable_docs_service.py`**
- **Código amigável** `SIGESC-XXXX-XXXX` (8 chars de alfabeto seguro — sem 0/O/1/I/L para evitar erro humano)
- **Entropia**: 28^8 ≈ 3.8×10^11 combinações por 8 chars, unicidade garantida por índice único + retry em até 5 colisões
- **Normalização de input** (LGPD-UX real): aceita `"sigescabcd2345"`, `"ABCD-2345"`, `"  abcd2345  "`, `"sigesc-abcd-2345"` — tudo resolve para o mesmo documento canônico
- **Revogação** com motivo + usuário + timestamp — definitivo, sem reversão (mantém simples)
- **Metadata pública mínima**: `{tipo, tipo_label, emitido_em, emitido_por, escopo}` — ZERO payload, ZERO ai_output
- **Integração automática com snapshots**: `create_snapshot()` agora emite código público automaticamente via `create_verifiable_document()` — rastreabilidade unificada

**Backend — `routers/verifiable_docs.py`**
- **Público (SEM AUTH)**: `GET /api/public/verify/{code}` com rate limit **20/min por IP** via slowapi
  - Response LGPD-safe em **3 estados claros**: `"valido" | "invalido" | "revogado"`
  - Valida hash + HMAC do snapshot vinculado quando existe (integridade real, não só "existe")
  - Schema: `{status, codigo, tipo, tipo_label, emitido_em, emitido_por, escopo, integridade, assinatura_valida, mensagem}`
- **Autenticado**:
  - `GET /api/documents` — lista com escopo (super_admin global / admin+secretario mantenedora / diretor suas escolas)
  - `GET /api/documents/{code}` — detalhes
  - `POST /api/documents/{code}/revoke` — revogação com motivo
  - `POST /api/documents/ensure-for-snapshot/{snapshot_id}` — geração **retroativa sob demanda** para snapshots pré-G1.6 (opção C escolhida: evita migração pesada)

**PDF com QR Code + código legível** (`services/snapshot_pdf.py` + `segno`)
- QR Code (correção ISO alta, ~3cm) gerado via `segno` (biblioteca leve, zero deps externas) apontando para `{FRONTEND}/verificar/{code}`
- Bloco destacado em indigo com:
  - Código `SIGESC-XXXX-XXXX` em Courier-Bold 14pt
  - URL do portal: `{FRONTEND}/verificar`
  - QR Code ao lado
  - Instrução: "Digite o código acima ou escaneie o QR Code ao lado para confirmar a autenticidade e integridade deste documento"

**Frontend — `pages/VerifyPublic.jsx` + rotas `/verificar` e `/verificar/:code`**
- Rota **PÚBLICA** (sem autenticação) — nova seção no App.js ao lado de /pre-matricula e /login
- UX moderno: gradient indigo-950 → slate-900, glass-morphism no card, tipografia grande e legível
- **Normalização client-side** espelhando backend — evita chamadas inválidas
- Input com autoFocus, placeholder `SIGESC-ABCD-1234`, monospace
- 3 estados visuais distintos:
  - **Válido**: badge verde `ShieldCheck` + "Documento autêntico e íntegro"
  - **Revogado**: badge âmbar `ShieldAlert` + "Documento revogado" + data da revogação
  - **Inválido**: badge vermelho `ShieldX` + "Documento inválido"
- URL compartilhável após verificação (`navigate` replace)
- Tratamento de 429 (rate limit) com mensagem clara
- Rodapé institucional: "Infraestrutura de Confiança SIGESC · Verificação pública baseada em SHA256 + HMAC-SHA256"

### Testes (`tests/test_verifiable_docs.py`) — 27/27 pass
- **Formato código**: 50 rodadas de regex match, 200 códigos únicos em lote
- **Normalização**: parametrizado com 7 variações aceitas + 7 inválidas
- **Persistência**: create + resolve com input não-canônico + revoke + idempotência
- **LGPD crítico**: `build_portal_response` recebe doc com `"DADO_PESSOAL_SENSIVEL"` embutido e retorna resposta sem vazar nenhum campo sensível (assert negativo explícito)
- **3 estados do portal**: validação individual
- **E2E público**: endpoint SEM auth retorna 200, schema mínimo, bloqueia `ai_output/payload_snapshot/public_hash/server_signature` no response
- **Normalização no endpoint**: código lowercase sem prefix/hífen resolve corretamente
- **Revogação via endpoint**: super_admin revoga → portal público retorna `"revogado"`
- **Integração**: `create_snapshot` emite automaticamente `verification_code`
- **Retroativo**: `ensure-for-snapshot` gera código para snapshot antigo + idempotência

### Regressão completa — 84/84 testes passando
- 17 legados + 8 IA + 6 evidências + 9 cookies + 17 snapshots + 27 verifiable docs.

### Validação E2E (screenshots)
Portal renderizado com `SIGESC-5NJP-XG93` (snapshot real com HMAC) → banner verde "Documento autêntico e íntegro" · Integridade: **confirmada** · Assinatura: **válida**.
Portal renderizado com `SIGESC-MK5B-6UH6` (doc de teste sem HMAC) → banner vermelho "Documento inválido" · Integridade: confirmada · Assinatura: **inválida / ausente** — comportamento correto.
Input normaliza: `sigescabcd2345` → resolve para `SIGESC-ABCD-2345`.

### Impacto estratégico
**Saída de** *"sistema com IA"* **para** *"infraestrutura de autenticação documental da rede municipal"*.
Qualquer documento institucional emitido pelo SIGESC agora pode ser:
- Validado publicamente em 2 segundos via QR Code (sem login)
- Defendido em reunião pública com evidência técnica reproduzível
- Revogado centralmente se for emitido por erro
- Estendido para qualquer outro tipo documental futuro (certificados, declarações) sem reformar infraestrutura

Isso **não é mais feature**. É **base para vender transparência como padrão** em redes que precisam cumprir Lei de Acesso à Informação.

### Status: ✅ PRODUÇÃO-READY
Ciclo completo: G1 (explicação) → G1.5 (prova privada) → G1.6 (verificação pública). Base consolidada para Sprint G3.

---

## Diagnóstico de Duplicidade Curricular no Boletim **[Fev/2026]**

### Problema reportado
Boletim Online da aluna AMANDA DA SILVA BARROS (7º Ano B, ano letivo 2026) exibia
o componente "Ciências" duplicado: uma linha com média 8,0 (curso ativo) e outra
com média 0,0 (curso fantasma/legado). Causa raiz suspeitada: dois `course_id`
distintos com mesmo `name="Ciências"` ambos vinculados em `class.course_ids`.

### Decisão arquitetural (owner)
**NÃO ocultar silenciosamente**. Boletim é espelho fiel do cadastro acadêmico —
esconder inconsistência contradiz a governança de "autoridade verificável" e
mascara erro estrutural que se propaga para Histórico Escolar e snapshots.

### Implementação P0
1. **Detecção de duplicidade no builder** — `utils/bulletin_builder.py`:
   - Função `_flag_duplicate_course_names()` agrupa componentes por nome
     normalizado (casefold + colapsa espaços) dentro de cada segmento.
   - Componentes em conflito recebem flag `_warning_duplicate_name=True`.
   - Boletim emite warning estruturado:
     `{code:"DUPLICATE_COURSE_NAME", course_name, class_id, period_index, course_ids, message}`.
   - **Não remove, não unifica, não esconde**.
2. **Endpoint admin de diagnóstico** — `GET /api/admin/diagnose-class-courses/{class_id}`:
   - Lista cursos da turma com `grades_count`, `attendance_count`, `students_with_records`,
     `active`, `deleted_at`, `suspected_ghost`.
   - Agrupa duplicidades por nome.
   - Identifica `orphan_grades` (notas em `course_id` que não está mais em
     `class.course_ids`).
   - Permissão: role `admin`/`super_admin` (`nav-admin-tools-button`).
   - **Read-only**. Não altera nada.
3. **Frontend (`BulletinViewer.jsx`)**: linha do componente duplicado ganha
   fundo amber + badge "Duplicidade" com tooltip explicativo.

### Adiado (P1 — sob comando humano explícito)
- `POST /api/admin/courses/merge` (preview → impacto → confirmação → snapshot
  before/after → audit trail). Mexe em notas/frequência/histórico/snapshots —
  exige fluxo supervisionado.

### Testes
- `test_bulletin_builder.py::test_duplicate_course_name_emits_warning_and_row_flag` ✅
- 31/31 testes passando (bulletin_builder + temporal_closure + academic_event_lens).

### Status: ✅ DEPLOY READY
Após deploy em produção, owner roda `GET /api/admin/diagnose-class-courses/{turma_amanda}`
para confirmar a hipótese (2 `course_id` "Ciências") e decidir o saneamento manual.

---

## Saneamento Curricular Supervisionado **[Fev/2026]**

### Endpoint `POST /api/admin/classes/{class_id}/remove-course`
Permite remover um `course_id` de `class.course_ids` com governança institucional
forte. Implementa as 3 regras adicionais aprovadas pelo owner:

#### Bloqueios não-negociáveis (sem override por header)
HTTP 409 `COURSE_HAS_ACADEMIC_RECORDS` se houver QUALQUER:
- `grades_count > 0` (notas registradas);
- `attendance_count > 0` (registros de presença);
- `linked_snapshots_count > 0` (snapshots emitidos);
- `linked_documents_count > 0` (documentos verificáveis);
- `linked_render_jobs_count > 0` (render jobs concluídos).

Resposta inclui `linked: {…}` com as contagens para o admin entender o bloqueio.

#### Confirmação institucional explícita
- Header `X-Academic-Confirm: true` obrigatório (alinhado ao padrão de
  `academic_events`). Sem ele → 428 `ACADEMIC_CONFIRMATION_REQUIRED`.
- Body `reason` ≥ 30 caracteres (Pydantic `Field(min_length=30, max_length=500)`).
  Reason curta → 422.

#### Soft removal — preservação histórica
- `course_id` é tirado de `class.course_ids` mas registrado em
  `class.class_course_overrides[]` com `{action, course_id, course_name, removed_at,
  removed_by_user_id, removed_by_user_email, removal_reason}`.
- **NÃO** apaga `grades`/`attendance`/`snapshots`/`documents` — esses permanecem
  como evidência (continuam aparecendo em `orphan_grades` no diagnóstico).
- Audit log canônico via `audit_service.log(action="update", collection="classes")`
  com `old_value`/`new_value` de `course_ids` + `extra_data` rica.

### Diagnose endpoint enriquecido
`GET /api/admin/diagnose-class-courses/{class_id}` ganhou:
- `safe_to_remove: bool` por curso (regra: tudo zerado);
- `linked_snapshots_count`, `linked_documents_count`, `linked_render_jobs_count`;
- `summary.safe_to_remove_count`.

### Frontend — `CurricularDiagnoseModal` no Boletim
- Quando `bulletin.warnings` contém `DUPLICATE_COURSE_NAME` e o usuário tem role
  `admin`/`super_admin`, aparece botão "Diagnosticar" ao lado do warning.
- Modal exibe duplicidades agrupadas por nome com tabela completa
  (course_id, notas, faltas, snapshots, docs, render jobs, status removível/bloqueado/fantasma)
  + lista de notas órfãs.
- **Read-only no UI**: a remoção em si só pelo backend (curl/API), por design —
  evita cliques acidentais em operação curricular crítica. Vide nota explícita
  no rodapé do modal.

### Testes
- `test_admin_curricular_sanitization.py` (7 cenários E2E HTTP):
  diagnose com `safe_to_remove`, bloqueio sem header (428), reason curta (422),
  bloqueio por academic records (409), soft removal sucesso (200 + override),
  idempotência (segunda remoção → 409 `COURSE_NOT_LINKED_TO_CLASS`),
  unauth (401/403).
- 48/48 testes passando (admin_curricular + bulletin_builder + temporal_closure +
  academic_event_lens + verifiable_docs).

### Adiado (P2 — sob comando explícito futuro)
- `POST /api/admin/courses/merge` (migração de notas entre `course_id`).
- Painel `/admin/curricular-integrity` (só quando o problema escalar).
- Heurísticas IA para detectar curso "correto" (rejeitado como anti-pattern).

### Status: ✅ PRODUÇÃO-READY

---

## Curriculum Resolver — Evidence-First **[Fev/2026]**

### Problema raiz reidentificado
A duplicidade "Ciências" no boletim da AMANDA **NÃO** era cadastral em
`class.course_ids` (a turma 7º ANO B nem tinha `course_ids` persistidos).
A causa real: o **fallback amplo por `nivel_ensino`** em
`routers/documents.py::generate_boletim` (linhas 272-289 originais) puxava
TODOS os cursos do nível, e dois "Ciências" no mesmo nível entravam no PDF
— um com nota, outro vazio (média 0.0).

### Solução: `utils/curriculum_resolver.py`
Resolver determinístico **puro**, fonte ÚNICA de componentes curriculares
para boletim online, PDF e (futuramente) render_jobs.

**Ordem de resolução**:
1. **STEP 1 — Evidence**: `course_ids` com `grades` + `attendance` reais do aluno.
2. **STEP 2 — class.course_ids**: matriz explícita da turma (exclui colisões de nome com evidência).
3. **STEP 3 — teacher_assignments**: cursos vinculados a professores ativos (exclui colisões).
4. **STEP 4 — Fallback `nivel_ensino`**: SOMENTE se `no_evidence AND no_matrix` (turma 100% virgem).
5. **STEP 5 — Dedupe final** por nome normalizado (NFKD + casefold + trim):
   1) maior `evidence_score`
   2) `active=true`
   3) `created_at` mais recente
   4) `course_id` (estável)

**Warnings obrigatórios** (mantidos mesmo após dedupe):
- `CLASS_WITHOUT_CURRICULUM_MATRIX`: turma sem `course_ids`.
- `DUPLICATE_COURSE_NAME`: candidatos com mesmo nome — sempre inclui `winner_course_id` e `winner_reason`.

**Metadados por componente**:
`source` (`evidence`|`class`|`teacher_assignment`|`fallback`), `evidence_score`, `dedupe_kept_reason`.

### Integração obrigatória
- ✅ `utils/bulletin_builder.py` — substitui `_resolve_courses_for_class` + fallback de grades órfãs.
- ✅ `routers/documents.py::generate_boletim` — substitui o bloco antigo (linhas 258-320).
- 🔜 Render jobs e Histórico Escolar herdarão automaticamente quando consumirem o boletim.

### Novo endpoint admin
`GET /api/admin/students/{student_id}/bulletin-resolution-debug?academic_year=YYYY`
Retorna observabilidade total: `evidence_course_ids`, `class_course_ids`,
`teacher_assignment_course_ids`, `fallback_course_ids`, `dropped_by_dedupe`,
`duplicate_names_detected`, `resolution_path[]`, `final_resolution[]`.

### Resultado para o caso AMANDA
- Turma sem `course_ids` → warning `CLASS_WITHOUT_CURRICULUM_MATRIX` (transparência).
- Aluna tem nota só no `course_id_A` → STEP 1 captura evidência → STEPS 2/3/4 skip por já ter matrix.
- Fallback por `nivel_ensino` NÃO é acionado (`skip_reason: has_academic_evidence`).
- Apenas 1 "Ciências" no boletim — a com evidência real. Boletim consistente entre PDF/UI/render_jobs.

### Testes (56/56 passando)
- `test_curriculum_resolver.py` (7): evidência + matriz, dedupe por evidência,
  fallback acionado em turma virgem, fallback skipped por evidência,
  cenário AMANDA explícito, teacher_assignments, determinismo.
- `test_bulletin_builder.py` (9): atualizado para o novo comportamento dedupe.
- `test_bulletin_e2e_http.py` (6).
- `test_admin_curricular_sanitization.py` (7).

### Status: ✅ PRODUÇÃO-READY (resolver é a nova fonte canônica)

---

## Bug Fix: Analista (semed2) sem acesso a Escolas **[Fev/2026]**

### Problema reportado
Usuário com role `semed2` (Analista) ou `semed1` (Tutor) — papéis globais
da SEMED, sem `school_ids` específicos — abria `/admin/schools` e via
"Nenhum registro encontrado".

### Causa raiz
`routers/schools.py::list_schools` mantinha lista `wide_roles` desatualizada
em relação ao mapa de permissões do frontend (`/app/frontend/src/pages/Users.js`):
- Frontend declarava `semed1: schools: 'view'` e `semed2: schools: 'view'`.
- Backend tinha apenas `['admin', 'admin_teste', 'super_admin', 'gerente', 'semed', 'semed3', 'ass_social', 'ass_social_2', 'agente_vacinas']`.
- Resultado: `semed1`/`semed2` caíam no `else` → `{"id": {"$in": []}}` → zero escolas.

Mesma inconsistência em `auth_middleware.py::check_school_access` (usado em
`GET /api/schools/{id}`, classes, students etc.).

### Fix mínimo (2 arquivos)
- `routers/schools.py:78` — `wide_roles` ganhou `semed1`, `semed2`.
- `auth_middleware.py::check_school_access` — refatorado para `global_tenant_roles`
  com 11 papéis: `super_admin, admin, admin_teste, gerente, semed, semed1, semed2,
  semed3, ass_social, ass_social_2, agente_vacinas`. Alinhado com `wide_roles`.

**Escrita (`update_school`, `delete_school`)** continua restrita por endpoint
(checagem separada que NÃO usa `check_school_access`) — semed1/semed2 ganham
LEITURA, não escrita.

### Testes (17/17 passando)
- `test_schools_semed_global_access.py`:
  - 11 parametrizados validando `check_school_access(role, school_id)=True`
    para todos papéis globais.
  - 5 parametrizados validando que papéis de escola (`coordenador`, `secretario`,
    `professor`, `diretor`, `aluno`) só passam se `school_id` está em `school_ids`.
  - 1 E2E que loga como `semed2` real (sem `school_ids`) e confirma que
    `GET /api/schools` retorna ambas as escolas do tenant.

### Status: ✅ DEPLOY READY

### Extensão: visão tenant-wide para Turmas e Alunos **[Fev/2026 — pós-fix]**

Após o fix de escolas, a permissão de leitura global foi estendida (apenas leitura):

- `routers/classes.py::list_classes` — `semed1`, `semed2` adicionados à lista de papéis
  com visão tenant-wide (linha ~73). Frontend (`Users.js`) já declarava `classes: 'view'`.
- `routers/students.py::list_students` — mesma extensão (linha ~321). Frontend já
  declarava `students: 'view'`.

**Escrita NÃO foi afetada** — validada por testes E2E:
- `POST /api/classes` com Analista → 403.
- `PUT /api/students/{id}` com Analista → 403.

Write endpoints continuam usando `require_roles(['admin', 'admin_teste', 'secretario'])`
ou checagens próprias que não passam por `check_school_access`.

### Testes finais (21/21 passando)
- 11 unit (`check_school_access` por role — todos papéis globais retornam True).
- 5 unit (papéis de escola exigem vínculo).
- 5 E2E HTTP: escolas + turmas + alunos lendo OK + 2 write-attempts bloqueados (403).


---

## Boletim de Dependência — Fase 3a (Frontend Seletor) **[Fev/2026]**

### Contexto
Sistema sempre tratou dependências como "componentes extras" dentro do boletim
regular do aluno. Com o novo modelo (`dependency_mode` em `students` + collection
`student_dependencies`), alunos que cursam dependência em **outra turma** devem
ter o boletim daquela turma **isolado** do regular.

### Backend (Fases 1 + 2, já entregue)
- `GET /api/students/{student_id}/bulletins-index?academic_year=YYYY` — catálogo
  de boletins disponíveis (regular + N dependências, agrupadas por `class_id`).
- `GET /api/students/{student_id}/dependency-bulletin?target_class_id=…&academic_year=YYYY`
  — boletim isolado contendo somente os `course_id`s das dependências ATIVAS
  do aluno na turma alvo, com frequência computada só nesses componentes.
- `GET /api/classes/{class_id}/roster` — unifica alunos regularmente matriculados
  + alunos cursando dependência naquela turma (uso futuro do professor).

### Frontend (Fase 3a, esta iteração)
`/app/frontend/src/pages/BulletinViewer.jsx`:
- Após selecionar aluno, busca `bulletins-index`. Quando há >1 item, exibe
  `<Tabs>` (shadcn) com triggers `bulletin-tab-regular` e
  `bulletin-tab-dep:<class_id>`.
- `activeBulletinKey` controla qual endpoint é consumido (`/bulletin` vs
  `/dependency-bulletin`). Em erro do catálogo, fallback gracioso para regular.
- Quando boletim ativo é dependência, renderiza card amarelo de contexto
  (`data-testid="bulletin-dependency-context"`) e oculta a `<DependencySection>`
  embutida (que só faz sentido no boletim regular).

### Testes
- `/app/backend/tests/test_dependency_bulletin_phase1.py` — 6 testes pytest.
- `/app/backend/tests/test_dependency_bulletin_e2e_http.py` — 7 testes E2E HTTP
  (catálogo regular+dep, validação 422, 401/403, dependency-bulletin retorna
  `bulletin_type='dependency'`, missing target → 422, target inexistente →
  warning 200 com `DEPENDENCY_CLASS_NOT_FOUND`).
- Smoke UI: fluxo regular intacto, Tabs oculto para aluno sem dependências.

### Status: ✅ DEPLOY READY

### Próximas fases
- ~~**Fase 3b** (P1)~~ ✅ Já estava implementada na "Fase 2 — Dependência de Estudos"
  anterior (backend `routers/grades.py` linhas 374-436 + `routers/attendance.py`
  linhas 365-414 injetam alunos dep com `is_dependency=true`; frontend
  `GradesTable.jsx` + `LancamentoTab.jsx` renderizam `DependencyBadge` + divider).
- **Fase 3c** (P1) ✅ **CONCLUÍDA — Fev/2026 (Iter 76)**

## Boletim de Dependência — Fase 3c (Ficha Individual PDF) **[Fev/2026]**

### Backend — novo endpoint
`GET /api/documents/ficha-individual-dependency/{student_id}?target_class_id=&academic_year=`
em `/app/backend/routers/documents.py` (após `get_ficha_individual`).

- Resolve aluno + turma alvo (404 quando ausente).
- Filtra `student_dependencies` ATIVAS para (student × class × year). Se vazio → 400.
- Hidrata `courses` apenas com os `course_id`s das dependências.
- Filtra `grades` por `course_id ∈ deps` E `dependency_id ∈ deps`.
- Frequência só para chamadas com `class_id == target_class_id` e
  `course_id ∈ dep_course_ids`.
- Reusa `generate_ficha_individual_pdf` com as listas filtradas — sem
  duplicar lógica de renderização.
- Validação de permissão adaptada: aluno `dependency_only` não tem
  `class_id` regular; a "matrícula" vive em `student_dependencies`.
  Mantém apenas o check escola↔usuário para roles não-globais.

### Frontend — botão de download
`/app/frontend/src/pages/BulletinViewer.jsx`:
- Quando `bulletin.bulletin_type === 'dependency'`, o card amarelo de
  contexto inclui botão **"Ficha Individual (PDF)"**
  (`data-testid="ficha-dependency-pdf-btn"`) que abre o PDF em nova aba via
  fetch+blob com headers autenticados.

### Testes (Iter 76 — 13/13 verdes)
- `/app/backend/tests/test_ficha_dependency_e2e_http.py` (6 testes):
  PDF válido, header `application/pdf`, magic bytes, filename pattern,
  sem deps → 400, turma inexistente → 404, aluno inexistente → 404,
  sem auth → 401/403.
- `/app/backend/tests/test_diary_to_bulletin_e2e_http.py` (7 testes):
  catálogo `dependency_only` só dep, `with_dependency` regular+dep, POST
  /api/grades reflete no dependency-bulletin, isolamento de componentes,
  boletim regular do `with_dependency` exclui curso dep, RBAC, warning
  `DEPENDENCY_CLASS_NOT_FOUND`.

### Status: ✅ DEPLOY READY

### Próximas tarefas backlog
- (P1) Boletim Online → PDF institucional via `render_jobs` (QR Code,
  verificação pública por terceiros).
- (P1) Histórico Escolar consolidado.
- (P2) `/admin/curricular-integrity/network-stats`.
- (P2) Refatoração `fetch()` → axios no frontend (CSRF automático).
- (P3) Helper genérico para repositório MongoDB (anti-projection bug).



## Cancelar Transferência — Reversão de transferência indevida **[Fev/2026 — Iter 76]**

### Problema
Aluno solicita transferência (`status='transferred'`) mas em seguida volta atrás
e quer permanecer na MESMA TURMA, como se nada tivesse ocorrido. Antes, a única
saída era refazer manualmente a matrícula (sujeita ao bug "Network Error"
agora corrigido).

### Backend
`POST /api/students/{student_id}/cancel-transfer` em `routers/students.py`:

- Aceita `class_id` opcional via query string ou body. Sem ele, usa o enrollment
  transferido mais recente.
- Exige `student.status='transferred'` (caso contrário 400).
- Reverte o `enrollment.status: 'transferred' → 'active'`.
- Restaura `student.status='active'`, `class_id` e `school_id` da matrícula.
- Adiciona entrada `student_history.action_type='transferencia_cancelada'`
  (auditoria — não conta como movimentação acadêmica).
- NÃO cria nenhum `academic_event` nem bloqueio temporal. A action_type não
  está em `action_type_map` do `class_details.py`, então o aluno volta a
  aparecer SEM o badge "Transferido" na turma.
- Roles permitidos: `admin`, `admin_teste`, `secretario`, `super_admin`, `gerente`.

### Frontend
`/app/frontend/src/pages/Classes.js` — modal "Detalhes da Turma":

- Para cada aluno com `action_label === 'Transferido'`, adiciona botão
  ícone-only (`<Undo2>` laranja) na coluna **Ações**
  (`data-testid="cancel-transfer-{student_id}"`).
- Clique → `window.confirm` com mensagem clara → `studentsAPI.cancelTransfer`
  → toast de sucesso → recarrega `classes/{id}/details` para refletir.

### Testes E2E (5/5 verde)
`/app/backend/tests/test_cancel_transfer_e2e_http.py`:
- Cancel → status volta a 'active', enrollment volta a 'active', histórico
  com `transferencia_cancelada`, aluno some do badge "Transferido" em
  `classes/{id}/details`.
- Cancel em aluno ATIVO → 400.
- Cancel em aluno inexistente → 404.
- Body vazio → usa a transferência mais recente automaticamente.
- Sem auth → 401/403.

### Status: ✅ DEPLOY READY


## Refatoração de PDFs — Streaming Direto para Download **[Fev/2026 — Iter 76]**

### Objetivo
Eliminar abertura de aba intermediária ao gerar PDFs. Download direto no
dispositivo do usuário, sem arquivos temporários no servidor.

### Backend (`/app/backend/routers/documents.py`)
Já usava `BytesIO` + `StreamingResponse` (nada em disco). Mudança: trocar
`Content-Disposition: inline` → `attachment` nos endpoints prioritários:

| Endpoint | Antes | Depois |
|---|---|---|
| `GET /documents/boletim/{id}` | inline | **attachment** |
| `GET /documents/ficha-individual/{id}` (caso normal e remanejamento) | inline | **attachment** |
| `GET /documents/ficha-individual-dependency/{id}` | inline | **attachment** |
| `GET /documents/declaracao-matricula/{id}` | inline | **attachment** |
| `GET /documents/declaracao-frequencia/{id}` | inline | **attachment** |
| `GET /documents/declaracao-transferencia/{id}` | inline | **attachment** |
| `GET /documents/historico-escolar/{id}` | inline | **attachment** |

**NÃO alterados** (fora do escopo, fluxo assíncrono ou batch):
- `GET /documents/certificado/{id}` — continua inline.
- `GET /documents/promotion/{class_id}` — livro de matrícula, continua inline.
- `GET /documents/batch/{class_id}/{type}` — exportação em lote, continua inline.
- `GET /documents/jobs/{job_id}/download` — `render_jobs`, continua inline.

### Frontend
Novo helper `/app/frontend/src/utils/downloadBlob.js`:

```javascript
await downloadBlob(url, filename, headers)
// 1. fetch com Authorization
// 2. response.blob()
// 3. <a download> programático + click() + revokeObjectURL após 1s
```

Consumidores atualizados:
- `components/documents/DocumentGeneratorModal.js`: substitui `window.open(blobUrl)` por `downloadBlob()` para todos os 6 botões (boletim, ficha, matrícula, frequência, transferência, certificado).
- `pages/StudentHistory.js`: `handleGeneratePdf` usa `downloadBlob` direto.
- `pages/BulletinViewer.jsx`: botão "Ficha Individual (PDF)" da dependência usa `downloadBlob`.

### Testes E2E (7 passed / 1 skip, `test_pdf_attachment_streaming.py`)
- Cada endpoint prioritário retorna `Content-Disposition: attachment;` + magic bytes `%PDF-` + `application/pdf`.
- Certificado verificado para CONTINUAR `inline;` (controle negativo).

### Status: ✅ DEPLOY READY

## Fase A — Boletim Oficial PDF (render_jobs + QR Code) **[Fev/2026 — Iter 76]**

### Arquitetura
PDF gerado **assincronamente** via fila `document_render_jobs` (já existente,
contrato V1 congelado). Worker in-process executa handler registrado:

```
POST /api/bulletins/{id}/render-pdf      → enfileira (idempotente)
GET  /api/render-jobs/{id}                → status (pending → processing → completed)
GET  /api/render-jobs/{id}/file           → download autenticado do PDF
GET  /api/verify/boletim/{token}          → verificação PÚBLICA (sem auth, sem CSRF)
```

### Backend
- **`services/document_files.py`** — helper de persistência. Collection
  `document_files` (`{id, data_base64, sha256, filename, mantenedora_id,
  school_id, student_id, document_type, created_at}`). Para PDFs <1MB.
- **`services/bulletin_renderer.py`** — handler:
  1. Parse `boletim:{student_id}:{year}` do `source_snapshot_id`.
  2. Monta dados via `pdf.boletim.generate_boletim_pdf` (mesmas regras do PDF síncrono).
  3. Cria registro em `bulletin_verifications` com token URL-safe de 22 chars
     (~128 bits). **Token NUNCA é armazenado em claro** — só `token_hash =
     SHA-256(token)`. Inclui dados-resumo LGPD-safe e `verify_url`.
  4. Overlay com QR Code (módulo `qrcode==8.2` adicionado) + texto institucional
     no rodapé de TODAS as páginas via `PyPDF2.PdfWriter + reportlab.canvas`.
  5. Computa SHA-256 do PDF final, persiste via `store_pdf`, atualiza
     `bulletin_verifications.pdf_hash_sha256 + file_id`.
- **`routers/bulletin_pdf.py`** — 3 endpoints novos:
  - `POST /bulletins/{id}/render-pdf?academic_year=YYYY` — idempotente via
    `compute_idempotency_key`. Diretor/coord/prof restritos à própria escola.
  - `GET /render-jobs/{id}/file` — ACL por mantenedora (super_admin/admin ignora).
    Header `X-PDF-SHA256` para validação client-side. `Content-Disposition: attachment`.
  - `GET /verify/boletim/{token}` — PÚBLICO. Retorna `valid/revoked/document_type/student_name/school_name/class_name/grade_level/academic_year/issued_at/pdf_sha256/verification_id/note`.
    Trata: token inválido (400), não encontrado (404), revogado (200 valid=false).
- **`server.py`** — registra handler `bulletin` no startup ANTES do worker
  iniciar. Lê `PUBLIC_VERIFY_BASE_URL` (fallback `APP_FRONTEND_URL` → `REACT_APP_BACKEND_URL`).

### Frontend
- **`pages/BulletinViewer.jsx`** — novo `<OfficialBulletinPdfCard>`. Renderizado
  acima das tabelas quando boletim regular (não dependência). Botão
  "Gerar PDF Oficial" enfileira via axios → poll a cada 2s → download
  automático via `downloadBlob`. `data-testid="bulletin-official-pdf-btn"`.
- **`pages/VerifyBulletin.jsx`** (NOVO) — página pública sem layout admin,
  sem requireAuth, em rota `/verify/boletim/:token`. Mostra:
  - ShieldCheck verde + "Documento autêntico" quando válido
  - ShieldAlert âmbar quando revogado
  - ShieldAlert vermelho quando não encontrado
  - Dados-resumo + hash SHA-256 em `<code>` para conferência manual
  - Nota LGPD explicando que notas detalhadas NÃO são expostas.
- **`App.js`** — `<Route path="/verify/boletim/:token">` registrada PÚBLICA
  (sem `<ProtectedRoute>`).

### Segurança / LGPD
- Token gerado com `secrets.token_urlsafe(16)` → 128 bits de entropia.
- DB nunca armazena o token em claro — só `token_hash = SHA-256(token)`.
- Endpoint público retorna SOMENTE dados-resumo: nome, escola, ano,
  turma, série, hash, data de emissão. **NÃO** retorna notas, faltas
  detalhadas, CPF, endereço, dados disciplinares.
- Verificação ainda possível mesmo se token vazar: o hash do PDF é o
  garantidor real — usuário compara visualmente.
- Suporte a revogação manual via `bulletin_verifications.revoked_at`
  (futuro botão de admin).

### Testes (6/6 + suíte 37/37 verdes)
`tests/test_bulletin_pdf_render_jobs.py`:
1. Fluxo completo: enfileira → polling → completed → download → verify
   pública → hash do PDF bate com `pdf_sha256` do verification.
2. Idempotência: segunda chamada retorna `idempotent_hit=true`.
3. Token inválido → 404.
4. Token muito curto → 400.
5. Revogação: `revoked_at` setado → endpoint retorna `valid=false`.
6. Sem auth no enfileiramento → 401/403.

### Status: ✅ DEPLOY READY


## Fase B — Histórico Escolar Consolidado (render_jobs + QR Code) **[Fev/2026 — Iter 76]**

### Princípio
Histórico **consolidado AUTOMATICAMENTE** a partir dos dados internos do
SIGESC (matrículas + notas + frequência + dependências), sem necessidade
de digitação manual. Reusa 100% da infraestrutura criada na Fase A.

### Backend
- **`services/history_consolidator.py`** — `build_consolidated_history(db, student_id=...)`:
  1. Lê todos os `enrollments` do aluno (ANO × TURMA).
  2. Para cada (ano, turma) válido: agrega notas (`grades` por componente:
     média dos b1-b4 lançados), frequência (`attendance` por dia, mesma
     regra da Declaração de Frequência) e classifica resultado:
     - status `active`/`Ativo` → "EM CURSO"
     - status `transferred`    → "TRANSFERIDO"
     - status `cancelled`/`dropout`/`inactive` → "CANCELADO"
     - finalizado → "APROVADO" se média ≥ 6.0 e freq ≥ 75%, senão "REPROVADO"
  3. Mapeia `grade_level` ("3º Ano", "3 ANO", etc.) para slot do template
     ("1º"..."9º") via regex.
  4. Junta com `student_history.records[]` para escolas anteriores fora do
     SIGESC, marcando `_consolidated: false`.
- **`services/history_renderer.py`** — handler `document_type='history'`:
  - Parse `source_snapshot_id = "history:{student_id}"` (sem `academic_year` —
    consolida TODOS os anos).
  - Token URL-safe 128 bits, `token_hash = SHA-256(token)` no DB
    (token claro NUNCA armazenado).
  - Cria `history_verifications` com dados-resumo LGPD-safe.
  - PDF via `pdf.historico_escolar.generate_historico_escolar_pdf` (já existente).
  - Overlay QR Code via `_stamp_qr_overlay` (reusa o helper do bulletin).
  - SHA-256 do PDF final atualiza `history_verifications.pdf_hash_sha256`.
- **`routers/history_pdf.py`** — 2 endpoints novos:
  - `POST /api/students/{id}/historico-consolidado/render-pdf` (idempotente,
    ACL por escola para diretor/coord/secretário).
  - `GET /api/verify/historico/{token}` (PÚBLICO, sem auth).
    Resposta: `document_type`, `student_name`, `school_name`, `years_covered[]`,
    `records_count`, `issued_at`, `pdf_sha256`, `verification_id`, `note`.
- Reusa `GET /api/render-jobs/{id}` (status) e `GET /api/render-jobs/{id}/file` (download).

### Frontend
- **`pages/StudentHistory.js`** — novo botão **"Histórico Oficial (PDF + QR)"**
  (`data-testid="history-official-pdf-btn"`, ícone `ShieldCheck` indigo)
  ao lado do "Gerar PDF (Local)" e "Salvar". Mesmo padrão de polling de 2s.
- **`pages/VerifyHistory.jsx`** (NOVO) — página pública SEM auth, em
  `/verify/historico/:token`. Layout idêntico ao `VerifyBulletin` mas com
  campos específicos: anos consolidados, total de séries, etc.
- **`App.js`** — `<Route path="/verify/historico/:token">` PÚBLICA registrada.

### Testes (6/6 verdes — `test_history_pdf_render_jobs.py`)
1. E2E completo (enfileira → poll → download → verify → hash bate)
2. Idempotência
3. Token inválido → 404
4. Token curto → 400
5. Revogação → `valid=false`
6. Sem auth → 401/403

Suíte ampla 43/43 verde — Fase A + Fase B sem regressões.

### Status: ✅ DEPLOY READY

### Coleções novas (acumulado Fase A + B)
- `document_files` (`{id, data_base64, sha256, filename, mantenedora_id, school_id, student_id, document_type, created_at}`)
- `bulletin_verifications` (token_hash + dados-resumo do boletim)
- `history_verifications` (token_hash + dados-resumo do histórico)


---

## [21/05/2026] Filtro "Turma" no Acompanhamento Bolsa Família

### Solicitação do usuário
> "Na página Acompanhamento Bolsa Família, acrescentar o filtro Turma."
> Aplicar o filtro também à exportação PDF.

### Implementação
- **Backend** (`/app/backend/routers/bolsa_familia.py`):
  - `GET /api/bolsa-familia/students` agora aceita query param opcional `class_id`.
  - `GET /api/bolsa-familia/pdf/{school_id}` agora aceita query param opcional `class_id`; mensagem 404 contextualizada ("Nenhum aluno com Bolsa Família encontrado nesta turma" vs. "...nesta escola").
- **Frontend** (`/app/frontend/src/pages/BolsaFamilia.js`):
  - Novo dropdown `bf-class-filter` (4ª coluna do filtro). Carrega via `classesAPI.list(school_id)` quando a escola muda; reseta a seleção ao trocar de escola.
  - `loadStudents()` e `handleGeneratePdf()` propagam `class_id` quando presente.
  - Label "Todas as turmas (N)" mostra a contagem.

### Testes
- 8 cenários pytest novos em `/app/backend/tests/test_bf_class_filter.py` — todos verdes.
- E2E Playwright validado: dropdown desabilitado até escola escolhida, troca de escola limpa turma, lista atualiza ao filtrar (4→2→4→1→0), PDF inclui `class_id` na URL.
- `/app/test_reports/iteration_77.json` — 100% backend e frontend.

### Status: ✅ COMPLETO



---

## [21/05/2026] Opção "Todas as Escolas" no filtro de Escola (BF)

### Solicitação do usuário
> "Na mesma página, no campo 'Escola', para visualização apenas para os papéis Super Administrador, Administrador, Gerente e Administração (antigo SEMED 3), acrescente como primeira opção, antes dos nomes das escolas, a opção 'Todas as Escolas'."

### Implementação
- **Backend** (`routers/bolsa_familia.py`):
  - `ALL_SCHOOLS_ROLES = ['super_admin', 'admin', 'gerente', 'semed3']`.
  - `GET /api/bolsa-familia/students` agora aceita `school_id` opcional. Quando omitido + role autorizada → agrega alunos BF de todas as escolas (READ-ONLY: `can_edit=false`, `all_schools_mode=true`). Role não-autorizada → 403.
  - `class_id` é IGNORADO em modo all-schools (turmas são por-escola).
  - Resposta inclui `school_id` e `school_name` por aluno; fallback `'Escola não cadastrada'` para FKs órfãos.
- **Frontend** (`pages/BolsaFamilia.js`):
  - `canSeeAllSchools = ALL_SCHOOLS_ROLES.includes(user?.role)` controla visibilidade.
  - Quando habilitado, opção `Todas as Escolas` (data-testid `bf-school-all-option`) é a 2ª no select Escola.
  - Em modo all-schools: dropdown Turma desabilitado com label "Não disponível em Todas as Escolas"; botão "Gerar PDF" disabled com tooltip; botão "Salvar" oculto (canEdit=false); badge "Visão consolidada (somente leitura)" exibido; cada card de aluno mostra o nome da escola acima do nome (data-testid `bf-student-school-{id}`).

### Testes
- 7 cenários pytest em `/app/backend/tests/test_bf_all_schools.py` — todos verdes.
- Regressão completa (filtro Turma + Todas as Escolas): 15/15 verdes.
- E2E Playwright (testing agent iter 78) — 100% frontend.
- 2 bugs encontrados na primeira passada e corrigidos: (a) `class_id` aplicado em all-schools mode; (b) school_name vazio para FKs órfãos.
- `/app/test_reports/iteration_78.json` — bugs corrigidos, retest aprovado.

### Status: ✅ COMPLETO


---

## [21/05/2026] Mini-dashboard executivo no Acompanhamento BF

### Solicitação do usuário
> "Adicionar uma linha resumo no topo ('X alunos | Y abaixo de 75% | Z sem motivo informado') agrupada por escola — transformaria a visão consolidada em um mini-dashboard executivo direto do Acompanhamento, sem precisar abrir o Dashboard de Busca Ativa."

Refinamento (1 linha única sempre; em modo "Todas as Escolas" consolida tudo; chips clicáveis funcionam como filtros).

### Implementação
- **Frontend-puro** (`pages/BolsaFamilia.js`):
  - `studentFlags`: por aluno, marca `belowThreshold` (ao menos 1 mês <75% no intervalo) e `missingReason` (ao menos 1 mês <75% sem `reason_id`).
  - `summary = {total, below, missing}` computado via useMemo.
  - 3 chips clicáveis (data-testids `bf-summary-total`, `bf-summary-below`, `bf-summary-missing`) com cores semânticas (slate / amber / red).
  - Chip clicado vira filtro toggle; `displayedStudents` substitui `students` na renderização.
  - Chips com contagem 0 ficam `disabled` (opacidade + cursor-not-allowed).
  - Botão "Limpar" (`bf-summary-clear`) aparece quando há filtro ativo.
  - Empty state (`bf-summary-filter-empty`) quando filtro resulta em 0.
  - Filtro auto-reset quando escola/turma/intervalo de meses muda.

### Testes
- E2E Playwright (iter 79) — 100% nas features testáveis com dados atuais.
- Toggle dinâmico não foi exercitado visualmente porque a base atual não tem alunos com frequência <75% registrada em 2026; código estático conforme à spec.
- Regressão completa (Turma + Todas as Escolas + ReasonCombobox + Save bulk + PDF) — todas OK.
- `/app/test_reports/iteration_79.json`.

### Status: ✅ COMPLETO


---

## [21/05/2026] Seed de Frequência <75% (validação dinâmica do mini-dashboard)

### Implementação
- Script idempotente: `/app/backend/scripts/seed_test_bf_attendance.py`
  - Cria calendário letivo 2026 global se ausente (4 bimestres Fev → Dez).
  - Seleciona ~30% dos alunos BF (deterministic por nome): hoje 2 alunos.
  - Insere 8 attendance docs com status='F' em Março/2026 → freq cai para ~63%.
  - Atribui `reason_id` MEC para METADE (1 aluno) — separa visualmente os chips "below" e "missing".
  - Todos os docs marcados com `_seed_bf_test: 'frequency_below_75'`.
  - Flag `--undo` remove tudo que foi seedado (não toca em dados reais).

### Resultado Visual (Escola Teste Multisseriada, Fev-Mar)
- 4 alunos | 2 abaixo de 75% | 1 sem motivo informado
- Aluno Teste Duplicidade: 72.7% + reason MEC seedado ("1a • Doença/problemas físicos") → conta em "below" mas NÃO em "missing"
- Ana Oliveira: 63.6% + sem reason → conta em ambos chips
- Joao Santos 90.9% / Maria Silva 100% → não aparecem nos filtros

### Validação dinâmica (E2E via Playwright direto)
- Chip "below" clicado → lista renderiza 2 alunos ✅
- Chip "missing" clicado → lista renderiza 1 aluno ✅
- Botão "Limpar" aparece, clica e volta para 4 ✅


---

## [21/05/2026] Rodada 1 — Fase 0 + Fase 1 (Diário: Audit Log + Optimistic Locking)

### Fase 0 — Diagnóstico (read-only)
Script `/app/backend/scripts/audit_attendance_collisions.py` mapeou estado real:
- 51 attendance docs; `updated_by` em 4 (cobertura parcial); `version` em 0.
- `audit_logs` já existe (4.479 docs) com shape genérico perfeito (`old_value/new_value/extra_data`).
- **Decisão arquitetural**: reutilizar `audit_logs` em vez de criar `attendance_audit_log` (single source of truth).
- `class_schedules` existe mas `schedule_slots=[]`; `teacher_assignments=0` docs → bloqueador conhecido para Fase 4a (futuro).
- Relatório completo: `/app/test_reports/fase_0_diagnostico_diario.json`.

### Fase 1 — Optimistic Locking + Auditoria Pedagógica
- **Modelo `AttendanceCreate`** (`routers/attendance.py`): novos campos opcionais `expected_version`, `force_overwrite`, `change_note`.
- **Endpoint POST `/api/attendance`**:
  - Toda criação nasce com `version=1`.
  - Update detecta mismatch `current_version != expected_version` → **409 `ATTENDANCE_VERSION_CONFLICT`** com `last_modified_by` + timestamp.
  - `force_overwrite=True` sem `change_note` → **422 `OVERWRITE_REQUIRES_NOTE`**.
  - `force_overwrite=True` + `change_note` → save permitido, audit marca `change_kind='overwrite_after_conflict'`.
  - Toda alteração incrementa `version` e atualiza `updated_by/updated_at`.
- **Serviço `services/attendance_audit_diary.py`**:
  - `diff_records()` calcula mudanças aluno-a-aluno.
  - `build_diary_audit_extra()` enriquece `extra_data` do audit_log com: `entity_scope='daily_frequency'`, `class_id`, `class_name`, `date`, `course_id`, `aula_numero`, `change_kind`, `expected_version/final_version`, `student_ids_changed`, `per_student_changes`, `change_note`.

### Migração e Índices
- Script idempotente `/app/backend/scripts/migrate_attendance_version_v1.py`: backfill `version=1` em 51 docs legados. Zero colisões no UNIQUE composto.
- Novos índices em `startup/indexes.py`:
  - `attendance`: UNIQUE `{class_id, date, course_id, aula_numero}` (`ux_attendance_class_date_course_aula`); `{updated_by, updated_at DESC}` (auditoria por professor).
  - `audit_logs`: 3 novos para queries pedagógicas — por turma+data, por aluno alterado, por `change_kind`.

### Testes (6/6 verdes)
`/app/backend/tests/test_attendance_audit_v1.py`:
- create → `version=1`
- update sem expected_version → incrementa
- update com expected_version correto → OK
- update com expected_version stale → 409 com payload completo
- force_overwrite sem nota → 422
- force_overwrite com nota → 200 + audit `change_kind='overwrite_after_conflict'`

### Status: ✅ COMPLETO — Rodada 1 concluída

### Próxima: Rodada 2 (Fases 2+3) — split do domínio Conteúdo (`content_entries`) + auditoria de delete/sobrescrita de conteúdo

### Status: ✅ COMPLETO


---

## [21/05/2026] Rodada 2 — Fase 2 (Split do domínio Conteúdo)

### Decisão arquitetural
Conteúdo pedagógico DEIXOU de ser atributo de `attendance` (campo `observations`) e passou a ser **entidade independente** com o seguinte modelo:
- 1 doc por (`class_id`, `component_id`, `teacher_id`, `date`, `aula_numero`).
- Vínculo SEMÂNTICO — sem `attendance_id`. Frequência e conteúdo coexistem independentemente.
- Multi-autoria desde o nascimento (`teacher_id` é parte da chave).
- Optimistic locking idêntico ao da frequência (Fase 1).
- Soft delete (`deleted=true` + nota obrigatória).
- Audit log com `previous_content` preservado (texto NUNCA destruído).
- Status nasce em `draft` (transições para `published`/`corrected` ficam para Rodada 3).

### Implementação
- **Router** `/app/backend/routers/content_entries.py`:
  - `POST /api/content-entries` (cria; teacher_id default = usuário logado)
  - `GET /api/content-entries?class_id=&date=&teacher_id=&component_id=&include_deleted=`
  - `GET /api/content-entries/{id}`
  - `PUT /api/content-entries/{id}` (com `expected_version`, `force_overwrite`, `change_note`)
  - `DELETE /api/content-entries/{id}` (soft delete com `change_note` obrigatório)
- **Serviço** `services/content_audit.py`: `build_content_audit_extra()` enriquece `extra_data` com `entity_scope='pedagogical_content'`, autoria, `change_kind`, `previous_content/new_content/diff_summary`, `change_note`.

### Códigos HTTP institucionais
- `409 CONTENT_ENTRY_DUPLICATE` (UNIQUE composto)
- `409 CONTENT_VERSION_CONFLICT` (optimistic locking)
- `422 OVERWRITE_REQUIRES_NOTE`

### Índices (`startup/indexes.py`)
- UNIQUE composto: `{class_id, component_id, teacher_id, date, aula_numero}` com `partialFilterExpression={deleted: false}` → permite soft-delete + recreate na mesma chave lógica.
- Operacionais: `{class_id, date, deleted}`, `{teacher_id, date DESC}`, `{status, updated_at DESC}`.

### Testes (7/7 verdes)
`/app/backend/tests/test_content_entries_v1.py`:
- CRUD happy path
- Optimistic lock: 409 com stale version, 422 sem nota, 200 com nota
- UNIQUE composto bloqueia duplicidade
- Soft delete permite recreate na mesma chave lógica
- Audit log preserva `previous_content` + `diff_summary` em sobrescritas e deletes

**Regressão completa Rodadas 1+2**: 13/13 verdes (`test_attendance_audit_v1.py` + `test_content_entries_v1.py`).

### Status: ✅ COMPLETO

### Próxima — Rodada 3 (Fase 6): workflow `draft → published → corrected`
- Endpoint `POST /content-entries/{id}/publish` (transita draft → published; trava conteúdo)
- Endpoint `POST /content-entries/{id}/correct` (de published → corrected, requer change_note + cria nova versão preservando `corrected_from_version`)
- Status no audit log (`change_kind='content_published'`, `'content_corrected'`)


---

## [21/05/2026] Rodada 3 — Fase 6 (Workflow Institucional draft/published/corrected)

### Estados implementados
- **draft** — editável livremente via PUT.
- **published** — congelado; PUT retorna **409 `REQUIRES_CORRECT_FLOW`**; só evolui via `/correct`. Snapshot SHA256 imutável em `published_snapshot_hash`.
- **corrected** — registrado com `corrected_from_version` apontando para a versão anterior; pode receber novas correções (preservando linhagem).

### Endpoints novos
1. **`POST /api/content-entries/{id}/publish`**:
   - Aceita `expected_version` (optimistic locking).
   - Bloqueia status ≠ draft (`409 PUBLISH_REQUIRES_DRAFT`).
   - Bloqueia content vazio (`422 EMPTY_CONTENT`).
   - Computa `published_snapshot_hash` (SHA256 do payload pedagógico: class/course/component/teacher/date/aula/content/methodology/observations) — base para PDF imutável + verificação futura.
   - Audit `change_kind='content_published'`.
2. **`POST /api/content-entries/{id}/correct`**:
   - Status atual deve ser `published` ou `corrected` (`409 CORRECT_REQUIRES_PUBLISHED`).
   - `change_note` obrigatório.
   - Pelo menos 1 campo a corrigir (`422 EMPTY_CORRECTION`).
   - Sucesso → version+=1, status=corrected, `corrected_from_version`=versão anterior.
   - Audit `change_kind='content_corrected'` com `previous_content`/`new_content`/`diff_summary`.

### Refator PUT
- PUT em status ≠ draft → 409 `REQUIRES_CORRECT_FLOW` (separação semântica: editar livre vs corrigir institucionalmente).

### Helper novo
- `services/content_audit.py::compute_snapshot_hash(entry)` — base para Fase 5 (PDF) e Fase 8 (assinatura/QR).

### Testes (10/10 verdes)
`/app/backend/tests/test_content_workflow_v1.py`:
- publish happy path com hash
- publish from already-published → 409
- PUT on published → 409 REQUIRES_CORRECT_FLOW
- correct from draft → 409
- correct preserves corrected_from_version
- re-correct atualiza corrected_from_version
- correct sem campos → 422
- correct sem change_note → 422
- correct com version stale → 409

### Regressão completa (Rodadas 1+2+3): 23/23 verdes ✅
**Suíte idempotente**: roda 2x seguidas sem reset de DB. Fixtures autouse cleanup em `_RUN_TAG` (uuid por execução) + `_clean_test_data` (limpa range 2026-12-XX).

### Status: ✅ COMPLETO — Núcleo do Diário fechado

```
frequência (Fase 1) → conteúdo (Fase 2) → concorrência → publicação/versionamento (Fase 6)
```

### Próximo bloqueio absoluto: Fase 4a — popular grade horária
- `teacher_assignments` = 0 docs / `class_schedules.schedule_slots` = []
- Sem isso: calendário (Fase 4), PDF multi-autoria (Fase 5), painel de completude → indefinidos.


---

## [21/05/2026] Rodada 4 — Fase 4a (Motor Temporal Institucional)

### Coleção `teacher_class_assignments`
Modelagem RICA: separa "grade da turma" (`class_schedules`) de "responsabilidade institucional" (`teacher_class_assignments`):

```json
{
  "id": "uuid", "teacher_id": "...", "teacher_name": "...",
  "class_id": "...", "class_name": "...", "school_id": "...",
  "component_id": "...", "shift": "morning|afternoon|evening|full|integral",
  "weekly_slots": [
    {"weekday": 1, "aula_numero": 1, "start_time": "07:00", "end_time": "07:50"}
  ],
  "valid_from": "YYYY-MM-DD", "valid_until": "YYYY-MM-DD|null",
  "is_substitute": false, "source": "manual|import|seed",
  "deleted": false, "created_at/by", "updated_at/by"
}
```

### 6 endpoints (`routers/teacher_class_assignments.py`)
- `POST /api/teacher-class-assignments` — cria com validações: weekly_slots>=1, end_time>start_time, valid_until>=valid_from, shift válido, source válido.
- `GET /api/teacher-class-assignments` — filtros: class_id, teacher_id, component_id, school_id, **active_on** (YYYY-MM-DD para vigência temporal), is_substitute, include_deleted.
- `GET /api/teacher-class-assignments/{id}` — detalhe.
- `PUT /api/teacher-class-assignments/{id}` — patch parcial; valida valid_until>=valid_from.
- `DELETE /api/teacher-class-assignments/{id}` — soft delete com change_note obrigatório.
- **`GET /api/teacher-class-assignments/conflicts?teacher_id=&on_date=`** — detector de choque de horário (mesmo professor, slots sobrepostos em períodos vigentes simultaneamente). 2 tipos: `same_aula` e `time_overlap`.

### Algoritmo de conflito
- 2 períodos se sobrepõem se `max(start) <= min(end)` (com `null` = +∞).
- 2 slots colidem se mesmo weekday + (mesma aula_numero OU janelas de horário se interceptam).
- NÃO bloqueia criação — fornece visibilidade para a SEMED revisar.

### Auditoria
- `change_kind`: `assignment_created`, `assignment_updated`, `assignment_deleted`.
- `extra_data` carrega teacher_id, class_id, component_id, weekly_slots_count, validade, source, change_note (delete).

### 5 índices (`startup/indexes.py`)
- UNIQUE `id`.
- `{teacher_id, valid_from, valid_until}` — busca operacional.
- `{class_id, component_id, deleted}` — calendário.
- `{teacher_id, weekly_slots.weekday, weekly_slots.aula_numero, valid_until}` — conflito.
- `{school_id, valid_from, valid_until, deleted}` — escola.

### Seed sintético institucional
`/app/backend/scripts/seed_teacher_class_assignments.py`:
- 12 turmas × 3 alocações = **36 assignments criados** (regente cobre Seg-Qui 1ª/2ª aulas; Arte na Sex; Ed. Física Qua).
- Imita realidade multi-professor de anos iniciais.
- `source='seed'`, idempotente, `--undo` para limpeza.

### Testes (11/11 verdes)
`/app/backend/tests/test_teacher_class_assignments.py`:
- CRUD básico + validações (end_time, valid_until, shift, slots vazios).
- Filtro temporal `active_on` (inclui/exclui por vigência).
- Update extends validity + is_substitute.
- Soft delete (default list omite, include_deleted recupera).
- Detector de conflito: `same_aula`, `time_overlap`, períodos disjuntos NÃO geram conflito.

### Regressão completa do Diário (Rodadas 1+2+3+4a): **34/34 verdes** ✅

### Status: ✅ COMPLETO — Núcleo + Motor Temporal fechados

### Próximas (núcleo do Diário está pronto)
- **Fase 4** — Calendário visual (engine de completude: cinza/verde para frequência; cinza/azul/verde/amarelo para conteúdo cruzando `weekly_slots` × `content_entries` × `attendance`).
- **Fase 5** — PDF dinâmico multi-autoria por bloco, com snapshot_hash imutável.
- **Fase 7** — Validation flow (`validated_by` em attendance — coordenação/secretaria).
- **Fase 8** — QR de verificação institucional via `published_snapshot_hash`.
- **Fase 9** — Relatórios consolidados (Por turma+data: agrupa frequência + conteúdo por componente/professor).
- **Frontend** — UI completa do Diário multi-professor (próximo grande passo de UX após validação backend).

### Camadas pendentes da estratégia "FAÇA OS DOIS"
- ✅ Camada 1: Modelagem REAL primeiro — pronta.
- ✅ Camada 2: Seed sintético operacional — pronto (36 docs).
- ⏳ Camada 3: Cadastro administrativo gradual (UI admin) — vira Fase 4a-frontend, depois desta rodada.


---

## [21/05/2026] Rodada 5 — Fase 4 (Calendário operacional)

### Endpoint agregador
**`GET /api/calendar/diary-state/{class_id}?from=YYYY-MM-DD&to=YYYY-MM-DD`** (`routers/calendar_diary_state.py`).

Fonte única da verdade para calendário, futura UI, PDF e relatórios.

### Pipeline híbrido (NÃO $facet puro)
1. Busca `teacher_class_assignments` vigentes (overlapping the range).
2. Em Python expande `weekly_slots[]` para cada (data, weekday) — apenas dias onde a validade temporal permite.
3. Busca `attendance` + `content_entries` com `$in` em dates_in_range.
4. Match: attendance por (date, aula_numero) com fallback para attendance única do dia (anos iniciais); content por (date, component_id, aula_numero, teacher_id).
5. Consolida estado SEMÂNTICO por entry, por dia e summary global. **Nunca persiste cor** — UI decide paleta.

### Status semânticos
- **`attendance_status`**: `missing | draft | completed | validated`
- **`content_status`**: `missing | draft | published | corrected`
- **Agregado por dia**: `empty | partial | complete | corrected | inconsistent` (último captura evidência fora de slot esperado).

### Limites e validações
- Range máximo 92 dias (defesa contra varredura).
- `from`/`to` em formato YYYY-MM-DD, `to >= from`.
- 400 em formato inválido, range invertido ou range excessivo.

### Response shape
```json
{
  "class_id": "...", "class_name": "...", "school_id": "...",
  "from": "...", "to": "...", "range_days": N,
  "summary": {
    "expected_slots": N,
    "attendance_completed": N, "attendance_validated": N,
    "content_published": N, "content_corrected": N, "content_drafts": N,
    "orphan_attendance_dates": ["..."], "orphan_content_dates": ["..."]
  },
  "days": [{
    "date": "YYYY-MM-DD", "weekday": 1-7, "status": "...",
    "expected_slots": N, "has_orphan_evidence": bool,
    "entries": [{ component_id, component_name, aula_numero,
                  teacher_id, teacher_name, assignment_id,
                  attendance_status, content_status,
                  expected_by_schedule: true, slot_start, slot_end }]
  }]
}
```

### Testes (9/9 verdes)
`/app/backend/tests/test_calendar_diary_state.py`:
- Validações 400 (formato data, range invertido, range > 92 dias)
- 5 status semânticos (empty / partial / complete / corrected / inconsistent)
- Summary global cumulativo

### Regressão Diário completa (Rodadas 1+2+3+4a+4): **43/43 verdes** ✅

### Status: ✅ COMPLETO — Calendário operacional pronto para UI

### Próximas
- **Fase 5** — PDF dinâmico multi-autoria por bloco (consome o mesmo endpoint /diary-state; assinaturas reais via teacher_id; usa `published_snapshot_hash` para imutabilidade).
- **academic_calendar** (campo derivado preparado: `expected_by_schedule:true` — futuro `expected_by_calendar` poderá subtrair feriados/recessos).
- **Frontend** — UI calendário consumindo este endpoint.
- **Fase 7/8/9** — Validation flow / QR de verificação / Relatórios consolidados.

---

## [21/05/2026] Rodada 5.5 — Correção semântica `not_expected`

### Mudança conceitual obrigatória
O calendário diferencia **"não deveria existir lançamento"** de **"deveria existir mas não veio"**. Sem isso, dashboards futuros alertariam fins de semana como "atraso" — falso positivo institucional.

### Implementação
- `_classify_day()` em `calendar_diary_state.py`:
  - **`not_expected`** — dia sem slots esperados (sem assignment vigente para o weekday) E sem evidência órfã.
  - **`empty`** — havia slots esperados, zero evidência. Pendência real.
  - Demais estados inalterados (`partial`, `complete`, `corrected`, `inconsistent`).
- `summary.day_status_counts` — contagem por status agregado. Permite dashboards executivos sem recálculo client-side.
- Invariante UX: `not_expected` deve ser visualmente quase invisível na futura UI (peso mínimo na hierarquia visual). Documentado para a UI calendário (próxima rodada).

### Testes (10/10 verdes)
- Novo `test_not_expected_for_weekend` — sábado/domingo confirmam `not_expected` e `day_status_counts.not_expected==2`.
- `test_empty_when_no_evidence` ajustado: só assert `empty` quando havia slots esperados.

### Regressão (Rodadas 1+2+3+4a+4+5.5): **44/44 verdes** ✅

### Status: ✅ COMPLETO — Semântica corrigida antes da UI

### Próxima — UI mínima operacional do Calendário
Princípios já definidos:
- **Frontend NÃO interpreta estados** — apenas representa.
- **Hierarquia visual estrita**: validated > corrected > inconsistent > partial > empty >> not_expected (último quase invisível).
- **UI responde 5 perguntas**: O que falta? Quem está pendente? O que está inconsistente? O que foi corrigido? O que está validado?
- **Operacional, não bonita** — primeira UI sem polish/animação, foco em validação semântica em dados vivos.



---

## [Fev/2026] Bug Fix — Busca de alunos em "Controle de Vacinas"

### Sintoma
Usuário relatou: ao digitar "rebeca barroso" no campo de busca por nome em
`/vacinas`, a lista mostrava alunos não relacionados (ex.: começando com "A"),
em vez de filtrar pelo termo digitado.

### Causa raiz
`/app/frontend/src/pages/VaccineDashboard.js`, função `searchStudents`:
o `useCallback` capturava `searchTerm` (state do componente) via closure e
estava memoizado por `[allStudents]`. Como `searchTerm` valia `""` no momento
em que `allStudents` carregou, o filtro chamava `normalizeForSearch("").includes("")`
→ sempre `true` → retornava TODOS os alunos, e o `.slice(0, 10)` mostrava os
10 primeiros (alfabeticamente, começando com "A").

### Fix
Substituído o uso de `searchTerm` (state) por `term` (parâmetro recebido),
que carrega o valor atual do debounce. Variável `termLower` não usada removida.

### Validação
- Screenshot tool: busca "Maria" → 2 resultados corretos; "rebeca" → "Nenhum
  aluno encontrado." (correto); "xyzabcnotfound" → nenhum resultado (não
  retorna mais alunos errados).

### Status: ✅ RESOLVIDO


---
## [Jun/2026] UI: Reconstrução de Histórico Pedagógico (P1 concluída)
- Nova página `/app/frontend/src/pages/HistoryReconstruction.jsx` (rota `/admin/reconstrucao-historico`, super_admin) consumindo `/api/admin/history-reconstruction` (dry-run -> execute -> recibo PDF).
- Fluxo: seleção de escopo (aluno/turma/escola) + escola/turma/aluno + ano letivo opcional; simulação (dry-run, não altera dados); modal de confirmação com justificativa (min 10) e frase "CONFIRMO A RECONSTRUCAO"; execução idempotente e download de recibo verificável (QR/token).
- Serviço `historyReconstructionAPI` em `services/api.js`; item de menu `nav-history-reconstruction-button` no grupo Gestão Institucional do Dashboard.
- Testado (iteration_106): backend 100% (dry-run + idempotência + 403 RBAC); frontend E2E (login -> menu -> dry-run escola/aluno -> validações do modal). Bug corrigido: studentsAPI.getAll retorna dict paginado (extração defensiva aplicada).
- Status: PENDENTE HOMOLOGAÇÃO DO USUÁRIO.


---
## [Jun/2026] FIX: Freeze GRANULAR por bimestre de notas/conceitos migrados (movimentação de aluno)
- Bug: na turma de DESTINO o controle temporal não estava por bimestre — a nota migrada (1º bim) e os demais bimestres eram tratados de forma errada (doc migrado inteiro era bloqueado para o professor, impedindo lançar bimestres pós-ação).
- Regra implementada: na turma de destino, apenas os bimestres MIGRADOS da origem ficam SOMENTE LEITURA para professor/coordenador; os bimestres lançados APÓS a data da ação (remanejo/transferência/progressão/reclassificação) ficam EDITÁVEIS. Papéis administrativos (admin/secretario/gerente/super_admin) editam qualquer bimestre.
- Backend `routers/grades.py`: helpers `_frozen_fields_of_migrated_grade`, `_migrated_bimesters`, `_strip_frozen_grade_fields`; aplicados em POST/PUT/POST batch; GET /by-class agora expõe `student.migrated_bimesters`.
- Frontend `Grades.js` (canEditStudentGrade) + `GradesTable.jsx` (tooltip) usam `migrated_bimesters` para bloquear só as células migradas.
- Cobre NOTAS e CONCEITOS (mesma coleção grades). Testado (iteration_107): backend 6/6 + regressão; contrato validado em DB real (migrated_bimesters=[1]).


---
## [Jun/2026] FEATURE: Múltiplos professores nos PDFs (Educação Infantil e Fundamental - Anos Iniciais)
- Regra: exclusivamente nesses dois níveis, quando a TURMA tem mais de um professor vinculado (distinto), os PDFs de Notas, Frequência e Objetos de Conhecimento passam a exibir "Professores(as): Nome1, Nome2" no cabeçalho/infos E ganham UMA linha extra de assinatura. Turmas com um único professor mantêm o comportamento atual.
- Novo serviço `services/class_teachers.py` (get_class_teacher_names / get_multi_teacher_names_for_pdf) — lê teacher_assignments (status ativo) + staff (nome/full_name), com fallback de ano letivo.
- Novo helper `pdf/utils.build_signature_table` (distribui rótulos de assinatura em 2 colunas, permite linha extra).
- Geradores `pdf/notas.py`, `pdf/frequencia.py`, `pdf/objetos.py` aceitam `teacher_names` e renderizam nomes + assinatura extra; endpoints `grades.py /pdf`, `attendance_ext.py` (frequência) e `learning_objects.py` buscam e repassam os nomes.
- Verificado: extração de texto dos 3 PDFs (nomes + 2 assinaturas) e E2E HTTP real do PDF de Notas (200, application/pdf, nomes presentes). Seed de teste removido.


---
## [Jun/2026] FEATURE: Painel de Análise dos ANOS FINAIS para o Plano Municipal de Educação (PME)
- Duas páginas novas (acesso: super_admin, admin/admin_teste, gerente, SEMED; escopo município/mantenedora com filtros de escola/zona/ano):
  - `/pme/anos-finais` (PmeAnosFinais.jsx): painel com KPIs + gráficos recharts (matrículas por escola, cor/raça, rendimento geral e por série, distorção idade-série, NIS), "Descrição resumida" automática e exportação PDF (html2canvas+jsPDF) e Excel (XLSX). Combina dados calculados do SIGESC com os indicadores externos informados.
  - `/pme/anos-finais/indicadores` (PmeExternalIndicators.jsx): formulário por ano letivo para IDEB/SAEB, evolução histórica, 

---
## [Jun/2026] FEATURE: Painel de Análise dos ANOS FINAIS para o Plano Municipal de Educação (PME)
- Duas páginas novas (acesso: super_admin, admin/admin_teste, gerente, SEMED; escopo município/mantenedora com filtros de escola/zona/ano):
  - /pme/anos-finais (PmeAnosFinais.jsx): painel com KPIs + graficos recharts (matriculas por escola, cor/raca, rendimento geral e por serie, distorcao idade-serie, NIS), "Descricao resumida" automatica e exportacao PDF (html2canvas+jsPDF) e Excel (XLSX). Combina dados calculados do SIGESC com indicadores externos informados.
  - /pme/anos-finais/indicadores (PmeExternalIndicators.jsx): formulario por ano letivo para IDEB/SAEB, evolucao historica, % populacao IBGE, descritores BNCC, infraestrutura, transporte e politicas docentes.
- Backend routers/pme_anos_finais.py: GET /analytics (classes fundamental_anos_finais + enrollments + students + teacher_assignments/staff: escolas urbano/rural, matriculas, multisseriadas, % deficiencia, cor/raca, rendimento por serie/zona/raca via status de matricula, distorcao idade-serie via birth_date, evasao/abandono, socioeconomico via NIS, perfil docente) e GET/PUT /external-indicators (colecao pme_external_indicators, chave mantenedora_id+academic_year, upsert idempotente + auditoria). RBAC uniforme; PUT exige X-CSRF-Token.
- Registrado em server.py; menu nav-pme-anos-finais-button; servico pmeAnosFinaisAPI em api.js; rotas em App.js.
- Testado (iteration_108): backend 11/11 pytest; frontend 100% (nav, painel com 26 graficos, exports XLSX/PDF, salvar+persistir indicadores externos, RBAC professor 403 front+back). Warning cosmetico de input null corrigido.
- NOTA: motivos detalhados de Busca Ativa permanecem no modulo proprio; reprovacao depende de processamento de fim de ano (atualmente derivada de status). Metricas indisponiveis no SIGESC ficam na Pagina 2 (manual).


---
## [Jun/2026] AJUSTE PME: acesso SEMED ao painel + restricao de edicao dos Indicadores Externos
- Botao atalho "Anos Finais - Analise PME" disponivel no dashboard para todos os perfis SEMED (semed/semed1/semed2/semed3) alem de Super Admin/Admin/Gerente.
- Inserir/editar "Indicadores Externos (PME)" agora e permitido APENAS a Super Administrador, Administrador e Gerente. SEMED apenas visualiza o painel.
- Backend: PUT /api/pme/anos-finais/external-indicators restrito por EDIT_EXTERNAL_ROLES=['super_admin','admin','admin_teste','gerente'] (403 para SEMED); GET analytics/external seguem liberados para SEMED.
- Frontend: rota /pme/anos-finais/indicadores restrita aos perfis de edicao; botao "Indicadores Externos" e link "Informar agora" ocultos para SEMED (isAdmin).
- Verificado E2E: SEMED GET analytics/external=200, PUT=403; admin PUT=200.


---
## [Jun/2026] FIX: Cor/Raca no Painel PME mostrava tudo como "Nao declarado"
- Causa: a analytics do PME lia o campo legado 'cor_raca' (vazio); o dado real esta em 'color_race' (mesmo campo usado por GET /students -> race_counts).
- Fix em routers/pme_anos_finais.py: helper _race(stu) = color_race or cor_raca or 'nao_informada', aplicado na distribuicao de cor/raca e no rendimento por cor/raca; projecao inclui color_race. Frontend COR_RACA_LABEL passou a mapear 'nao_informada'.
- Verificado (iteration_109): backend 14/14 (3 testes de regressao), frontend exibe Branca/Parda/Preta corretamente; consistencia cross-endpoint com /api/students confirmada.
