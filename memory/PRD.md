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
