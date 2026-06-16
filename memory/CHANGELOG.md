# CHANGELOG — SIGESC

## 2026-06 — Completude divergente: lista (93%) × Editar Aluno (50%) (P0)

- **Causa raiz:** a coluna "Completude" da lista usava o **inteiro calculado no
  backend** (`row.completeness`), enquanto o modal "Editar Aluno(a)" recalcula no
  cliente (`registrationCompleteness.js`). Em produção, a resposta da listagem vinha
  de versão antiga/cache do backend (todos 93%), divergindo do modal (50%, correto —
  a aluna realmente está sem 7 campos). Além disso, o backend **removia** os campos-
  fonte da completude do payload da lista, impedindo o cliente de recalcular.
- **Correção (blinda os dois lados para nunca divergir):**
  - `routers/students.py` (`list_students`): em vez de remover, agora **inclui todos
    os 14 campos-fonte** da completude (null quando vazios) no payload.
  - `pages/StudentsComplete.js`: a coluna "Completude" passa a **recalcular no cliente
    com o MESMO util do modal** (`computeCompleteness`), com fallback para o valor do
    backend apenas se os campos não vierem (resposta cacheada antiga).
- **Resultado:** lista e "Editar Aluno(a)" usam o mesmo cálculo sobre os mesmos dados —
  sempre batem, independente de versão/cache do backend.
- **Testes:** `tests/test_students_completeness.py::test_list_includes_completeness_source_fields_for_client_recompute` (valida que o payload traz os campos e que o recálculo client-side == backend). Suite: 12/12 PASS.



- **O quê:** ferramenta de reparo em lote que copia `students.student_series` →
  `enrollments.student_series` para matrículas ATIVAS sem série cujo aluno já tem
  série no cadastro. Resolve em massa os PDFs/diários por etapa sem depender do
  fallback em tempo de leitura.
- **Backend (`routers/students.py`):**
  - `GET /api/students/series-sync/audit` — preview (total + amostra com nome,
    turma e série-alvo). Read-only, tenant/escola-aware.
  - `POST /api/students/series-sync/repair` — aplica a sincronização. Idempotente
    (filtro `student_series` vazio no update), auditado, NÃO toca alunos sem série
    no cadastro.
- **Frontend (`EnrollmentAudit.jsx` + `services/api.js`):** painel "Auditoria de
  Matrículas" (`/admin/auditoria-matriculas`) ganhou seção "Matrículas sem série
  (corrigíveis pelo cadastro)" + botão "Sincronizar séries (N)".
- **Verificação:** curl e2e (audit=2 candidatos, repair fixou 2, rerun=0 idempotente)
  + `tests/test_multigrade_series_pdf.py::test_series_sync_repair_copies_record_to_enrollment` (PASS). Arquivo: 5/5 PASS.



- **Causa raiz:** `routers/students.py` (`list_students`, ~linha 1064) **sobrescrevia**
  `student['student_series']` com o valor da matrícula ativa — que muitas vezes é
  `None` em turmas multisseriadas. Assim, mesmo com a série salva no cadastro
  (e selecionada em "Editar Aluno(a)"), a coluna "ANO" aparecia vazia ("-") e a série
  não refletia na tela de notas.
- **Correção:** fallback — `enrollment_series_map.get(id) or student.get('student_series')`.
  Agora a listagem usa a série da matrícula e, se ela estiver vazia, a série do
  cadastro do aluno. Consistente com `grades/by-class` e com o PDF de notas.
- **Teste:** `tests/test_multigrade_series_pdf.py::test_students_list_ano_column_fallback_to_record` (PASS). Suite do arquivo: 4/4 PASS.

## 2026-06 — Turmas multisseriadas: alunos sumindo dos PDFs/telas de notas (P0)


- **Causa raiz (provada com os 3 PDFs enviados):** turma "Maternal I e II" tem 14
  matriculados, mas os PDFs por etapa listavam só 3 (Maternal I) + 4 (Maternal II) = 7.
  Os 7 ausentes estavam **sem `student_series`** (ou com case/espaços divergentes). O
  endpoint de PDF (`grades.py` → `generate_grades_pdf`) filtrava por igualdade EXATA de
  `enrollments.student_series`, descartando-os silenciosamente.
- **Bug secundário:** em "Editar Aluno(a)", `PUT /api/students/{id}` só propagava a série
  para a matrícula quando `academic_year == ano_atual` — fragilizando a correção.
- **Correções:**
  - `routers/students.py` (`update_student`): propagação de `student_series` agora usa
    `update_many` na(s) matrícula(s) **ativa(s)** do aluno, sem travar por ano.
  - `routers/grades.py` (`generate_grades_pdf`): filtro de série agora **normaliza**
    (case/espaços) e faz **fallback** para `students.student_series` quando a matrícula
    estiver vazia → nenhum aluno classificado some do PDF.
  - `pages/StudentsComplete.js`: dropdown de Ano/Série em multisseriada com fallback
    para `grade_levels` (resiliência quando `series` não está populado), em edição e
    cadastro.
  - `pages/Grades.js`: filtro da tela de notas por série agora normalizado.
- **Fluxo final:** o gestor abre **Editar Aluno(a)**, escolhe a etapa (Etapa I/II) no
  dropdown e salva → série persiste no cadastro **e** na matrícula ativa → o aluno passa
  a aparecer no diário/PDF da etapa correta, fechando os 14.
- **Testes:** `tests/test_multigrade_series_pdf.py` (3 casos: by-class lista todos;
  edição propaga + inclui no PDF; fallback por cadastro + normalização de case). 3/3 PASS.


## 2026-06 — Diário AEE: causa raiz do "Erro ao salvar plano" + guard de UX

