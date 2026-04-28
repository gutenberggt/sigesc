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
