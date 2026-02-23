# SIGESC - Sistema de Gestão Escolar

## Problema Original
Sistema de gestão escolar completo com funcionalidades para gerenciamento de escolas, turmas, alunos, professores, notas, frequência, matrículas e pré-matrículas.

## Stack Tecnológica
- **Frontend:** React + TailwindCSS + Shadcn/UI
- **Backend:** FastAPI (Python)
- **Database:** MongoDB
- **Deploy:** Coolify + Docker no DigitalOcean

## Funcionalidades Implementadas

### Core
- ✅ Autenticação JWT com refresh token automático
- ✅ Gestão de escolas e mantenedoras
- ✅ Gestão de turmas com níveis de ensino
- ✅ Gestão de alunos com histórico
- ✅ Gestão de professores e usuários
- ✅ Lançamento de notas e frequência
- ✅ Geração de PDFs (boletins, fichas individuais, atas)
- ✅ Sistema de matrículas e pré-matrículas
- ✅ Notificações em tempo real (WebSocket)
- ✅ Sistema de mensagens entre usuários

### Turmas Multisseriadas (Fev 05, 2026) - NOVO
- ✅ **Backend - Modelo Class:** Adicionados campos `is_multi_grade` (bool) e `series` (List[str])
- ✅ **Backend - Modelo Enrollment:** Adicionado campo `student_series` (str) para especificar série do aluno
- ✅ **Frontend - Formulário de Turmas:** Checkbox "Turma Multisseriada" aparece quando nível de ensino tem múltiplas séries
- ✅ **Frontend - Seleção de Séries:** Quando multisseriada ativada, permite selecionar múltiplas séries via checkboxes
- ✅ **Frontend - Badge na Tabela:** Turmas multisseriadas exibem badge "Multi" com contagem de séries
- ✅ **Frontend - Modal de Matrícula:** Dropdown de série do aluno aparece ao selecionar turma multisseriada
- ✅ **Validação:** Botão de confirmar matrícula desabilitado se turma multisseriada e série não selecionada
- ✅ **Relatório por Série:** Modal de detalhes da turma exibe "Distribuição por Série" com contagem de alunos por série
- ✅ **Coluna Série na Tabela:** Lista de alunos matriculados mostra a série de cada aluno (apenas em turmas multisseriadas)

### Funcionalidades Recentes (Jan 2026)
- ✅ **Atestados Médicos:** Sistema completo para registro de atestados que bloqueia lançamento de frequência
- ✅ **Funcionalidade Offline:** Cadastro e edição de alunos offline com sincronização em background
- ✅ **Legendas em PDFs:** Legenda dinâmica para notas conceituais (Educação Infantil e 1º/2º Ano)
- ✅ **Sessão Persistente:** Token JWT com 7 dias de duração e auto-refresh
- ✅ **Permissões de Secretário:** Perfil com regras granulares de edição
- ✅ **Tratamento de Erros Global:** Utilitário `errorHandler.js` para erros de validação

### Melhorias no Cadastro de Alunos (Fev 02, 2026)
- ✅ **Campos Telefone e E-mail:** Adicionados na mesma linha do Nome Completo na identificação
- ✅ **Formatação de Telefone:** Formato (00)00000-0000 automático
- ✅ **Validação de E-mail:** Verifica formato válido de e-mail
- ✅ **Formatação de CPF:** Formato 000.000.000-00 (máx 11 dígitos)
- ✅ **Formatação de NIS/PIS/PASEP:** Formato 000.00000.00-0 (máx 11 dígitos)
- ✅ **Formatação de Número SUS:** Formato 000.0000.0000.0000 (máx 15 dígitos)
- ✅ **Autocomplete de Cidades:** Campo Naturalidade (Cidade) e Cidade da Certidão Civil com sugestões de cidades brasileiras a partir do 3º caractere
- ✅ **E-mail nos Responsáveis:** Campos de e-mail adicionados para Pai, Mãe e Outro Responsável
- ✅ **Formatação nos Responsáveis:** CPF e Telefone formatados automaticamente

### Funcionalidade de Ação do Aluno (Fev 02, 2026)
- ✅ **Campo "Ação":** Adicionado na aba Turma/Observações da página de edição de aluno
- ✅ **Opções de Ação:** Matricular, Transferir, Remanejar, Progredir
- ✅ **Lógica de Disponibilidade:** Opções habilitadas/desabilitadas com base no status do aluno:
  - **Alunos Transferidos/Desistentes:** Podem ser Matriculados
  - **Alunos Ativos:** Podem ser Transferidos, Remanejados ou Progredidos
- ✅ **Modal de Matricular:** Permite selecionar escola e turma de destino
- ✅ **Modal de Transferir:** Permite informar motivo da transferência
- ✅ **Modal de Remanejar:** Permite selecionar nova turma na mesma escola
- ✅ **Modal de Progredir:** Permite avançar para próxima série ou emitir histórico escolar
- ✅ **Registro no Histórico:** Todas as ações são registradas com tipo (matricula, transferencia_saida, remanejamento, progressao)