- **Causa raiz (provada com artefatos da API de produção):** `POST /api/aee/planos` →
  HTTP **400** = regra de duplicidade. Os alunos selecionados já possuíam Plano AEE
  ativo/rascunho no ano. Backend correto (criar para aluno SEM plano → 201). Não era
  CSRF (403), 422 (schema) nem multi-tenant. O frontend de produção (bundle antigo)
  mostrava o genérico "Erro ao salvar plano", escondendo o motivo.
- **Backend (`routers/aee.py`):** mensagem de duplicidade agora é acionável (nome do
  aluno, status, ano e orientação a editar o plano existente).
- **Frontend (`PlanoAEEModal.js` + `DiarioAEE.js`):** novo GUARD no dropdown "Aluno" do
  Novo Plano — alunos que já têm plano no ano aparecem **desabilitados** com selo
  "já possui plano" + nota orientando a editar pela aba Planos. Validado com dados reais
  (4/5 desabilitados; só o aluno sem plano selecionável).

## 2026-06 — FIX (regressão CSRF): "Erro ao salvar" no Diário AEE e outras telas

- **Causa raiz**: na migração do token CSRF para `localStorage` (fix multi-aba),
  4 telas continuaram lendo o CSRF do `sessionStorage` (que passou a ficar vazio).
  Resultado: POST/PUT iam SEM `X-CSRF-Token` → 403 → "Erro ao salvar plano AEE /
  atendimento" (e afins).
- **Corrigido** para ler `localStorage` primeiro (fallback sessionStorage/cookie) em:
  `DiarioAEE.js` (readCsrfToken), `ContentReview.jsx` (authHeaders — também corrigido
  token `sigesc_token`→`accessToken`), `UserProfile.js` e `OfflineContext.jsx` (CSRF
  enviado ao Service Worker no push).
- **Validado**: em aba nova (sessionStorage vazio), POST `/api/aee/atendimentos` agora
  leva o CSRF e retorna 404 (plano inexistente) em vez de 403. Frontend compila OK.

## 2026-06 — Apoio à Escrita: busca sob demanda para o PROFESSOR

- Novo endpoint `POST /api/admin/text-improvement/scan`: o professor (ou admin)
  dispara a análise de textos e recebe propostas de correção (formatação +
  ortografia, 100% determinístico, reutilizando `scripts/text_improvement.py`).
- **Escopo restrito ao usuário logado**: professor analisa SOMENTE seus próprios
  `learning_objects` (`recorded_by`); itens enfileirados ficam visíveis só a ele
  (`recorded_by_user_id`). Admin pode varrer todas as coleções da whitelist.
- Frontend (`TextImprovement.jsx`): página agora role-aware — botão "Buscar
  sugestões" para todos; ferramentas de admin (aprovação em massa / por regra e
  `rules-summary`) só aparecem para admin (evita 403 que quebrava a página do
  professor). Empty state orienta a clicar em "Buscar sugestões". `authHeaders`
  corrigido (lê `accessToken` + CSRF do localStorage).
- Testado: professor → scan (3 sugestões no próprio registro) → lista (scope=self)
  → aprovar (dono validado, aplicado na origem). Smoke de UI do professor OK.

## 2026-06 — SIE (Student Intelligence Engine) — FASE 0 (backend, baseado em regras)

- Novo motor de inteligência por aluno com **scores SEPARADOS**: Risco Acadêmico,
  Risco de Frequência e Risco Geral (0–100), em **4 níveis** (low/moderate/high/critical).
- 5 coleções multi-tenant: `sie_config`, `student_risk_scores`, `student_diagnostics`
  (estruturado), `student_snapshots` (série temporal), `student_alerts`.
- 5 motores puros e testáveis (`services/`): academic/attendance/overall/diagnostic/alert
  + orquestração `sie_service.py`. Pesos: acadêmico (notas 50/recup 20/repro 20/tend 10),
  frequência (presença anual 70/faltas recentes 30), geral (acad 55% + freq 45%).
- Tendência (improving/stable/falling) e **explicabilidade** (factors/breakdown) em todo score.
- Endpoints `/api/sie`: GET/PUT `/config`, GET `/students/{id}` (ao vivo), POST
  `/students/{id}/compute` (persiste), POST `/compute` (lote), GET `/risk`, `/alerts`,
  `/students/{id}/snapshots`. Multi-tenant via `tenant_scope.py`.
- Testes: 11 unitários (`tests/test_sie_engines.py`) + 9 de endpoint — 100% passando.
- Blueprint em `/app/memory/ROADMAP_SIE.md`. Próximo: FASE 1 (frontend MVP + cron + notificações).

## 2026-06 — Offline: confirmação acolhedora no momento do salvar (offline)

- Ao salvar **Notas** ou **Frequência** sem internet, a mensagem passou a ser, em
  linguagem clara e tranquilizadora: *"Notas/Frequência salva no aparelho ✓ — será
  enviada automaticamente quando a internet voltar."* (antes: "salvas localmente /
  serão sincronizadas").
- Reforça a confiança no exato momento da ação, complementando o Painel de
  Sincronização. Frontend compila; alteração é apenas de texto (sem lógica nova).
  Obs.: avisos de lint `react-hooks` em Grades.js/Attendance.js são pré-existentes,
  não relacionados a esta mudança.


## 2026-06 — Offline: Painel de Sincronização (visibilidade p/ o professor) + telemetria p/ SIGESC IA

**Objetivo:** acabar com a insegurança "será que perdi os lançamentos?". Tudo em
português claro (sem "sync"/jargão).

**Frontend — novo `components/PainelSincronizacao.jsx` (núcleo do módulo offline):**
- Status **Conectado / Sem internet**; resumo grande com cor (Tudo enviado ✓ /
  N aguardando envio / N não enviados / sem internet).
- **"Última vez enviado"** em linguagem natural (agora mesmo / há X min / hoje às
  HH:MM / ontem...), **persistida** (sobrevive a recarregar).
