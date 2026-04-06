# SIGESC - Sistema Integrado de Gestão Escolar

## Visão Geral
Sistema full-stack (React + FastAPI + MongoDB) para gestão escolar municipal.

## Arquitetura
- **Frontend**: React + TailwindCSS + Shadcn/UI
- **Backend**: FastAPI + Motor (MongoDB async)
- **Banco**: MongoDB
- **PDF**: ReportLab + PyPDF2

## Módulos Implementados

### Módulo Acadêmico (Completo)
- Cadastro de escolas, turmas, alunos, servidores
- Matrículas e transferências, frequência e notas
- Boletins e fichas individuais
- Registros de conteúdo, diário de classe e AEE
- Calendário letivo, Analytics / Ranking de escolas

### Módulo RH / Folha (Fases 1-4 Completas - 27/03/2026)
**Backend**: `/app/backend/routers/hr.py`
**Frontend**: `/app/frontend/src/pages/HRPayroll.js`
**PDF Generator**: `/app/backend/hr_pdf_generator.py`
**Rota**: `/admin/hr`
**Acesso**: admin, semed, semed3, diretor, secretario
**Coleções**: payroll_competencies, school_payrolls, payroll_items, payroll_occurrences, hr_audit_logs

#### Fase 1 - Base:
- Abertura de competência + pré-folha automática
- Dashboard, lista de folhas, detalhe com tabela de servidores
- Edição de lançamentos, ocorrências, validações automáticas
- Fluxo: não_iniciada -> em_preenchimento -> enviada -> aprovada/devolvida -> fechada

#### Fase 2 - Avançado:
- Upload de documentos comprobatórios (PDF/JPG/PNG até 10MB)
- Hora-aula avançado (não cumpridas, repostas, extras)
- Substituições vinculadas com validação
- Horas complementares detalhadas (11 motivos, período, autorização)
- Histórico de alterações (auditoria) com diff campo-a-campo

#### Fase 3 - Fluxo Avançado e Notificações:
- Notificações automáticas ao devolver folha (aviso no sistema para diretor/secretário)
- WebSocket em tempo real para notificações
- Validações rigorosas no envio
- Bloqueio automático por prazo
- Reabertura de competência com justificativa obrigatória

#### Fase 4 - Relatórios PDF (Implementado em 27/03/2026):
- **Espelho Individual**: PDF com dados do servidor, carga horária, ausências, ocorrências, assinaturas
  - Endpoint: `GET /api/hr/reports/espelho/{item_id}`
  - Botão: Tela de detalhe do servidor (item-detail)
- **Folha Consolidada por Escola**: Tabela de todos servidores com totalizadores
  - Endpoint: `GET /api/hr/reports/folha-escola/{payroll_id}`
  - Botão: Tela de detalhe da folha (payroll-detail)
- **Consolidado da Rede**: Resumo de todas as escolas da competência
  - Endpoint: `GET /api/hr/reports/consolidado-rede/{competency_id}`
  - Botão: Dashboard (somente admin/semed)
- **Relatório de Auditoria**: Log de todas as alterações da competência
  - Endpoint: `GET /api/hr/reports/auditoria/{competency_id}`
  - Botão: Dashboard (somente admin/semed)

#### Painel de Indicadores Visuais (Implementado em 27/03/2026):
- **Taxa de Conformidade**: Cards com % de servidores sem pendências e % de folhas enviadas/aprovadas
- **Distribuição de Status**: Gráfico de donut (pizza) com cores por status
- **Horas da Rede**: Gráfico de barras horizontal (Previstas vs Trabalhadas vs Complementares)
- **Ausências por Escola**: Ranking das escolas com mais ausências (barras horizontais)
- **Detalhamento de Ausências**: Gráfico de barras verticais (Faltas, Atestados, Afastamentos)
- Endpoint: `GET /api/hr/dashboard/analytics?competency_id={id}` (somente admin/semed)
- Biblioteca: Recharts v3.8.1