### Dashboard Assistente Social (Fev 23, 2026) - NOVO
- ✅ **Nova Página:** `/ass-social` - Dashboard exclusivo para usuários com papel "Ass. Social"
- ✅ **Header Azul:** Barra superior com logo SIGESC e identificação "Assistência Social"
- ✅ **Busca por Nome:** Filtro de alunos por nome com mínimo de 3 caracteres
- ✅ **Busca por CPF:** Alternativa de busca por CPF do aluno
- ✅ **Card de Detalhes:** Exibe informações do aluno selecionado:
  - Nome completo e CPF
  - Data de nascimento
  - Nome da mãe
  - Escola matriculada
  - Série/Turma
  - Porcentagem de frequência no ano letivo
- ✅ **Indicador de Frequência:** Mostra status "Regular" (≥75%) ou "Alerta" (<75%)
- ✅ **Redirecionamento Automático:** Usuários com papel `ass_social` são redirecionados automaticamente para `/ass-social`
- ✅ **Papel "Ass. Social":** Novo papel de usuário adicionado, visível apenas para administradores

### Patches de Segurança - FASE 3 (Fev 02, 2026)
- ✅ **PATCH 3.1 - Idle Timeout:** Access token expira em 15 minutos, mas é renovado automaticamente enquanto o usuário está ATIVO. O frontend detecta atividade (mouse, teclado, scroll) e renova proativamente a cada 10 minutos. Usuários inativos por 15 minutos precisam fazer login novamente
- ✅ **PATCH 3.2 - Rotação de Tokens:** Cada uso do refresh token gera um novo par de tokens e revoga o antigo. Impede reutilização de tokens vazados
- ✅ **PATCH 3.3 - Blacklist de Tokens:** Sistema de revogação com endpoints `/api/auth/logout` (sessão atual) e `/api/auth/logout-all` (todas as sessões). Logout no frontend agora revoga tokens no servidor

### Patches de Segurança - FASE 2 (Fev 02, 2026)
- ✅ **PATCH 2.1 - Filtragem de Dados Sensíveis:** Campos como CPF, RG, NIS, dados bancários e senhas são automaticamente removidos dos dados de sincronização offline
- ✅ **PATCH 2.2 - Paginação no Sync:** Endpoint `/api/sync/pull` agora suporta paginação (`page`, `pageSize`) para evitar sobrecarga de memória. Padrão: 100 itens, máximo: 500
- ✅ **PATCH 2.3 - Rate Limiting no Sync:** Limites implementados - máximo 5 coleções por pull e 100 operações por push

### Patches de Segurança - FASE 1 (Fev 02, 2026)
- ✅ **PATCH 1.1 - Download de Backup:** Rotas `/api/download-backup` e `/api/download-uploads` desativadas por padrão. Requerem `ENABLE_BACKUP_DOWNLOAD=true` no `.env` e autenticação de admin
- ✅ **PATCH 1.2 - Anti-Traversal:** Rota `/api/uploads/{file_path}` protegida contra path traversal (`../`), paths absolutos e acesso fora do diretório de uploads
- ✅ **PATCH 1.3 - Upload Restrito:** Rota `/api/upload` restrita a roles autorizados (admin, admin_teste, secretario, diretor, coordenador)

### Correções e Melhorias (Jan 30, 2026)
- ✅ **Botão "Início":** Adicionado na página de Gestão de Pré-Matrículas para navegação rápida
- ✅ **Cache Offline:** Melhorada a inicialização do banco IndexedDB com tratamento de erros de versão
- ✅ **Banco de Dados Local:** Sistema de auto-recuperação quando há conflitos de versão do Dexie

### Permissões de Secretário (Jan 29, 2026)
- ✅ **Visualização:** Secretário pode ver TODOS os alunos de todas as escolas
- ✅ **Edição de Alunos:** Pode editar alunos ATIVOS apenas da sua escola; alunos NÃO ATIVOS de qualquer escola
- ✅ **Geração de Documentos:** Botão "Documentos" visível apenas para alunos da escola vinculada ao secretário
- ✅ **Filtro de Turmas:** Página de turmas filtrada para mostrar apenas turmas das escolas do secretário
- ✅ **Estatísticas Dashboard:** Cards de estatísticas filtrados para escolas do secretário

## Tarefas Pendentes (Backlog)

### P0 - Crítico
- [ ] **Deploy em Produção:** Resolver Gateway Timeout após redeploy via Coolify
- [ ] **Testar Exportação Excel:** Validar botão "Exportar para Excel" na aba Servidores

### P1 - Alta Prioridade
- [ ] **Refatoração Backend FASE 4:** Extrair rotas restantes e implementar App Factory em `app_factory.py`
- [ ] **Email de Confirmação na Pré-Matrícula:** Enviar email para responsável
- [ ] **Destaque de Aluno Recém-Criado:** Implementar highlight via URL na lista

### P2 - Média Prioridade
- [ ] **Refatoração Frontend:** Decompor o "god component" StudentsComplete.js
- [ ] **Expansão Offline:** Estender funcionalidade offline para módulo de matrículas
- [ ] **Padronização de Erros:** Aplicar errorHandler.js em componentes restantes