- **Detalhe por categoria**: Frequência, Notas (+ Planejamento/Alunos quando houver)
  com ✓ Tudo enviado / ⏳ aguardando / ⚠ não enviada.
- Botão **"Sincronizar Agora"** (mesmo com envio automático) + **"Ver detalhes"**
  (P2) listando falhas com mensagem amigável e **"Tentar enviar novamente"**.
- Renderizado no topo das telas de **Notas (Grades.js)** e **Frequência (Attendance.js)**;
  o `OfflineManagementPanel` (avançado) permanece abaixo.

**OfflineContext / dados:** `lastSyncTime` persistido (localStorage); novos
`pendingByCategory` e `failedSyncCount`; `retryFailedSync` e `getFailedItems`;
helpers `countPendingByCollection`/`getFailedSyncItems` no Dexie.

**Telemetria — modelo de dados preparado para o SIGESC IA:**
- Backend: coleção `sync_telemetry` + `POST /api/sync/telemetry` registrando
  `{ last_sync_at, pending_items, failed_items, last_error, sync_duration_ms }` +
  contexto `mantenedora_id/school_id/user_id/role/is_online/created_at`.
- Frontend envia telemetria (best-effort) ao fim de cada sincronização. Habilita,
  no futuro, monitorar escolas com internet ruim, professores muito offline e
  gargalos de envio (P3 — painel gerencial da SEMED ainda não construído).

**Validação:** lint limpo; frontend compila; `POST /telemetry` → 200 e doc gravado
com a forma correta; 6/6 testes de isolamento do sync verdes. ⚠️ Verificação visual
do painel pendente (preview em inatividade) → testar após redeploy do frontend.


## 2026-06 — Offline: fix do Background Sync (CSRF) + blindagem multi-tenant do sync

**Contexto:** verificação do funcionamento offline (PWA + SW + Dexie + push/pull).
Sistema maduro, mas com 2 falhas reais.

**P0-a — Background Sync quebrado (CSRF):**
- `public/sw.js` enviava `POST /api/sync/push` só com `Authorization: Bearer`, sem
  `X-CSRF-Token` → middleware CSRF respondia **403** e a sync automática em segundo
  plano falhava silenciosamente (cenário-chave: app fechado, internet volta depois).
- **Fix:** SW agora envia `X-CSRF-Token` (recebido do cliente via `GET_SYNC_INFO`
  ou, em fallback, derivado do claim `csrf` do próprio JWT) + **logging explícito**
  de 401/403/erro de rede (sem falha silenciosa). `OfflineContext` passou a incluir
  `csrf` (sessionStorage `sigesc_csrf_token`) na mensagem. Cache `v9→v10`,
  `version.json` `2.9.0`.

**P0-b — Isolamento multi-tenant no `routers/sync.py` (crítico):**
- Antes: create não carimbava `mantenedora_id` (confiava no cliente); update/delete
  por `{'id'}` sem escopo; pull/status sem tenant → risco de vazamento/alteração
  cruzada entre redes e contagens globais.
- **Fix (via `tenant_scope`):** create usa `resolve_tenant_id_for_create` (servidor
  é a autoridade; `clean_sync_data` agora descarta `mantenedora_id/created_by/updated_by`
  do cliente); update/delete usam `apply_tenant_filter({'id': ...})`; pull aplica
  `apply_tenant_filter` em TODAS as coleções; status conta por tenant ativo.
  `super_admin` continua cross-tenant (ou sob `X-Mantenedora-Id`).

**P1 — Testes (`tests/test_sync_tenant_isolation.py`, 6/6 verde):**
- CSRF: push sem CSRF → 403; com CSRF → 200.
- Multi-tenant: create carimba tenant do servidor (ignora tenant forjado pelo
  cliente); update/delete não tocam registro de outro tenant; pull não vaza.
- ⚠️ O e2e completo do SW (offline→fechar→reconectar→sync sozinho) exige browser;
  aqui validou-se o **contrato de servidor** que o habilita.

**Validação:** lint backend/JS limpo, `node --check sw.js` OK, frontend compila,
sync status/pull do super_admin sem regressão. Requer **redeploy backend+frontend**.


## 2026-06 — PDFs: cabeçalho com fundo branco + linha de contexto escola-turma-aluno

- **Fundo branco** no cabeçalho dos 3 PDFs (antes era faixa colorida): texto da
  mantenedora/município em escuro, título na cor de destaque e linha separadora.
- **Dashboard Analítico:** a linha de contexto agora combina, na mesma linha e
  separada por hífen, os filtros ativos — `Nome da escola - Nome da turma - Nome
  do aluno` — SEM o rótulo "Escola:" (o próprio nome já identifica). Montada em
  `buildHeaderInfo(true)` a partir de `selectedSchool/selectedClass/selectedStudent`.
- **Análise Detalhada do Score:** usa `contextLine` = nome da escola (sem rótulo).
- Lint JS limpo; `webpack compiled successfully`. ⚠️ Requer **redeploy do frontend**
  (verificação visual pendente — preview em inatividade).


## 2026-06 — Rodapé (gerado por + data/hora + paginação) nos 3 PDFs

- Frontend (`AnalyticsDashboard.jsx`): helper `drawPdfFooter(doc, generatedBy)`
  desenha em TODAS as páginas: "Gerado por {nome do usuário} em {data/hora}" à
  esquerda e "SIGESC · Página i de N" à direita, com faixa branca + linha separadora
  (legível mesmo sobre a imagem do dashboard). Nome vem de `user.full_name` (fallback
  e-mail), via `buildHeaderInfo().generatedBy`.
- Aplicado aos 3 PDFs: Dashboard completo, Ranking de Escolas (substituiu o rodapé
  antigo) e Análise Detalhada do Score.
- Lint JS limpo; `webpack compiled successfully`. ⚠️ Verificação visual pendente
  (preview em inatividade) → requer **redeploy do frontend**.


