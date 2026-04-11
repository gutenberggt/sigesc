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

## Bug Fixes (07/04/2026)
- Fix Batch PDF (P0): `get_batch_documents` agora usa mesma lógica de filtragem do individual
- Fix Limpeza de Conceitos: Backend agora aceita `null` em campos de nota (b1-b4, rec_s1, rec_s2) para permitir limpar conceitos selecionados erroneamente (tracinho "-")
- Fix Conceito Final: Quando todas as notas são limpas, `final_average` reseta para `null` e `status` para `cursando` (backend + frontend)
- Feature "Ignorar" na Alocação: Checkbox ao lado de cada componente curricular para marcar como voluntário (não contabiliza carga horária na lotação/folha)
- Fix Filtro Componentes por Atendimento: Boletim/Ficha Individual/Batch agora filtram componentes por `atendimento_programa` da turma (regular, integral, AEE). Filtro aplicado SEMPRE, inclusive quando há teacher_assignments — turmas regulares/multisseriadas não recebem mais componentes de escola integral
- Fix status filter: Adicionado 'ativo' (lowercase) ao filtro de status dos teacher_assignments em todos os 3 endpoints de documentos
- Feature Histórico Escolar: CRUD completo + geração de PDF. Acessível por Admin, Secretário, Diretor, Auxiliar de Secretaria. Backend: `/api/student-history/{id}` (GET/POST) + `/api/documents/historico-escolar/{id}` (PDF). Frontend: `StudentHistory.js` com formulário por série (1º-9º), notas por componente BNCC + parte diversificada
  - Filtra componentes via `teacher_assignments` (fallback: `nivel_ensino`)
  - Calcula `attendance_data` com estrutura `_meta` (faltas_regular, faltas_por_componente)
  - Busca `calendario_letivo` corretamente (era `db.calendar`, agora `db.calendario_letivo`)
  - Calcula `dias_letivos_ano` por bimestre
  - Propaga `student_series` do aluno para enrollment
  - (07/04/2026) Funcionalidade "Desvincular Aluno da Turma": novo endpoint `POST /api/enrollments/cancel-enrollment` que cancela matrícula ativa (status = 'cancelled') mantendo histórico com motivo, data e responsável. Botão `UserX` aparece na coluna AÇÕES quando turma está filtrada. Modal com campo de motivo obrigatório. Apenas Admin e Secretário.

## Bug Fixes (07/04/2026 - Sessão 2)
- Fix Filtro Turma AEE no Diário AEE (P0): Backend não retornava `class_id` e `atendimento_programa_class_id` nas respostas das APIs `/api/aee/estudantes`, `/api/aee/diario` e `/api/students`. Frontend não conseguia filtrar alunos por turma AEE selecionada.
  - `aee.py` `get_estudantes_aee`: adicionado `atendimento_programa_class_id` na projeção MongoDB e no response dict (ambas seções: alunos com plano e alunos sem plano)
  - `aee.py` `get_diario_aee`: adicionado `class_id` e `atendimento_programa_class_id` na projeção e no objeto `student` das fichas
  - `students.py` `list_students`: adicionado `atendimento_programa_class_id` na `list_projection`
  - `DiarioAEE.js`: filtro melhorado com fallback direto nos dados do `estudantes` (não depende apenas do array `students`)
- Ajuste card de estudante AEE (08/04/2026): Removida matrícula, adicionadas "Escola Origem" e "Professor Regente" no card dos estudantes do Diário AEE
  - Backend: `get_estudantes_aee` agora busca `school_name` e professor regente via `teacher_assignments` + `staff`
  - Frontend: `DiarioAEE.js` card atualizado com novos campos
- Dashboard Professor AEE (10/04/2026): Adicionado "Diário AEE" no Acesso Rápido e na lista de turmas.
  - Se professor só tem turmas AEE: oculta "Lançar Notas", "Frequência" e "Objetos de Conhecimento"
  - Se tem turmas regulares + AEE: exibe todos os menus
  - Turmas separadas visualmente: AEE (cards teal) e Regulares
- Modal Novo Plano AEE (08/04/2026): Dropdown de alunos filtrado por turma selecionada; campo Professor Regente auto-preenchido (somente leitura); campo Turma de Origem somente leitura; removido temporizador de alerta auto-dismiss
- Correção Frequência Anos Finais (09/04/2026): Padronizado tudo em hora-aula (number_of_classes):
  - `aulas_previstas` = course.workload (anual) / 4 (bimestre). Sem misturar dias letivos × slots.
  - `aulas_ministradas` = soma real de number_of_classes registradas no diário.
  - P/F/J por aluno = multiplicado por number_of_classes de cada lançamento.
  - attendance-summary (Lançamento): workload como fonte primária, schedule_slots como fallback.
  - PDF (attendance_ext.py + frequencia.py): mesma lógica padronizada.
  - Alertas (attendance_ext.py): P/F/J × number_of_classes.
  - Relatórios (attendance.py): report_type="aulas" para anos finais.
  - Frontend (Attendance.js): exibe "X aulas" em vez de "X dias" para anos finais.