### P3 - Baixa Prioridade
- [ ] **Limpeza de Código:** Remover arquivo obsoleto Courses.js
- [ ] **Relatórios Gerenciais:** Criar relatórios para atestados médicos

## Última Atualização
**Data:** 16 de Fevereiro de 2026
**Funcionalidade:** Dashboard de Acompanhamento de Diários e Novos Papéis de Usuário

### Dashboard de Acompanhamento de Diários (Fev 16, 2026):
Implementada nova funcionalidade para monitoramento do preenchimento dos diários escolares (frequência, notas e conteúdos).

**Funcionalidades Implementadas:**
- ✅ **Nova página DiaryDashboard:** `/admin/diary-dashboard` com gráficos de acompanhamento
- ✅ **Cards de resumo:** Exibição de percentuais de preenchimento de Frequência, Notas e Conteúdos
- ✅ **Gráficos interativos:** 4 gráficos usando recharts (Frequência por Mês, Notas por Bimestre, Conteúdos por Mês, Visão Geral)
- ✅ **Filtros:** Escola, Turma, Componente Curricular e Ano Letivo
- ✅ **Link no Dashboard:** Acesso rápido via "Menu de Administração" → "Acompanhamento de Diários"
- ✅ **Backend endpoints:** `/api/diary-dashboard/attendance`, `/grades`, `/content`

**Novos Papéis de Usuário:**
- ✅ **Auxiliar de Secretaria:** Papel com permissões de apenas visualização (mesmo que coordenador)
- ✅ **SEMED Nível 1:** Visualização de todas as escolas (papel base SEMED mantido para retrocompatibilidade)
- ✅ **SEMED Nível 2:** Visualização de todas as escolas + acesso ao dashboard de acompanhamento
- ✅ **SEMED Nível 3:** Visualização de todas as escolas + acesso ao dashboard de acompanhamento

**Melhoria na Página de Registro de Conteúdos:**
- ✅ **Calendário reduzido:** O calendário mensal agora ocupa 1/4 da largura (lg:col-span-1), com o formulário ocupando 3/4 (lg:col-span-3)
- ✅ **Filtro de componentes:** Componentes curriculares são filtrados pelo nível de ensino da turma selecionada

**Arquivos Criados/Modificados:**
- `/app/frontend/src/pages/DiaryDashboard.js` - Nova página de dashboard
- `/app/frontend/src/pages/LearningObjects.js` - Calendário reduzido e filtro de componentes
- `/app/frontend/src/pages/Dashboard.js` - Link para nova página
- `/app/frontend/src/hooks/usePermissions.js` - Definição de novos papéis
- `/app/frontend/src/App.js` - Rotas e permissões atualizadas
- `/app/backend/routers/diary_dashboard.py` - Novo router de endpoints
- `/app/backend/auth_middleware.py` - Permissões para novos papéis
- `/app/backend/server.py` - Registro do novo router

**Testado:** ✅ Validado pelo testing_agent (iteration_19.json - 100% backend, 100% frontend)

---

### Melhorias no Horário de Aulas (Fev 15, 2026):
Implementadas três melhorias no módulo de Horário de Aulas.

**Funcionalidades Implementadas:**
- ✅ **Limite de aulas aumentado:** Opções de 3 a 10 aulas por dia (antes era 3-8)
- ✅ **Coluna Horário:** Nova coluna entre "Aula" e os dias da semana com campos para hora de início e fim (ex: 07:00 / 07:45)
- ✅ **Exibição do professor:** Ao selecionar um componente, exibe o primeiro nome do professor alocado abaixo do dropdown

**Arquivos Modificados:**
- `/app/frontend/src/components/ClassScheduleTab.jsx` - Estados slotTimes, teacherAllocations, funções updateSlotTime e getTeacherForCourse
- `/app/backend/models.py` - Novo modelo SlotTime e campo slot_times em ClassSchedule
- `/app/backend/routers/class_schedule.py` - Suporte a slot_times nos endpoints

**Testado:** ✅ Validado pelo testing_agent (iteration_18.json - 100% backend, 100% frontend)

---

### Relatório de Frequência por Bimestre (Fev 15, 2026):
Implementada a funcionalidade de gerar PDF do relatório de frequência por bimestre.

**Funcionalidades Implementadas:**
- ✅ **Seletor de Bimestre:** Dropdown com opções 1º, 2º, 3º e 4º Bimestre na aba Relatórios
- ✅ **Botão "Gerar PDF":** Botão verde ao lado do "Ver na Tela" que abre o PDF em nova aba
- ✅ **Endpoint Backend:** GET /api/attendance/pdf/bimestre/{class_id}?bimestre={num}&academic_year={year}
- ✅ **PDF Formato Paisagem:** Gerado em A4 landscape com cabeçalho, informações da turma, tabela de frequência diária e espaço para assinaturas

**Arquivos Modificados:**
- `/app/frontend/src/pages/Attendance.js` - Seletor de bimestre e botão Gerar PDF
- `/app/backend/server.py` - Novo endpoint /api/attendance/pdf/bimestre/{class_id}
- `/app/backend/pdf_generator.py` - Nova função generate_relatorio_frequencia_bimestre_pdf