## 2026-06 — Cabeçalho institucional (brasão + município + escola) nos PDFs exportados

**Solicitação:** todos os PDFs do Dashboard Analítico devem trazer um cabeçalho
institucional com o brasão da mantenedora + nome do município; quando o relatório
for de uma escola específica, citar o nome da escola.

**Backend (`routers/mantenedora.py`):** novo `GET /api/mantenedora/brasao-base64`.
A URL do brasão fica em outro domínio SEM cabeçalho CORS (o `fetch` do browser
falharia), então o backend baixa a imagem (httpx), faz downscale com Pillow
(thumbnail 400px → de ~2,7MB para ~165KB) e devolve um data URL base64 mesma origem.

**Frontend (`AnalyticsDashboard.jsx`):**
- `useMantenedora()` + `useEffect` (na seção de hooks, antes de qualquer early-return)
  carrega o brasão em base64 e guarda em `logoDataUrl`.
- Helper `drawInstitutionalHeader(doc, {...})` desenha faixa com brasão + nome da
  mantenedora + "Município de X - UF" + título do documento; se `schoolName`, cita
  "Escola: ...". Retorna o Y onde o conteúdo começa.
- Aplicado aos 3 PDFs: **Dashboard completo** (cita escola se filtro de escola ativo),
  **Ranking de Escolas** (rede toda, sem escola) e **Análise Detalhada do Score**
  (sempre cita a escola). A planilha Excel do Dashboard também ganhou o contexto
  (mantenedora/município/escola) no topo do "Resumo".

**Validação:** endpoint testado via curl (retorna PNG base64 ~165KB). Lint JS/PY
limpo; `webpack compiled successfully`. Regras de Hooks respeitadas (sem React #310).
⚠️ Verificação visual do PDF NÃO feita: preview em modo inatividade. Requer
**redeploy do backend + frontend** (e acordar o preview p/ testar o download).


## 2026-06 — Fix: "Média por Componente Curricular" repetia componentes + escopo 3º–9º/EJA

**Sintoma:** o gráfico "Média por Componente Curricular" exibia o MESMO componente
várias vezes (ex.: Educação Física/Ensino Religioso repetidos).

**Causa raiz:** `GET /analytics/grades/by-subject` agrupava por `course_id`. Como
existem múltiplos documentos em `courses` com o mesmo nome (um por escola/série),
cada um virava uma barra → duplicação.

**Fix (backend `analytics.py::get_grades_by_subject`):**
- Passa a mesclar por NOME canônico do componente (normaliza acento/caixa) →
  cada componente aparece UMA única vez; a média é recomputada como soma÷contagem
  real entre todos os `course_id` daquele nome (não média de médias).
- Restringe às turmas elegíveis **3º ao 9º Ano e EJA** (exclui Ed. Infantil, 1º e
  2º Ano), mesma regra do `/students/performance`.
- Retorna ordenado por média **decrescente** (maior no topo). Removidos campos
  `course_id`/`abbreviation` do payload (frontend já gera a sigla a partir de
  `course_name`).

**Validação:** `tests/test_grades_by_subject_dedup.py` (3 testes — componente único,
média mesclada 7.0 ignorando 1º Ano, ordem desc com maior no topo) + regressão
`test_by_subject_usa_final_average` verde. Curl 2026: retorna cada componente 1×.
Requer **redeploy do backend**.


## 2026-06 — Dashboard Analítico: exportação PDF/Excel + fix do botão PDF (jspdf-autotable v5)

**1) Exportar Dashboard completo (cards + gráficos):**
- Frontend (`AnalyticsDashboard.jsx`): 2 botões no header — **Exportar PDF** e
  **Exportar Excel** (`data-testid` export-dashboard-pdf-btn / export-dashboard-excel-btn).
- PDF: captura a região de cards + gráficos via `html2canvas` (Tailwind v3, sem
  oklch) → `jsPDF` multipágina A4. Wrapper com `ref={dashboardCaptureRef}`.
- Excel: workbook com abas Resumo (KPIs), Frequência Mensal, Desempenho Bimestre,
  Média por Componente e Distribuição de Notas.
- Dependência declarada: `html2canvas@1.4.1` (`yarn add`).

**2) Ranking de Escolas (Score V2.1) — export em PDF além de Excel:**
- Novo `exportRankingToPDF()` (jsPDF paisagem + `autoTable`, 16 colunas, rodapé
  paginado). Botões "Excel" + "PDF" lado a lado (`export-ranking-pdf-btn`).

**3) Fix (bug) — botão PDF da "Análise Detalhada do Score V2.1" não funcionava:**
- **Causa raiz:** `jspdf-autotable@5` REMOVEU o método de protótipo
  `doc.autoTable(...)`; o código usava a API antiga → `doc.autoTable is not a
  function`. **Fix:** import funcional `import autoTable from 'jspdf-autotable'`
  e todas as chamadas migradas para `autoTable(doc, {...})`. `doc.lastAutoTable.finalY`
  mantido (válido na v5).

**Validação:** `webpack compiled successfully` + lint JS limpo. ⚠️ Verificação
visual de clique/download NÃO pôde ser feita: o proxy de **preview** estava em
modo de inatividade ("Preview Unavailable"). Testar após acordar o preview ou no
ambiente publicado. As mudanças exigem **redeploy do frontend**.


## 2026-06 — Dashboard Analítico: siglas de componentes, cores da distribuição e fix Frequência Mensal por escola

**1) Média por Componente Curricular — siglas oficiais + todos os componentes:**
- Frontend (`AnalyticsDashboard.jsx`): novo mapa `COMPONENT_ABBREVIATIONS` + helper
  `abbreviateComponent(course_name)` (normaliza acento/caixa). Siglas: L. PORT.,
  ARTE, ED. FÍS., L. ING., MAT., CIÊN., HIST., GEOG., ENS. REL., EST. AMAZ.,
  LIT. E RED., ED. AMB. CLI. (fallback p/ não mapeados).