- Refatoração UI Frequência Anos Finais - Abas de Sessão (10/04/2026):
  - Frontend (Attendance.js): Substituída lógica legada de pipe `P|F|J` e múltiplas colunas por sistema de abas (Aula 1, Aula 2, + Nova Aula)
  - Cada aba representa uma sessão independente (aula_numero), tabela sempre com coluna única "Frequência"
  - Troca de aba carrega status corretos da sessão selecionada do backend (via sessions[].records)
  - `updateStudentStatus` e `markAll` simplificados: sem pipe, sem aulaIndex, operam na sessão ativa
  - `saveAttendance` envia `aula_numero` = sessão ativa para turmas de anos finais
  - Removido estado legado `numberOfClasses` — substituído pelo array `sessions` + `activeSession`
  - Retrocompatibilidade: turmas de Anos Iniciais funcionam normalmente (sem abas, frequência diária)
  - Testado: 17/17 cenários passaram (testing agent iteration_48)
- UI Frequência Anos Finais - Colunas Múltiplas (10/04/2026):
  - Substituídas abas de sessão por dropdown "Nº de Aulas:" (1 a 6)
  - Número selecionado gera colunas na tabela (1ª AULA, 2ª AULA, 3ª AULA...) com P/F/J por aluno
  - Cada aula é salva como registro independente com `aula_numero` no backend
  - "Todos Presentes" / "Todos Ausentes" marca TODAS as colunas de todos os alunos
  - Estado `aulaStatuses` gerencia status por aluno por aula: `{ studentId: { 1: 'P', 2: 'F' } }`
  - Ao carregar: popula `aulaStatuses` e `numberOfAulas` a partir das `sessions` retornadas pela API
  - Retrocompatibilidade: turmas Anos Iniciais = coluna única "Frequência" sem dropdown
  - Testado: 12/12 cenários passaram (testing agent iteration_49)
- Fix Relatório e PDF Frequência Anos Finais (10/04/2026):
  - **Relatório (Ver na Tela)**: Adicionado suporte a pipe-separated statuses (legado "P|F") no cálculo de P/F/J/total
  - **PDF**: Path legado agora expande `number_of_classes > 1` em colunas separadas (repete data para múltiplas aulas no mesmo dia)
  - **PDF**: Suporte a pipe-separated statuses (cada status do pipe vira uma coluna distinta)
  - **Alertas**: Mesmo fix de pipe-separated aplicado no endpoint de alertas
  - Dados mistos (novo aula_numero + legado number_of_classes + pipe) tratados corretamente
- Ajuste PDF Objetos de Conhecimento para Anos Iniciais e Ed. Infantil (11/04/2026):
  - "Total de Registros" → "Dias Previstos:" com cálculo real do calendário letivo (dias úteis no bimestre)
  - "Total de Aulas" → "Dias Registrados:" com contagem de datas únicas
  - Removida coluna "AULAS" da tabela
  - Colunas "CONTEÚDO" e "PRÁTICAS PEDAGÓGICAS" reduzidas a 2/3
  - Espaço liberado (1/3 de cada + coluna AULAS) acrescido à coluna "COMPONENTE CURRICULAR"
  - Anos Finais e EJA: mantido layout original (5 colunas com AULAS)

## Tarefas Pendentes

### Outras Tarefas
- (P1) Carga horária zerada na folha de pagamento (aguardando decisão do usuário)
- (P1) Alterar carga horária de componentes curriculares
- (P2) Envio de e-mail de confirmação na pré-matrícula

### Refatoração
- ~~Modularizar pdf_generator.py (+4200 linhas)~~ CONCLUÍDO (06/04/2026): Dividido em pacote `pdf/` com 11 módulos
- ~~Centralizar permissões em hook usePermissions~~ CONCLUÍDO (06/04/2026): Hook em `/app/frontend/src/hooks/usePermissions.js`, integrado em 8 páginas (Dashboard, Attendance, Grades, LearningObjects, Events, Enrollments, StudentsComplete, Classes)
- ~~Refatorar inferEducationLevel duplicado~~ CONCLUÍDO (06/04/2026): Centralizado em `/app/frontend/src/utils/educationLevel.js`

## Bug Fixes Produção (06/04/2026)
- Fix CORS 503: variáveis `turma_integral` e `class_id` indefinidas nos endpoints boletim e ficha individual (NameError → crash → 503 sem CORS)
- Fix IndexedDB VersionError: SW v2.1.0 abre DB sem versão fixa + não intercepta requests cross-origin

## Credenciais de Teste
- Admin: gutenberg@sigesc.com / @Celta2007
- Coordenador: coordenador@sigesc.com / coordenador123
- Secretário: secretario@sigesc.com / secretario123

## Notas Técnicas
- Token frontend: `localStorage.getItem('accessToken')` (NÃO 'token')
- Escapar HTML em PDFs: usar `xml_escape`
- Background polling: usar `useRef` para initial load
- Benefits/disabilities: excluídos de uppercase