**Testado:** ✅ Validado pelo testing_agent (iteration_17.json - 100% backend, 100% frontend)

---

### Melhorias em Servidores e Alunos (Fev 15, 2026):
Implementadas 4 funcionalidades relacionadas ao cadastro de servidores e alunos, além de melhorias na gestão de lotações e alocações.

**Funcionalidades Implementadas:**
- ✅ **Bug fix CPF:** Corrigido bug onde o CPF não era exibido ao editar um servidor
- ✅ **Máscara de Telefone:** Campo "Celular" no formulário de servidor agora aplica formatação automática (99) 99999-9999
- ✅ **Upload de Certificados:** Botão para anexar certificados a cada formação acadêmica e especialização do servidor
- ✅ **Campo Comunidade Tradicional:** Novo campo no cadastro de alunos com opções: Não Pertence, Quilombola, Cigano, Ribeirinho, Extrativista
- ✅ **Histórico de Certificados:** Modal de detalhes do servidor agora exibe links para visualizar certificados anexados e uma seção unificada "Documentos Anexados" com contagem
- ✅ **Edição de Lotações:** No modal "Gerenciar Lotações", botão de lápis azul permite editar Função, Turno e Data Início de lotações existentes
- ✅ **Edição de Alocações (NOVO):** No modal "Gerenciar Alocações", botão de lápis azul permite trocar o componente curricular de uma alocação existente

**Arquivos Modificados:**
- `/app/frontend/src/components/staff/StaffModal.js` - UI para CPF, telefone e upload de certificados
- `/app/frontend/src/components/staff/StaffDetailModal.js` - Visualização de certificados no perfil do servidor
- `/app/frontend/src/components/staff/LotacaoModal.js` - Edição inline de lotações existentes
- `/app/frontend/src/components/staff/AlocacaoModal.js` - Edição inline de componentes em alocações
- `/app/frontend/src/hooks/useStaff.js` - Handlers de edição para lotações e alocações
- `/app/frontend/src/pages/StudentsComplete.js` - Novo campo comunidade_tradicional
- `/app/frontend/src/pages/Staff.js` - Props de edição para LotacaoModal e AlocacaoModal
- `/app/backend/server.py` - Novo endpoint POST /api/upload/certificado

**Testado:** ✅ Lotações validadas pelo testing_agent (iteration_16.json). Alocações seguem mesmo padrão de implementação.

---

### Horário de Aulas (Fev 13, 2026):
Nova funcionalidade para gerenciar o horário de aulas das turmas.

**Funcionalidades Implementadas:**
- ✅ Nova aba "Horário de Aulas" no Calendário Letivo
- ✅ Seleção de Escola → Turma (filtro dinâmico)
- ✅ Grade de horários com dias da semana (Segunda a Sexta)
- ✅ Navegação por semanas (anterior/próxima/hoje)
- ✅ Exibição das datas da semana atual
- ✅ Número de aulas por dia configurável (3-8 aulas)
- ✅ Turno da turma detectado automaticamente
- ✅ Lógica de sábados letivos (preenchimento automático baseado no dia correspondente)
- ✅ Validação de conflitos de professor (mesmo professor em duas turmas no mesmo horário)
- ✅ Controle de permissões (admin/secretário podem editar; outros só visualizam)
- ✅ Filtros de visualização por perfil (aluno/responsável/professor/secretário/diretor/coordenador)
- ✅ **NOVO: Painel de Conflitos da Rede** - Visualização em tempo real de todos os conflitos de horário

**Painel de Conflitos da Rede:**
- Exibe todos os professores com aulas sobrepostas em toda a rede
- Gráfico de conflitos por dia da semana
- Filtro por escola específica
- Detalhes completos de cada conflito (turma, escola, componente)
- Acessível apenas para admin, semed e secretário

**Regras de Sábados Letivos:**
- 1º sábado letivo = aulas de segunda-feira
- 2º sábado letivo = aulas de terça-feira
- 3º sábado letivo = aulas de quarta-feira
- ... até o 12º, depois volta ao início

**Arquivos Criados:**
- `/app/backend/routers/class_schedule.py` - Router completo da API
- `/app/frontend/src/components/ClassScheduleTab.jsx` - Componente da interface

**Arquivos Modificados:**
- `/app/backend/models.py` - Adicionados modelos ClassSchedule, ClassScheduleSlot
- `/app/backend/server.py` - Registrado o router class_schedule
- `/app/frontend/src/services/api.js` - Adicionado classScheduleAPI
- `/app/frontend/src/pages/Calendar.js` - Integrada nova aba

---

### Indicação de Gênero nas Funções/Cargos (Fev 12, 2026):
Todas as funções e cargos agora exibem indicação de gênero masculino/feminino.