- Removido o `slice(0,10)` → exibe TODOS os componentes; altura do gráfico dinâmica
  (`max(300, n×34)`); tooltip mostra o nome COMPLETO do componente.

**2) Distribuição de Notas — cores distintas por faixa:**
- Novo `DISTRIBUTION_COLORS` por `boundary`: 0-2.9 vermelho escuro, 3-4.9 laranja,
  5-5.9 amarelo, 6-6.9 verde-limão, 7-7.9 verde, 8-8.9 azul-claro, 9-10 índigo
  (antes 6+ eram todas verdes, indistinguíveis).

**3) Fix (bug) — Frequência Mensal "Sem dados" ao selecionar escola:**
- **Causa raiz:** `attendance` NÃO possui campo `school_id`; o endpoint
  `/analytics/attendance/monthly` filtrava `match_filter['school_id']=school_id`
  → resultado SEMPRE vazio quando uma escola era selecionada.
- **Fix (backend `analytics.py`):** resolve as turmas da escola e filtra por
  `class_id` (mesmo padrão do `/overview`). Pipeline migrado para o helper de
  split de `records[]` (combos `P|F`) e rate = P/total (J e F = ausência),
  alinhado ao restante do dashboard.
- **Validado via curl:** ano 2026 + `school_id` da Escola Multisseriada agora
  retorna Fev/Mar/Abr/Dez com taxas (antes vinha `[]`).

**Validação:** regressão `test_analytics_dashboard.py` + `test_teachers_performance_sla.py`
10/10 verde; lint JS/PY limpo.


## 2026-06 — Ajuste: coluna "Diários (60%)" = média ponderada de 3 SLAs (Desempenho dos Professores)

**Solicitação:** Na tabela "Desempenho dos Professores – Top 10" (Dashboard
Analítico), a coluna "Diários (60%)" deixa de ser só a cobertura de objetos de
conhecimento e passa a ser a MÉDIA PONDERADA de 3 SLAs (normalizada 0–100%):
- **SLA Frequência (peso 4):** lançamentos de frequência em até 3 dias / total
  (compara `attendance.created_at` vs `attendance.date`), nas turmas do professor.
- **SLA Conteúdo (peso 3):** objetos de conhecimento registrados / previstos
  (= lógica anterior da coluna).
- **SLA Notas (peso 3):** placeholder = 100% (workflow de prazo de notas ainda não existe).
- Fórmula: `Diários = (SLA_Freq×4 + SLA_Conteúdo×3 + SLA_Notas×3) / 10`.
- `score` final inalterado (60% Diários + 40% índice da média).

**Escopo isolado:** alteração EXCLUSIVA em `GET /api/analytics/teachers/performance`.
O "Ranking de Escolas – Score V2.1" NÃO foi tocado (confirmado pelo usuário).

**Entregue (backend `routers/analytics.py`, `get_teachers_performance`):**
- Pré-agregação de SLA Frequência por turma (pipeline `$dateFromString`/`$subtract`).
- Resposta agora expõe breakdown `sla_freq`, `sla_conteudo`, `sla_notas` além de
  `diario_pct`. Frontend já consome `diario_pct` (nome de campo inalterado → sem mudança de UI).

**Validação:** novo teste `tests/test_teachers_performance_sla.py` (4 testes, semeia
ano isolado 2099 → dias letivos fallback 200; valida SLA Freq 66.7, Conteúdo 10.0,
Notas 100, Diários 59.7). Regressão `test_analytics_dashboard.py` 6/6 verde
(Ranking V2.1 intacto).


## 2026-02 — UX: estado "Sem dados suficientes" no Dashboard Analítico

**Solicitação:** Exibir aviso de "Sem dados suficientes" nos cards/gráficos
quando não houver notas/frequência no período, em vez de mostrar 0 / gráfico em
branco (evita falsa impressão de bug quando um bimestre ainda não foi lançado).

**Entregue (frontend `AnalyticsDashboard.jsx`, somente UI):**
- Novo componente `EmptyChart` (ícone + mensagem + dica).
- Flags `hasGrades`, `hasAttendance`, `hasPeriodData`, `hasSubjectData`,
  `hasDistributionData`, `hasMonthlyData`.
- 5 cards (Frequência, Média Geral, Presença Média, Total de Faltas, Taxa de
  Aprovação) exibem "Sem dados suficientes" quando sem dados (data-testids
  freq-empty, media-geral-empty, presenca-empty, faltas-empty, aprovacao-empty).
- 4 gráficos (Frequência Mensal, Desempenho por Bimestre, Média por Componente,
  Distribuição de Notas) exibem `EmptyChart` no lugar do gráfico em branco.

**Validação:** Testing agent (iteration_92) — cenário 2026 (com dados): SEM
regressão; cenário 2025 (sem dados): estados vazios exibidos. Card "Média Geral"
(única peça faltante apontada) corrigido na sequência (mesmo padrão dos demais).


## 2026-02 — Correção crítica: Dashboard Analítico (10 itens) — schema real

**Problema:** Todos os cards/gráficos/rankings do Dashboard Analítico estavam
zerados/em branco e o ranking mostrava aprovação irreal (100%).

**Causa raiz:** `routers/analytics.py` agregava sobre um schema inexistente
(`grades.grade`, `attendance.status` no topo, `academic_year` como TEXTO). O
banco real usa: notas em **b1..b4 + final_average** (course_id, ano int) e
frequência em **records[]** com status **P/F/J** (combos `P|F`).

**Regras de negócio aplicadas (confirmadas pelo usuário):**
- Frequência = P / total de aulas (J e F = ausência; J exibida à parte).
- Total de Faltas = F + J (Justificadas detalhadas à parte).
- Média Geral / Média(60%) = `final_average` (já é a média dos bimestres lançados).
- Aprovação = por ALUNO: ≥ 5,0 em TODOS os componentes avaliados (base = alunos
  com nota lançada). Substitui a contagem por `status='aprovado'`.
