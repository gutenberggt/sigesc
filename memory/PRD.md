# SIGESC - Product Requirements Document

## Original Problem Statement
Sistema Integrado de Gestão Escolar multi-tenant (SaaS) para prefeituras, com isolamento de dados entre mantenedoras, gestão de escolas, turmas, alunos, servidores e folha de pagamento.

## User's preferred language: Portuguese

## Multi-Tenancy Architecture
- Collection `mantenedoras` (plural) é a fonte definitiva de dados de tenants
- Collection legacy `mantenedora` (singular) foi removida
- Row-Level Security via `tenant_scope.py` (`apply_tenant_filter`)
- Super_admin tem acesso cross-tenant e ignora RLS quando sem header `X-Mantenedora-Id`
- Frontend: `TenantSwitcher` + `TenantSyncBoundary` permitem troca fluída sem reload

## Implemented Features (histórico)

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

## Current Backlog

### P1
- Regras de cálculo de carga horária prevista na folha de pagamento (aguarda regras de negócio do usuário)

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