**Alterações Realizadas:**
- ✅ **Dashboard:** Cards e botões de acesso rápido exibem "Alunos(as)" e "Servidores(as)"
- ✅ **Página de Alunos:** Título "Alunos(as)", botões "Novo(a) Aluno(a)" e "Editar Aluno(a)"
- ✅ **Página de Servidores:** Título "Gestão de Servidores(as)", aba "Servidores(as)", botão "Novo(a) Servidor(a)"
- ✅ **Logs de Auditoria:** Filtros de entidade com "Alunos(as)" e "Servidores(as)"
- ✅ **Labels de Papéis:** Secretário(a), Diretor(a), Coordenador(a), Professor(a), Aluno(a), Responsável(is)
- ✅ **Cargos de Servidores:** Auxiliar Administrativo(a), Coordenador(a), Diretor(a), Professor(a), Secretário(a), etc.

**Arquivos Modificados:**
- `/app/frontend/src/pages/Dashboard.js`
- `/app/frontend/src/pages/StudentsComplete.js`
- `/app/frontend/src/pages/Students.js`
- `/app/frontend/src/pages/Staff.js`
- `/app/frontend/src/pages/AuditLogs.jsx`
- `/app/frontend/src/pages/Users.js`
- `/app/frontend/src/pages/Announcements.js`
- `/app/frontend/src/components/Layout.js`
- `/app/frontend/src/components/staff/constants.js`
- `/app/frontend/src/components/staff/StaffModal.js`
- `/app/frontend/src/pages/SchoolsComplete.js`
- E outros arquivos relacionados

### Filtro de Alunos por Escola no Dashboard (Fev 12, 2026):
Secretários, diretores e coordenadores agora veem apenas a quantidade de alunos das escolas às quais têm vínculo.

**Funcionalidade:**
- ✅ **Dashboard:** Stats filtradas para secretário, diretor e coordenador
- ✅ **AnalyticsDashboard:** Dados já filtrados no backend por `userSchoolIds`
- ✅ **Lógica Implementada:** Variável `isSchoolStaff` identifica esses papéis e filtra `filteredStudents` por `school_id`

**Arquivos Modificados:**
- `/app/frontend/src/pages/Dashboard.js` (linhas 29-91)
- `/app/backend/routers/analytics.py` (já implementado anteriormente)

---

### Campos CPF, E-mail, Turma e Turno na Aba Servidores (Fev 12, 2026):
Adicionadas novas colunas na tabela de servidores do cadastro de escola.

**Campos Adicionados:**
- ✅ **CPF** - Formatado como XXX.XXX.XXX-XX
- ✅ **Turma(s)** - Mostra badges com os nomes das turmas onde o servidor atua
- ✅ **Turno** - Mostra Matutino/Vespertino/Noturno/Integral da lotação

**Arquivos Modificados:**
- `/app/frontend/src/pages/SchoolsComplete.js`

---

### Filtro de Usuário nos Logs de Auditoria (Fev 11, 2026):
Adicionado dropdown para filtrar logs por usuário específico.

**Funcionalidade:**
- ✅ Dropdown "Todos os usuários" com lista de usuários do sistema
- ✅ Lista ordenada alfabeticamente pelo nome
- ✅ Integração com o backend (parâmetro `user_id`)
- ✅ Ícone de usuário para identificação visual

**Arquivo Modificado:**
- `/app/frontend/src/pages/AuditLogs.jsx`

---

### Filtro de Ano Letivo no Cadastro de Aluno (Fev 10, 2026):
Adicionado seletor de ano letivo na seção "Vínculo com Turma" tanto para Novo Aluno quanto para Editar Aluno.

**Funcionalidade:**
- ✅ Dropdown de ano letivo (2025-2030) ao lado do título "Vínculo com Turma"
- ✅ Turmas filtradas automaticamente pelo ano selecionado
- ✅ Label do campo "Turma" mostra o ano selecionado (ex: "Turma (2026)")
- ✅ Mensagem de aviso quando não há turmas para o ano/escola selecionados
- ✅ Ao mudar o ano ou escola, a turma selecionada é limpa automaticamente
- ✅ **NOVO**: Edição de aluno agora permite selecionar escola e turma de outros anos
- ✅ **NOVO**: Ao abrir para edição, o ano é automaticamente definido com base na turma atual do aluno

**Arquivo Modificado:**
- `/app/frontend/src/pages/StudentsComplete.js`

---

### Melhorias na Geração de Documentos (Fev 10, 2026):

**1. Bloqueio de Documentos para Alunos Inativos:**
- ✅ Alunos com status diferente de "Ativo" (Transferido, Inativo, Desistente, etc.) não podem ter documentos gerados
- ✅ Mensagem clara informando o status atual do aluno e que apenas alunos ativos podem ter documentos
- ✅ Implementado nos endpoints: Boletim, Ficha Individual, Declaração de Matrícula e Declaração de Frequência

**2. Redução do Tamanho do Brasão em 40%:**
- ✅ Tamanho do brasão reduzido em todos os documentos PDF
- ✅ Boletim: 2.7cm x 1.8cm → 1.62cm x 1.08cm
- ✅ Declarações: 3.75cm x 2.5cm → 2.25cm x 1.5cm
- ✅ Ficha Individual: 2.4cm x 1.6cm → 1.44cm x 0.96cm