- Desempenho por Bimestre = b1..b4 com notas não-lançadas contando como ZERO.

**Corrigidos 7 endpoints** (`analytics.py`): /overview, /grades/by-period,
/grades/by-subject, /distribution/grades, /schools/ranking, /students/performance,
/teachers/performance. Novo helper `_attendance_split_stages()` (unwind records[]
+ split de `|` + normaliza P/F/J).

**Validação:** Backend pytest 6/6 (`tests/test_analytics_dashboard.py`); frontend
E2E 100% (iteration_91) — cards >0, gráficos renderizando, ranking correto
(escolas sem notas = 0% aprovação, não 100%), Média(60%) preenchida.
OBS: tabela de Professores fica vazia no PREVIEW por não haver `teacher_assignments`
cadastrados (esperado); o cálculo de `media_notas` foi validado via alocação
temporária (retornou 10.0). Sem alterações de frontend.


## 2026-02 — Ajuste: cards de Completude contam apenas alunos ATIVOS

**Solicitação:** Nos cards de Completude (verde/amarelo/vermelho), as somas
devem considerar apenas alunos com status "Ativo".

**Entregue (backend `routers/students.py`, list_students):**
- `completeness_counts` agora é calculado sobre `active_filter`
  (`status='active'`), e não mais sobre todos os status.
- O filtro por faixa (`completeness_band`) na lista também passou a considerar
  apenas ativos, mantendo a consistência entre a contagem do card e a lista.
- Testes atualizados/adicionados em `tests/test_students_completeness.py`
  (soma == active_count; verificação com escola de status misto).

**Validação:** curl numa escola com 1 ativo + 1 transferido → soma das faixas = 1
(= active_count), total = 2. Pytest 6/6 OK. Sem alteração de frontend.


## 2026-02 — Feature: Somas por agrupamento nos "Indicadores da Rede" (Alunos)

**Solicitação:** Acrescentar somatórios na seção "Indicadores da Rede".

**Entregue (frontend `StudentsComplete.js`, somente exibição):**
- Helper `sumSeries(labels)` + consts de total (lê `series_counts`, chaves MAIÚSCULAS).
- Linha "Educação Infantil": 3 badges de soma destacados — `Educação Infantil`
  (Berçário/Maternal/Pré), `Anos Iniciais` (1º-5º Ano), `Anos Finais` (6º-9º Ano)
  (data-testids sum-educacao-infantil / sum-anos-iniciais / sum-anos-finais).
- Linha "Etapas (EJA) e Modalidades": badge `EJA` (soma 1ª-4ª Etapa) inserido
  ENTRE "4ª Etapa" e "Regular" (data-testid sum-eja).

**Validação:** Testing agent frontend 100% (5/5 — iteration_90). Somas conferem
com os badges individuais e backend series_counts.


## 2026-02 — Refactor (frontend): config central das categorias de conexão

**Motivo:** Centralizar rótulos/ícones/cores das categorias (antes fixos no
`OnlineUsers.js`), em par com o módulo central do backend.

**Entregue:**
- Novo `frontend/src/config/connectionCategories.js`: `CONNECTION_CATEGORIES`
  (array com key/label/icon/cores/testId). Editar rótulo, ícone ou cor de uma
  categoria agora é feito SOMENTE aqui. As `key` espelham `by_category` do backend.
- `OnlineUsers.js` consome o config (removida a array inline e os imports de
  ícones movidos para o config).

**Validação:** Lint OK; estrutura de renderização idêntica à validada na
iteration_89 (apenas a fonte da array mudou).


## 2026-02 — Refactor: mapeamento role→categoria de conexão centralizado

**Motivo:** Permitir adicionar novas roles (ex.: novas roles de Saúde) a uma
categoria sem editar a lógica do endpoint.

**Entregue:**
- Novo módulo `backend/utils/connection_categories.py`: `CONNECTION_CATEGORY_ROLES`
  (mapa categoria→roles), `categorize_role()` (case-insensitive, fallback
  "administrativas") e `empty_category_counts()`. Para incluir uma role basta
  editar o conjunto da categoria — único ponto de mudança.
- `routers/admin.py` (login-count) refatorado para usar o módulo. Resposta
  inalterada (`by_category`); soma continua == `successful`.
- Testes: `backend/tests/test_connection_categories.py` (4 testes).

**Validação:** Endpoint confere (soma == successful via curl); 8/8 pytest OK.


## 2026-02 — Feature: Subdivisão das "Conexões Registradas" por categoria (Usuários Online)

**Solicitação:** Manter o campo "Conexões Registradas" e adicionar 5 campos que
subdividem essas conexões por categoria de perfil.

**Categorias:** Professores (role professor), Alunos (aluno), Assistência Social
(ass_social/ass_social_2), Saúde (agente_vacinas + futuras roles de saúde),
Administrativas (todos os demais: admin, semed, secretario, etc.).

**Entregue:**
- Backend (`routers/admin.py`, GET /admin/online-users/login-count): resposta
  agora inclui `by_category` agrupando os logins bem-sucedidos por `user_role`
  via aggregation. A soma das 5 categorias == `successful`.
- Frontend (`OnlineUsers.js`): card "Conexões Registradas" mantido + nova seção
  "Conexões por categoria" (data-testid connections-by-category) com 5 cards
  (conn-cat-professores/alunos/assistencia/saude/administrativas).
- Testes: `backend/tests/test_online_users_login_count.py` (4 testes).

**Validação:** Testing agent E2E 100% (backend 4/4 + frontend — iteration_89).
Card antigo intacto; soma das categorias confere com o total.


## 2026-02 — Feature: Filtros por faixa de Completude na lista de Alunos