## Correções Implementadas
- Bug fix: Benefícios do aluno (case mismatch)
- PDF Frequência: labels DIAS vs AULAS por nível
- Registros de conteúdo: incluídos na conversão CAIXA ALTA
- PDF Frequência: componente e nível completo para Anos Finais
- Fórmula Carga Horária Mensal: Alterada de Semanal×4.33 para Semanal×5 (27/03/2026)
- Migração retroativa: endpoint `/api/admin/migrate-payroll-hours` + botão em Ferramentas de Administração (27/03/2026)
- Bug fix: Servidores com lotação "anexa" apareciam na folha de pagamento das escolas anexas (28/03/2026)
  - Reescrito filtro `_filter_anexa_items(db, items, school_id)` — verifica por employee_id + school_id (não depende de assignment_id)
  - Aplicado em: detalhe da folha, lista de folhas, dashboard summary, analytics, relatórios PDF (folha-escola, consolidado)
  - Criado endpoint `/api/admin/cleanup-anexa-payroll` — busca por (employee_id, school_id) para remover dados
  - Botão "Limpar Servidores Anexos da Folha" em Ferramentas de Administração
- Renomeado "Horas Não Cumpridas" para "Faltas" em toda a folha de pagamento: visualização, edição e PDFs (28/03/2026)
- Validação de email no formulário de Usuários: impede salvamento de emails sem formato válido (nome@email.com) com feedback visual em tempo real (01/04/2026)
- Removida validação estrita (response_model) do endpoint /api/users para evitar erro 500 por dados inconsistentes no banco (01/04/2026)
- Adicionado handler global de exceções para garantir CORS em respostas 500 (01/04/2026)
- Filtro de componentes em Objetos de Conhecimento: agora busca teacher_assignments da turma para exibir apenas componentes vinculados (01/04/2026)
- Filtro de componentes aplicado também em Frequência (Attendance.js) e Notas (Grades.js) — mesma lógica por teacher_assignments (01/04/2026)
- PDF por componente para EJA e Anos Finais: modal de PDF exige seleção de componente curricular, gerando PDF individual por disciplina (01/04/2026)
- PDF de Frequência para EJA e Anos Finais: validação obrigatória de componente antes de gerar PDF (01/04/2026)
- Aba Relatórios da Frequência: seletor de componente curricular obrigatório para EJA/Anos Finais, com dados filtrados por componente (01/04/2026)
  - Backend: endpoint /report/class/{id} aceita course_id e bimestre como filtros opcionais
  - Frontend: campo de componente aparece apenas para turmas Anos Finais/EJA; botões desabilitados sem seleção
- Correção de Relatório PDF de Frequência para EJA/Anos Finais (01/04/2026):
  - attendance_ext.py: adicionado filtro course_id na query de frequência → PDF agora exibe apenas registros do componente selecionado
  - attendance_ext.py: corrigida busca do professor via teacher_assignments com filtro course_id → nome correto no PDF
  - attendance.py: adicionado filtro por bimestre (datas do calendário) ao endpoint /report/class/{id} → "Ver na Tela" mostra dados do bimestre selecionado
  - Frontend: loadClassReport agora envia selectedBimestre para a API
- Melhorias de robustez no backend (02/04/2026):
  - students.py: geração de matrícula atômica via find_one_and_update (elimina race condition em 3 locais)
  - students.py: re.escape() na busca de alunos por nome/CPF (previne regex injection via campo de busca)
  - attendance.py, hr.py, maintenance.py: substituído except:pass por logger.error para auditoria
  - students.py: corrigido bug pré-existente student_doc → student na transferência externa
- Mensageiro Global e Mensagens Diretas Admin (02/04/2026):
  - Criado MessagingContext para gerenciar estado de chat globalmente
  - ChatBox renderizado no Layout → funciona em qualquer página do sistema
  - MessagesBadge abre chat direto ao clicar (sem redirecionar para /profile)
  - Admin pode enviar mensagem para qualquer usuário sem necessidade de "Conectar"
  - Qualquer usuário pode enviar mensagem para Admin sem necessidade de "Conectar"
  - Backend: endpoint POST /api/connections/direct/{user_id} para criar conexão direta
  - Backend: send_message auto-cria conexão quando admin está envolvido
  - Backend: get_connection_status retorna "admin_direct" quando admin está envolvido