**3. Melhorias nas Declarações (Matrícula e Frequência):**
- ✅ Endereço completo da escola usando campos de Localização (logradouro, número, bairro, município, estado, CEP)
- ✅ Telefone da escola no formato correto "(DDD) NÚMERO" ou em branco se não cadastrado
- ✅ Turno traduzido para português: morning→Matutino, afternoon→Vespertino, full_time→Integral
- ✅ Removida assinatura do Diretor (mantida apenas do Secretário Escolar)
- ✅ Margem superior reduzida em 60% (3cm → 1.2cm)

**4. Declaração de Frequência - Cálculo Correto:**
- ✅ Total de dias letivos calculado com base no calendário letivo até a data de emissão
- ✅ Dias de presença = dias letivos - faltas registradas
- ✅ Percentual de frequência baseado nos dias letivos transcorridos
- ✅ Considera feriados, recessos e sábados letivos do calendário

**5. Declaração de Matrícula - Número de Matrícula:**
- ✅ Usa o `enrollment_number` do aluno quando `registration_number` é N/A

**Arquivos Modificados:**
- `/app/backend/server.py` - Verificação de status e cálculo de frequência
- `/app/backend/pdf_generator.py` - Layout das declarações e tamanho do brasão

---

### Logs de Auditoria - Exibição de Nomes (Fev 10, 2026):
Alterada a página de Auditoria para exibir o nome completo dos usuários em vez do email, melhorando a legibilidade.

**Alterações:**
- ✅ Método `get_logs()` em `audit_service.py` modificado para usar aggregation pipeline com `$lookup`
- ✅ Enriquecimento dos logs com nomes de usuários da coleção `users`
- ✅ Compatibilidade com logs antigos que não tinham `user_name` preenchido
- ✅ Frontend já estava preparado para exibir `user_name || user_email`

**Arquivo Modificado:**
- `/app/backend/audit_service.py`

---

### Última Atualização Anterior
**Data:** 07 de Fevereiro de 2026
**Funcionalidade:** Simplificação de Imagem - Unificação Brasão/Logotipo

### Unificação Brasão/Logotipo (Fev 07, 2026):
Removido o campo "Logotipo" separado, mantendo apenas o "Brasão" como imagem única do sistema.

**Motivo:** Resolver problema de upload FTP em produção simplificando a estrutura.

**Alterações:**
- ✅ Removido campo `logotipo_url` do formulário de Mantenedora
- ✅ Campo `brasao_url` agora é a única imagem do sistema
- ✅ Fallback automático: se `brasao_url` não existir, usa `logotipo_url` (retrocompatibilidade)
- ✅ Layout.js atualizado para usar `brasao_url || logotipo_url`
- ✅ MantenedoraContext.js: função `getBrasaoUrl()` substituiu `getLogotipoUrl()`
- ✅ pdf_generator.py: todas as referências atualizadas para `brasao_url or logotipo_url`
- ✅ Label atualizado: "Brasão / Logotipo" com descrição explicativa

**Arquivos Modificados:**
- `/app/frontend/src/pages/Mantenedora.js`
- `/app/frontend/src/components/Layout.js`
- `/app/frontend/src/contexts/MantenedoraContext.js`
- `/app/backend/pdf_generator.py`

---

### Score V2.1 - Implementado (Fev 07, 2026):
Sistema de pontuação de 0-100 pontos para ranking de escolas, baseado em indicadores objetivos.

#### Composição do Score (100 pontos):

**BLOCO APRENDIZAGEM (45 pts):**
- ✅ **Nota Média (25 pts):** `(média_final / 10) × 100`
- ✅ **Taxa de Aprovação (10 pts):** `(aprovados / total_avaliados) × 100`
- ✅ **Ganho/Evolução (10 pts):** `clamp(50 + delta×25, 0, 100)` - Mede evolução entre bimestres

**BLOCO PERMANÊNCIA/FLUXO (35 pts):**
- ✅ **Frequência Média (25 pts):** `(P + J) / total × 100`
- ✅ **Retenção/Anti-evasão (10 pts):** `100 - (dropouts / matrículas) × 100`

**BLOCO GESTÃO/PROCESSO (20 pts):**
- ✅ **Cobertura Curricular (10 pts):** `(aulas_com_registro / aulas_previstas) × 100` (proxy)
- ✅ **SLA Frequência - 3 dias úteis (5 pts):** `(lançamentos_no_prazo / total) × 100`
- ✅ **SLA Notas - 7 dias (5 pts):** `(lançamentos_no_prazo / total) × 100`

**INDICADOR INFORMATIVO (não entra no score):**
- ✅ **Distorção Idade-Série:** % de alunos com 2+ anos acima da idade esperada para a série

#### Endpoint Atualizado:
- `GET /api/analytics/schools/ranking?academic_year=YYYY&limit=N&bimestre=B`
  - Retorna: `score`, `score_aprendizagem`, `score_permanencia`, `score_gestao`
  - Retorna: `indicators` com todos os indicadores detalhados
  - Retorna: `raw_data` com dados brutos para auditoria
  - Retorna: `grade_evolution` com médias bimestrais (b1, b2, b3, b4)