**Solicitação:** Na página Alunos(as), na linha do "Total: N registros / Gerar
PDF / Ações em Lote", adicionar 4 botões (Verde, Amarelo, Vermelho, Branco/Todos)
espelhando a coluna "Completude". Cada botão mostra a quantidade de alunos na
faixa e, ao clicar, filtra a lista; o branco ("Todos") limpa o filtro.

**Faixas:** Verde ≥80%, Amarelo 50-79%, Vermelho <50% (espelham completenessColor).

**Entregue:**
- Backend (`routers/students.py`, list_students): novo param `completeness_band`
  (green|yellow|red) que filtra a lista server-side; resposta agora inclui
  `completeness_counts` {green,yellow,red} calculado por aggregation sobre TODO
  o conjunto filtrado (não só a página). Helpers `_completeness_pct_stage()` e
  `_BAND_EXPR` espelham os 14 critérios de `_compute_student_completeness`.
- Frontend (`StudentsComplete.js`): estados `completenessCounts`/`completenessBand`,
  4 botões na linha do Total (data-testid completeness-filter-green/yellow/red/all),
  toggle ao reclicar a faixa ativa, reset de página ao trocar filtro.
- Testes: `backend/tests/test_students_completeness.py` (5 testes).

**Validação:** Testing agent E2E 100% (backend 5/5 + frontend — iteration_88).
Contagens batem com o total; filtros e toggle funcionam.


## 2026-02 — Feature: Painel in-app de Auditoria de Matrículas (read-only)

**Solicitação:** Transformar a fase de auditoria do script de saneamento num
painel in-app na secretaria, para acompanhar matrículas ausentes/duplicadas em
tempo real sem usar o shell.

**Entregue:**
- Backend: `GET /api/students/enrollment-audit` (em `routers/students.py`) —
  read-only, tenant/escola-aware. Retorna, por coleção (`students` e
  `enrollments`): total, vazios, grupos duplicados (+ owners) e amostra de
  alunos sem matrícula (limite 200); além de `owner_names` e o status do índice
  único `uq_enrollment_number`. Restrito a super_admin/admin/gerente/semed/secretario.
- Frontend: `pages/EnrollmentAudit.jsx` — rota `/admin/auditoria-matriculas`,
  card "Auditoria de Matrículas" no Dashboard (grupo "Gestão Escolar"). Mostra
  4 cards de estatística, banner do índice único (ATIVO/inativo) e tabelas de
  duplicatas + alunos sem matrícula. Botão "Atualizar" para refresh.
- Testes: `backend/tests/test_enrollment_audit.py` (10 testes, autossuficiente).

**Validação:** Testing agent E2E 100% (backend + frontend, iteration_87). Pytest
local 10/10 OK.


## 2026-02 — P1: Backfill + Deduplicação de Matrículas + Índice Único

**Solicitação:** Sanar passivo de matrículas AUSENTES (vazias) e DUPLICADAS.
Regra do usuário p/ duplicatas: manter a matrícula do aluno/registro MAIS ANTIGO
e gerar nova matrícula para os demais.

**Entregue:**
- `backend/scripts/backfill_dedup_enrollment.py` (novo): script standalone com
  3 fases (Dedup → Backfill → Índice único parcial). DRY-RUN por padrão; exige
  `--apply` para alterar e `--apply --create-index` para criar o índice.
  - Dedup mantém o doc mais antigo (menor `created_at`/`enrollment_date`) e
    regenera os demais via gerador atômico (`utils/enrollment.py`).
  - Backfill preenche vazios em `students` e `enrollments`.
  - Índice ÚNICO PARCIAL `uq_enrollment_number` (`partialFilterExpression:
    {enrollment_number: {$gt: ""}}`) — barra duplicatas mas permite vazios.
  - Contador atômico é "sememeado" via `$max` acima do maior sufixo do ano,
    evitando colisão com legado.
- `backend/tests/test_backfill_dedup_enrollment.py` (novo): regressão da lógica
  de ordenação (mais antigo) e geração única (3 testes, OK).

**Validação (banco de preview):** aplicado com sucesso → 0 vazios, 0 duplicatas
em ambas as coleções; índice bloqueia inserção duplicada e permite múltiplos
vazios. Backend saudável (200).

**Como rodar em PRODUÇÃO (após deploy):**
```
cd /app/backend
python3 scripts/backfill_dedup_enrollment.py                 # 1) dry-run (revisar plano)
python3 scripts/backfill_dedup_enrollment.py --apply --create-index   # 2) aplicar
```


## 2026-05-31 — Feature: Indicador de Completude do Cadastro

**Solicitação:** Indicador de "completude do cadastro" do aluno. Escolhas do usuário:
exibir em AMBOS (badge na lista + barra no formulário); conjunto AMPLIADO de campos;
estilo percentual com cor.

**Critérios (14, espelhados frontend/backend):** os 10 obrigatórios + Documento
(CPF/NIS/Certidão) + Telefone do Responsável + Turma + Matrícula. (Não há campos de
endereço no formulário, então não entraram no cálculo.)

**Implementação:**
- `frontend/src/utils/registrationCompleteness.js` (novo): `computeCompleteness(data)`
  → {percent, filled, total, missing}, `completenessColor(percent)` (verde ≥80,
  amarelo 50–79, vermelho <50), e `COMPLETENESS_CRITERIA`.
- `backend/routers/students.py`: `_compute_student_completeness(student)` (espelha o
  frontend); a listagem `GET /api/students` adiciona `completeness` (0–100) em cada
  item, projetando os campos extras só para o cálculo e removendo-os depois (payload leve).
- `frontend/src/pages/StudentsComplete.js`:
  - Coluna "Completude" na tabela inline (badge com mini-barra + % colorido,
    data-testid `completeness-badge-<id>`). Atualizados thead, tbody, skeleton e colSpan.
  - Barra de progresso no topo do formulário (data-testid `form-completeness-bar` /
    `form-completeness-percent`), com `useMemo`, contagem n/14, lista "Faltando: ..." e cor.
  - `components/Tabs.js` já controlável (da feature anterior).