- Hook de Alterações Não Salvas - useUnsavedChangesWarning (02/04/2026):
  - Hook global em /app/frontend/src/hooks/useUnsavedChangesWarning.js
  - Intercepta: fechar aba/F5 (beforeunload), botão voltar do navegador (popstate), navegação interna React Router (guardedNavigate), botão Sair/logout (via UnsavedChangesContext)
  - Contexto global UnsavedChangesContext permite Layout verificar estado de edição para proteger o botão Sair
  - Integrado em Attendance.js (Frequência), Grades.js (Notas) e LearningObjects.js (Objetos de Conhecimento)
  - Rastreia alterações em todos os campos de edição e reseta ao salvar/cancelar

## Papéis SEMED (Reestruturado em 27/03/2026)
- **SEMED** (base): Visualização de módulos acadêmicos + Acompanhamento de Diários
- **SEMED 1** (`semed1`): SEMED + Diário AEE
- **SEMED 2** (`semed2`): SEMED 1 + RH/Folha como Analista (aprovar/devolver)
- **SEMED 3** (`semed3`): SEMED 2 + Dashboard Analítico + Pré-Matrículas (RH somente visualização)

| Módulo | SEMED | SEMED 1 | SEMED 2 | SEMED 3 |
|---|:---:|:---:|:---:|:---:|
| Base (Escolas, Turmas, Alunos, etc.) | Viz | Viz | Viz | Viz |
| Avisos | Edita | Edita | Edita | Edita |
| Acomp. Diários | Viz | Viz | Viz | Viz |
| Diário AEE | - | Viz | Viz | Viz |
| RH / Folha | - | - | Analista | Viz |
| Dashboard Analítico | - | - | - | Viz |
| Pré-Matrículas | - | - | - | Viz |
| Usuários Online | - | - | - | Viz |
| Auditoria | - | - | - | Viz |

### Diretor (Ajustado em 27/03/2026)
- **Somente visualização** em todos os módulos acadêmicos (Escolas, Turmas, Alunos, Notas, Frequência, etc.)
- **Edita**: RH/Folha e Avisos
- **Visualiza**: Diário AEE (novo acesso)

### Secretário (Ajustado em 27/03/2026)
- **Edita**: Diário AEE (novo acesso)

### Auditoria (Ajustado em 27/03/2026)
- Acesso restrito a Admin e SEMED 3 apenas

## Tela de Gestão de Papéis (Implementado em 27/03/2026)
- Botão "Matriz de Permissões" no módulo de Usuários (somente admin)
- Tabela visual 9 papéis × 18 módulos com badges: Edita (verde), Viz (azul), Analista (âmbar), — (sem acesso)
- Dropdown de troca rápida de nível SEMED na coluna "Papel" (semed→semed1→semed2→semed3)
- Restrição: papéis admin/semed/ass_social só são visíveis e criáveis por administradores
- Legenda explicativa no rodapé da matriz

## Tarefas Pendentes

### Outras Tarefas
- (P1) Alterar carga horária de componentes curriculares
- (P2) Envio de e-mail de confirmação na pré-matrícula

### Refatoração
- Modularizar pdf_generator.py (+4200 linhas)
- Centralizar permissões em hook usePermissions
- Refatorar inferEducationLevel duplicado

## Credenciais de Teste
- Admin: gutenberg@sigesc.com / @Celta2007
- Coordenador: coordenador@sigesc.com / coordenador123
- Secretário: secretario@sigesc.com / secretario123

## Notas Técnicas
- Token frontend: `localStorage.getItem('accessToken')` (NÃO 'token')
- Escapar HTML em PDFs: usar `xml_escape`
- Background polling: usar `useRef` para initial load
- Benefits/disabilities: excluídos de uppercase