#### Frontend Atualizado:
- ✅ Tabela de ranking com todas as colunas de indicadores
- ✅ Cores indicativas (verde/amarelo/vermelho) por faixa de desempenho
- ✅ Breakdown por bloco (Aprendizagem | Permanência | Gestão)
- ✅ Legenda explicativa dos indicadores
- ✅ Tooltip com descrição de cada coluna
- ✅ **Gráfico de Radar** comparando Top 5 escolas nos 3 blocos
- ✅ **Barras de progresso** mostrando % de aproveitamento por bloco
- ✅ **Modal de Drill-Down** com detalhamento completo ao clicar em uma escola:
  - Resumo dos 3 blocos com pontuação e percentual
  - Detalhamento dos 8 indicadores com contribuição individual
  - Gráfico de evolução das notas por bimestre (AreaChart)
  - Indicador informativo de Distorção Idade-Série
  - Dados brutos (matrículas, aprovados, evasões, objetos de conhecimento)
- ✅ **Exportação de Relatórios:**
  - Botão "Exportar Ranking" no card de ranking (Excel com todas as escolas)
  - Botão "Excel" no modal de drill-down (planilha detalhada da escola)
  - Botão "PDF" no modal de drill-down (relatório formatado com gráficos e tabelas)

### Restrições de Acesso - LGPD (Fev 07, 2026):
Sistema de controle de acesso por perfil para proteger dados sensíveis conforme LGPD.

#### Matriz de Permissões:

| Funcionalidade | Admin | SEMED | Diretor | Coord. | Secret. | Professor |
|----------------|-------|-------|---------|--------|---------|-----------|
| Ranking de Escolas | ✅ | ✅* | ❌ | ❌ | ❌ | ❌ |
| Gráfico de Radar | ✅ | ✅* | ❌ | ❌ | ❌ | ❌ |
| Drill-Down Escolas | ✅ | ✅* | ❌ | ❌ | ❌ | ❌ |
| Desempenho Alunos (global) | ✅ | ✅* | ❌ | ❌ | ❌ | ❌ |
| Desempenho Alunos (escola) | ✅ | ✅* | ✅ | ✅ | ✅ | ❌ |
| Desempenho Alunos (turma) | ✅ | ✅* | ✅ | ✅ | ✅ | ✅** |

*\* SEMED requer aceite do Termo de Responsabilidade (válido por 30 dias)*
*\*\* Professor vê apenas suas turmas e componentes curriculares vinculados*

#### Implementações:

**Backend:**
- ✅ Endpoint `/api/analytics/schools/ranking`: Restrito a Admin/SEMED
- ✅ Endpoint `/api/analytics/students/performance`: Filtrado por perfil
  - Professor: Obrigatório selecionar turma vinculada
  - Staff escola: Filtrado pela escola vinculada
- ✅ Endpoint `/api/analytics/semed/check-terms`: Verifica aceite do termo
- ✅ Endpoint `/api/analytics/semed/accept-terms`: Registra aceite (30 dias)
- ✅ Collection `user_terms`: Armazena aceites com data de expiração

**Frontend:**
- ✅ Variáveis de controle: `canViewRanking`, `canViewStudentData`, `isProfessor`, `isSchoolStaff`
- ✅ Modal do Termo de Responsabilidade para SEMED com:
  - Descrição dos dados acessíveis
  - Compromissos LGPD
  - Validade de 30 dias
- ✅ Mensagens de restrição contextuais para cada perfil
- ✅ Card "Desempenho dos Alunos" com estados:
  - Professor sem turma: "Selecione uma turma"
  - Sem permissão: "Acesso Restrito"
  - Sem dados: "Nenhum dado disponível"

### Arquivos Modificados:
- `/app/backend/routers/analytics.py` - Endpoint `/schools/ranking` completamente reescrito
- `/app/frontend/src/pages/AnalyticsDashboard.jsx` - Nova tabela de ranking com Score V2.1

---

### Implementações Anteriores (Fev 05, 2026):
1. **Ordenação Alfabética**
   - ✅ Escolas, turmas e alunos ordenados alfabeticamente nos filtros do Dashboard Analítico
   
2. **Bloqueio de Alunos Transferidos**
   - ✅ Alunos com status "transferido" têm frequência e notas bloqueadas para edição pelo professor
   - ✅ Badge "🔒 Bloqueado" exibido na lista de alunos
   
3. **Remanejamento - Cópia de Dados**
   - ✅ 100% dos dados de frequência E notas são copiados para turma destino
   - ✅ Dados na turma de origem ficam bloqueados para o professor
   - ✅ Endpoint `/api/students/{id}/copy-data` criado
   
4. **Progressão - Cópia de Dados**
   - ✅ 100% dos dados de frequência são copiados para turma destino
   - ✅ Dados na turma de origem ficam bloqueados para o professor
   
5. **Bloqueio de Alunos Falecidos**
   - ✅ Alunos com status "falecido/deceased" têm frequência e notas bloqueadas para professor

## Arquitetura de Deploy

### Coolify + Traefik
O Traefik não detecta automaticamente os labels dos containers. Foi necessário criar configuração manual:

```yaml
# /traefik/dynamic/sigesc-backend.yaml (dentro do container coolify-proxy)
http:
  routers:
    sigesc-backend:
      rule: "Host(`api.sigesc.aprenderdigital.top`)"
      service: sigesc-backend-service
      entryPoints:
        - https
      tls:
        certResolver: letsencrypt
  services:
    sigesc-backend-service:
      loadBalancer:
        servers:
          - url: "http://backend:8001"
```

### Domínios
- **Frontend:** https://sigesc.aprenderdigital.top
- **Backend API:** https://api.sigesc.aprenderdigital.top

## Arquivos Importantes

### Backend
- `/app/backend/server.py` - Servidor principal FastAPI
- `/app/backend/models.py` - Modelos Pydantic
- `/app/backend/pdf_generator.py` - Geração de PDFs
- `/app/backend/routers/medical_certificates.py` - API de atestados

### Frontend
- `/app/frontend/src/pages/StudentsComplete.js` - Gestão de alunos
- `/app/frontend/src/pages/PreMatriculaManagement.jsx` - Gestão de pré-matrículas
- `/app/frontend/src/pages/Attendance.js` - Lançamento de frequência
- `/app/frontend/src/utils/errorHandler.js` - Tratamento de erros
- `/app/frontend/src/db/database.js` - Banco de dados local (IndexedDB/Dexie)
- `/app/frontend/src/contexts/OfflineContext.jsx` - Contexto de funcionalidade offline
- `/app/frontend/nginx.conf` - Configuração do Nginx

## Credenciais de Teste
- **Admin:** gutenberg@sigesc.com / @Celta2007
- **Secretários de teste:**
  - ROSIMEIRE: rosimeireazevedo@sigesc.com (vinculada à escola "C M E I PROFESSORA NIVALDA MARIA DE GODOY")
  - ADRIANA: adrianapereira@sigesc.com (vinculada à escola "E M E I E F PAROQUIAL CURUPIRA")

## Documentação de Infraestrutura
- `/app/memory/TRAEFIK_FIX_GUIDE.md` - Guia completo para resolver o problema do Traefik no Coolify
- `/app/docker-compose.coolify.yml` - Docker Compose otimizado para deploy no Coolify

## Backlog

### P0 - Crítico
- ⚠️ **Configuração do Traefik no Coolify:** A configuração manual atual é frágil. Aplicar o guia `/app/memory/TRAEFIK_FIX_GUIDE.md` para solução permanente. **NOTA:** Este é um problema de infraestrutura externa que requer acesso ao servidor de produção.

### P1 - Próximas
- Email de confirmação após pré-matrícula
- Highlight do aluno recém-criado na lista
- Padronizar valores de status dos alunos no banco de dados ("transferred" vs "Transferido")

### Implementações Recentes (Fev 2026)

#### Diário AEE - Atendimento Educacional Especializado (Fev 20, 2026) - NOVO
- ✅ **Backend - Modelos:** PlanoAEE, AtendimentoAEE, EvolucaoAEE, ArticulacaoSalaComum
- ✅ **Backend - API:** `/api/aee/*` - CRUD completo para planos, atendimentos, evoluções
- ✅ **Backend - PDF:** Geração de diário em PDF por aluno ou completo
- ✅ **Frontend - Página:** `/admin/diario-aee` com 4 abas (Estudantes, Planos AEE, Atendimentos, Diário Consolidado)
- ✅ **Frontend - Modais:** Cadastro de Plano AEE e Registro de Atendimento
- ✅ **Frontend - Grade:** Visualização da grade de atendimentos por dia da semana
- ✅ **Frontend - Estatísticas:** Resumo de frequência, carga horária, total de atendimentos
- ✅ **Campos do Plano:** Público-alvo, barreiras, objetivos, cronograma, recursos de TA, articulação com sala comum
- ✅ **Campos do Atendimento:** Data, horário, presença, objetivo trabalhado, atividade, nível de apoio, resposta do estudante

#### Validações de Dados (Fev 20, 2026) - NOVO
- ✅ **Status Ativo:** Aluno não pode ter status "Ativo" sem escola e turma definidas
- ✅ **CPF Duplicado:** Backend bloqueia salvamento de CPF duplicado em alunos e servidores
- ✅ **CAIXA ALTA:** Campos de texto convertidos para maiúsculas (exceto e-mail)

#### Correção de Bug - Alunos Matriculados (Fev 20, 2026) - NOVO
- ✅ **Detalhes da Turma:** Endpoint `/classes/{id}/details` agora busca alunos de duas fontes (enrollments + students) para garantir que todos os alunos vinculados apareçam

### P2 - Futuras (FASE 4 Concluída)
- ✅ **Routers Extraídos:** students, grades, attendance, calendar, staff, announcements
- ✅ **Rotas Legadas Removidas:** 28 rotas duplicadas removidas do server.py
- ✅ **Redução de Código:** server.py reduzido de 7588 para 6470 linhas (~15%)
- ✅ **App Factory:** Criado `/app/backend/app_factory.py` com padrão Factory
- Refatoração do `SchoolsComplete.js`
- Expansão offline para matrículas
- Padronização de erros em todos componentes

### P3 - Backlog
- Remover `Courses.js` obsoleto
- Relatórios gerenciais de atestados médicos