**Testado:** testing_agent iteration_86 (barra do form 100% OK). Coluna da lista
corrigida (era código morto no array `columns`; migrada para o markup inline da tabela)
e validada visualmente: 20 badges, cores corretas (43% vermelho, 50% amarelo), %
batendo com o backend.

**AÇÃO PENDENTE DO USUÁRIO:** redeploy de **frontend E backend** (esta feature mexe
nos dois) no Coolify.

---

## 2026-05-31 — Feature: campos obrigatórios no cadastro de aluno + pop-up de alerta

**Solicitação:** Tornar campos obrigatórios no cadastro do aluno; se algum estiver
ausente ao salvar, abrir um pop-up de alerta (caixa centralizada com mensagem e
botão OK) e navegar até a aba do primeiro campo faltante.

**Campos obrigatórios:**
- Aba Identificação: Nome Completo, Data de Nascimento, Sexo, Nacionalidade,
  Cor/Raça, Comunidade Tradicional, Naturalidade (Cidade), Estado.
- Aba Responsáveis: Mãe (mother_name) e Responsável Legal (legal_guardian_type;
  se "Outro", o nome do responsável também é exigido).

**Implementação (frontend):**
- `getMissingRequiredFields()` + validação no `handleSubmit` que abre o pop-up
  (`setRequiredAlert`) e troca para a aba do 1º campo faltante (`setFormTabIndex`).
- Pop-up centralizado novo (data-testid `required-fields-modal`, itens
  `required-field-item-N`, botão `required-fields-modal-ok-btn`).
- `components/Tabs.js` tornado CONTROLÁVEL (props opcionais `activeIndex` +
  `onTabChange`, retrocompatível) para permitir a navegação programática de aba.
- Labels obrigatórios marcados com `*`. Adicionados data-testid `create-student-btn`
  e `save-student-btn`.
- **Fix importante:** o `<form>` recebeu `noValidate` — o input `full_name` tinha
  `required` HTML5 que disparava o tooltip nativo do browser e bloqueava o
  `handleSubmit`, impedindo o pop-up. Com `noValidate`, a validação customizada é a
  única fonte.

**Testado:** testing_agent iteration_85 — 100% (5/5 cenários). Pop-up dispara,
OK fecha, navegação de aba funciona, asteriscos presentes.

**AÇÃO PENDENTE DO USUÁRIO:** redeploy do **frontend** (Save to GitHub → Coolify
Redeploy do serviço frontend) para publicar esta feature.

---

## 2026-05-31 — Fix definitivo: "Série não reconhecida" nos Indicadores da Rede (P0)

**Sintoma (produção):** Escola Nivalda mostrava 314 alunos ativos, mas as séries
somavam só 47 (Berçário II 12, Maternal I 7, Maternal II 28) — 267 alunos "sumiam".
O backend os jogava em "SÉRIE NÃO RECONHECIDA: 267".

**Root cause:** No pipeline de agregação `series_pipeline` (routers/students.py),
o cálculo de `_grade_effective` usava:
`$cond[$and[$ne(ss, null), $ne(ss, "")] ? ss : class.grade_level]`.
Quando o campo `student_series` estava **AUSENTE** (não apenas null/""), a variável
`$$ss` virava "missing" e `$ne(missing, null)` resolve para **TRUE** no MongoDB →
o `$cond` mantinha o valor missing em vez de cair no fallback `classes.grade_level`
→ canonicalizava para None → "Série não reconhecida". (Os scripts de diagnóstico em
Python usavam `.get()/.strip()`, por isso reconheciam corretamente os 314.)

Dados de Nivalda confirmados: 267 com `student_series` ausente/null, cujas turmas
TÊM `grade_level` válido (Maternal II 129, Maternal I 98, Berçário II 40).

**Fix:** `vars.ss = $trim($ifNull($student_series, ""))`. O `$ifNull` coage
null E campo ausente para "", e `$trim` normaliza só-espaços. Assim cai no fallback
do `grade_level` corretamente. Mantém a prioridade do `student_series` quando
preenchido (multisseriadas).

Validado nos dados reais de produção (via pipeline standalone): Nivalda passa a
somar 314 (Berçário II 52, Maternal I 105, Maternal II 157), 0 não reconhecidas.

**Arquivos:**
- `routers/students.py` (~linha 609-628): pipeline `_grade_effective` corrigido.
- `tests/test_series_pipeline_fallback.py`: 4 testes de regressão (missing/null/
  vazio/espaços caem no fallback; student_series válido tem prioridade;
  reconciliação soma 100%). Todos passando.

**Scripts de diagnóstico criados em** `backend/scripts/` (standalone, sem deps do
projeto, rodam em qualquer container via base64):
- `diagnose_snr_standalone.py` — classifica causa-raiz por aluno (A/B/C/D/E).
- `series_breakdown_standalone.py` — detalhamento de séries (código novo) p/ comparar com a tela.
- `fix_grade_level_standalone.py` — preenche `classes.grade_level` vazio a partir do nome da turma (DRY-RUN por padrão).

**Diagnóstico de ambiente (produção = Coolify):** backend `uvicorn server:app`,
frontend nginx (PWA com service worker network-first), traefik. Código implantado
(students.py + serie_canonical.py) estava CORRETO/idêntico (md5 batendo) — o bug era
de LÓGICA no pipeline, não de deploy desatualizado.

**AÇÃO PENDENTE DO USUÁRIO:** redeploy do **backend** em produção (Save to GitHub →
Coolify Redeploy do serviço backend) para subir o fix. Frontend NÃO precisa redeploy.
Após o deploy, validar Nivalda = 314 no painel "Indicadores da Rede".
