# SIGESC - Sistema de Gestão Escolar

## Problema Original
Sistema de gestão escolar para a Secretaria Municipal de Educação, com funcionalidades de:
- Cadastro de escolas, turmas, alunos, professores
- Registro de notas e frequência
- Geração de documentos (boletins, fichas individuais, certificados, declarações)
- Controle de ano letivo
- Gestão de lotações de servidores

## Implementações Recentes

### 2026-01-06 (Sessão 5)
- **Bug Crítico Corrigido - Lógica de Aprovação Ignorava Componentes Sem Nota** (P0 - RESOLVIDO):
  - Problema 1: Alunos com componentes OBRIGATÓRIOS sem nota (media=None) eram marcados como "APROVADO"
  - Problema 2: O Boletim exibia notas com ponto (.) em vez de vírgula (,)
  - Causa raiz: A função `_calcular_resultado_com_avaliacao` ignorava componentes onde `media is None`, mesmo sendo obrigatórios
  - Correção 1: Em `grade_calculator.py`, componentes obrigatórios sem nota agora são adicionados à lista de reprovados
  - Correção 2: Em `pdf_generator.py`, a função `fmt_grade` do Boletim agora usa `.replace('.', ',')`
  - Regra de negócio: "Só pode ser Aprovado se, em TODOS os componentes obrigatórios a média for >= 5,0"
  - **Testado**: 54 testes unitários passaram
  - Cenário principal: Aluna Ana Beatriz Pereira Sousa (5º Ano A) - 2 componentes com nota, 10 sem nota → REPROVADO (antes: APROVADO)
  - Arquivos de teste: `tests/test_mandatory_no_grade_bug.py` (13 testes)

- **Bug Corrigido - Notas não exibidas no Livro de Promoção** (P1 - RESOLVIDO):
  - Problema: A página do Livro de Promoção exibia "-" em todas as células de notas, mesmo havendo notas no banco
  - Causa raiz 1: O código esperava formato `period/grade` mas as notas usam `b1, b2, b3, b4, rec_s1, rec_s2`
  - Causa raiz 2: A ordem dos alunos em `filteredStudents` não correspondia à ordem em `studentIds`, fazendo com que as notas fossem associadas ao aluno errado
  - Correção: Em `Promotion.jsx`, mapeamento direto dos campos e uso de `indexOf` para encontrar o índice correto das notas
  - **Testado**: Screenshot confirmou que as notas estão aparecendo corretamente

- **Feature - Exibição de Data Limite de Edição para Professores** (P1 - IMPLEMENTADO):
  - Antes: Professor só via aviso quando o prazo já havia encerrado
  - Agora: Professor vê a data limite **antes** de encerrar, com:
    - Contador de dias restantes
    - Cores indicativas de urgência (azul: normal, amarelo: <= 7 dias, laranja: <= 3 dias)
    - Ícone de calendário e mensagem informativa
  - Componente: `BimestreDeadlineAlert` em `BimestreStatus.jsx`
  - Backend: Endpoint `/api/calendario-letivo/{ano}/status-edicao` agora retorna `data_limite` para todos os usuários
  - **Testado**: Screenshot confirmou exibição do alerta com datas limite

- **Bug Corrigido - Média para Aprovação não salva na Mantenedora** (P1 - RESOLVIDO):
  - Problema: O campo "Média para Aprovação" não exibia o valor salvo e ao salvar sem alterar, perdia o valor
  - Causa raiz: O backend retorna `5.0` (número), que JavaScript converte para `"5"` (sem `.0`), mas o Select espera `"5.0"` para corresponder ao `SelectItem`
  - Correção: Em `Mantenedora.js`, usar `Number(data.media_aprovacao).toFixed(1)` para garantir formato correto
  - **Testado**: API confirmou que valor foi salvo e carregado corretamente

- **Bug Corrigido - Livro de Promoção não usava Média de Aprovação da Mantenedora** (P1 - RESOLVIDO):
  - Problema: O Livro de Promoção usava valor hardcoded (6.0) em vez da média configurada na Mantenedora
  - Correções aplicadas em `Promotion.jsx`:
    1. Adicionado import do `useMantenedora` para acessar regras de aprovação
    2. Alterado cálculo da média de aprovação para usar `mantenedora?.media_aprovacao ?? 5.0`
    3. Implementado cálculo usando fórmula ponderada: `(B1×2 + B2×3 + B3×2 + B4×3) / 10`
    4. Implementadas regras de "Aprovação com Dependência" usando configuração da Mantenedora
    5. Adicionado "APROVADO COM DEPENDÊNCIA" ao contador de aprovados
  - **Testado**: Screenshot confirmou exibição correta com regras da Mantenedora

- **Feature PWA Offline - Fase 1 Básica** (P1 - IMPLEMENTADO):
  - Objetivo: Suporte offline para escolas em áreas rurais com internet intermitente
  - Implementado:
    1. **Service Worker** (`/public/sw.js`): Cache de assets, estratégia Network First para APIs
    2. **Manifest PWA** (`/public/manifest.json`): Instalação como app no celular/desktop
    3. **Ícones do App**: 8 tamanhos diferentes (72x72 até 512x512)
    4. **Página Offline** (`/public/offline.html`): Interface amigável quando sem conexão
    5. **Contexto Offline** (`OfflineContext.jsx`): Gerenciamento de estado de conexão
    6. **Componentes de Status** (`OfflineStatus.jsx`): Badge, banner e indicador flutuante
    7. **Integração no Layout**: Indicador visual de conexão no header
  - **Testado**: Service Worker ativo e registrado, manifest acessível

- **Feature PWA Offline - Fase 2 IndexedDB** (P1 - IMPLEMENTADO):
  - Objetivo: Armazenamento local de dados para lançamento offline de notas e frequência
  - Implementado:
    1. **Banco IndexedDB** (`/db/database.js`): Schema com Dexie.js para grades, attendance, students, classes, courses, schools
    2. **Fila de Sincronização** (`syncQueue`): Tabela para operações pendentes com controle de retries
    3. **Hook useOfflineGrades** (`/hooks/useOfflineGrades.js`): CRUD de notas com cache local e sync automático
    4. **Hook useOfflineAttendance** (`/hooks/useOfflineAttendance.js`): CRUD de frequência com cache local
    5. **Hook useOfflineSync** (`/hooks/useOfflineSync.js`): Sincronização de dados de referência (alunos, turmas, etc)
    6. **Serviço de Sync** (`/services/syncService.js`): Processamento da fila quando volta online
    7. **Integração OfflineContext**: Contador de pendências, eventos de sync, auto-sync ao reconectar
  - **Testado**: IndexedDB `SigescOfflineDB` criado com sucesso

- **Feature PWA Offline - Fase 4 Endpoints de Sincronização** (P0 - IMPLEMENTADO):
  - Objetivo: Criar endpoints de backend para sincronização bidirecional de dados
  - Implementado:
    1. **Router `/api/sync`** (`/backend/routers/sync.py`): Endpoints de sincronização
    2. **GET `/api/sync/status`**: Retorna contagens das coleções e dados do usuário
    3. **POST `/api/sync/push`**: Recebe operações pendentes do cliente (create/update/delete) e processa no servidor
    4. **POST `/api/sync/pull`**: Envia dados do servidor para popular cache local, com filtros opcionais (classId, academicYear, lastSync para delta sync)
    5. **syncService.js atualizado**: Frontend agora usa os novos endpoints em vez de APIs individuais
  - **Testado**: 17/17 testes passaram (iteration_9.json) - todos os endpoints funcionando
  - **Próximas Fases**:
    - Fase 5: UI de status de sincronização com indicador de progresso e lista de pendentes
  - Objetivo: Integrar a funcionalidade offline nas páginas de Notas e Frequência
  - Implementado:
    1. **OfflineManagementPanel** integrado em `Grades.js` e `Attendance.js`
    2. **Lógica offline-first em `loadGradesByClass`**: Busca da API quando online e atualiza cache local; lê do IndexedDB quando offline
    3. **Lógica offline-first em `saveGrades`**: Salva na API quando online; salva no IndexedDB e adiciona à fila de sincronização quando offline
    4. **Lógica offline-first em `loadAttendance`**: Mesmo padrão de notas
    5. **Lógica offline-first em `saveAttendance`**: Mesmo padrão de notas
    6. **Mensagens informativas**: Alerta quando dados são carregados do cache local
  - **Testado**: 100% testes de frontend passaram (iteration_7.json)
  - **Próximas Fases**:
    - Fase 4: Endpoints de sincronização no backend (`/api/sync/push`, `/api/sync/pull`)
    - Fase 5: UI de status de sincronização com indicador, lista de pendentes e botão de sync

- **Feature Notificações Push para Sincronização** (P2 - IMPLEMENTADO):
  - Objetivo: Alertar o professor quando a sincronização for concluída após voltar ao modo online
  - Implementado:
    1. **Serviço de Notificações** (`/services/notificationService.js`): Gerencia notificações do navegador
    2. **Tipos de notificações**: Sincronização concluída, erro de sync, conexão restaurada, conexão perdida
    3. **Botão "Ativar notificações"**: Adicionado ao OfflineManagementPanel para solicitar permissão
    4. **Integração com OfflineContext**: Envia notificações automaticamente nos eventos de sync e conexão
    5. **Estado de permissão**: Mostra "Notificações ativas" (verde) quando já tem permissão
  - **Testado**: Screenshot confirmou botão de ativação visível no painel

- **Melhoria de Segurança - Botão Limpar Cache** (P1 - IMPLEMENTADO):
  - Objetivo: Evitar perda acidental de dados não sincronizados
  - Implementado:
    1. **Validação de pendências**: Verifica se há itens na fila de sincronização antes de permitir limpeza
    2. **Confirmação dupla**: Quando há pendências, exige duas confirmações com avisos enfáticos
    3. **Indicador visual**: Botão fica laranja com ⚠️ quando há itens pendentes
    4. **Aviso de pendências**: Banner informativo aparece automaticamente quando há dados não sincronizados
    5. **Tooltip contextual**: Mostra quantidade de itens pendentes ao passar o mouse no botão
  - **Testado**: Screenshot confirmou comportamento correto do botão

- **Feature Pré-Matrícula Online** (P1 - IMPLEMENTADO):
  - Objetivo: Permitir que responsáveis realizem cadastro prévio de novos alunos online
  - Implementado:
    1. **Página pública `/pre-matricula`**: Lista escolas com pré-matrícula ativa, formulário completo com dados do aluno, responsável e endereço
    2. **Botão na página de login**: Botão verde "Pré-Matrícula" adicionado abaixo do formulário de login
    3. **Toggle na aba Permissão**: Seção "Pré-Matrícula Online" com toggle para ativar/desativar por escola
    4. **Modelo de dados**: `PreMatricula` com campos para aluno, responsável, endereço e status (pendente, analisando, aprovada, rejeitada, convertida)
    5. **Endpoints API**:
       - `GET /api/schools/pre-matricula` (público): Lista escolas com pré-matrícula ativa
       - `POST /api/pre-matricula` (público): Cria nova pré-matrícula
       - `GET /api/pre-matriculas` (autenticado): Lista pré-matrículas para gestão
       - `PUT /api/pre-matriculas/{id}/status` (autenticado): Atualiza status da pré-matrícula
  - **Testado**: 100% testes passaram (iteration_8.json) - 6 testes unitários + testes de frontend

### 2026-01-06 (Sessão 4)
- **Bug Crítico Corrigido - Lotação não reconhecida na Alocação** (P0 - RESOLVIDO):
  - Problema: Após criar uma lotação para um professor, o modal de alocação não reconhecia a nova lotação, mostrando mensagem "Este professor não possui lotação em nenhuma escola"
  - Causa raiz: O estado `professorSchools` no hook `useStaff.js` não era atualizado após salvar uma nova lotação
  - Correção no `useStaff.js`:
    - Adicionada chamada `loadProfessorSchools(staffIdSaved)` após salvar lotação (linhas 609-615)
    - Garante sincronização imediata do estado
  - Correção no `AlocacaoModal.js`:
    - Adicionado indicador de loading "Carregando lotações do professor..."
    - Mensagem de aviso melhorada com instruções claras
  - **Testado**: 100% aprovado - fluxo Lotação → Alocação funciona corretamente

- **Migração de Carga Horária por Série** (P1 - CONCLUÍDO):
  - Problema: Componentes curriculares com diferentes cargas horárias por nível de ensino não tinham o campo `carga_horaria_por_serie` preenchido
  - Solução: Script de migração `/app/backend/scripts/migration_fix_course_workload.py`
  - Resultado: 26 componentes atualizados com mapeamento correto de carga horária
  - Execução: `python scripts/migration_fix_course_workload.py [--dry-run] [--verbose]`
  - Script idempotente: pode ser executado múltiplas vezes sem efeitos colaterais

- **Bug Sincronização de Notas entre Documentos** (P0 - RESOLVIDO):
  - Problema: Notas lançadas apareciam na Ficha Individual mas não no Boletim e Livro de Promoção
  - Causa raiz 1 (Boletim): O parâmetro `academic_year` era string mas o banco salva como int
  - Causa raiz 2 (Livro de Promoção): O código esperava campos `period/grade` mas as notas usam `b1/b2/b3/b4`
  - Causa raiz 3 (Boletim): O cálculo da média usava média aritmética simples ao invés da fórmula ponderada
  - Correções no `server.py`:
    - Endpoint `/documents/boletim`: Convertido `academic_year` para int antes da query (linha 4729)
    - Endpoint `/documents/promotion`: Corrigido mapeamento de notas para usar `b1/b2/b3/b4` (linhas 5484-5499)
  - Correções no `pdf_generator.py`:
    - Boletim: Corrigido mapeamento de notas para usar `grade.get('b1')` diretamente
    - Boletim: Implementada fórmula ponderada `(B1×2 + B2×3 + B3×2 + B4×3) / 10`
    - Boletim: Implementada lógica de recuperação - substitui menor nota do semestre (se notas iguais, substitui a de maior peso)

### 2026-01-05 (Sessão 3)
- **Padronização da Exibição de Turmas** (P0 - CONCLUÍDO):
  - Solicitação: "Em todo o sistema, exibir apenas o nome da turma, sem série/etapa e turno"
  - Arquivos modificados:
    - `Classes.js`: Removidas colunas "Nível de Ensino", "Série/Etapa" e "Turno" da tabela
    - `SchoolsComplete.js`: Removidas colunas "Série/Etapa" e "Turno" da tabela de turmas da escola
  - Arquivos já corretos (sem alteração necessária):
    - `StudentsComplete.js`: getClassName já retorna apenas o nome
    - `Enrollments.js`: getClassName já retorna apenas o nome
    - `Grades.js`: seletor usa cls.name
    - `Attendance.js`: seletor usa c.name
    - `Promotion.jsx`: seletor usa cls.name
  - **Testado**: 100% aprovado em todas as páginas

- **Geração de PDF do Livro de Promoção** (P0 - CONCLUÍDO):
  - Novo endpoint: `GET /api/documents/promotion/{class_id}?academic_year=XXXX`
  - Nova função: `generate_livro_promocao_pdf()` em `pdf_generator.py`
  - Estrutura do PDF (2 páginas, formato paisagem):
    - **Cabeçalho institucional** (igual à Ficha Individual): Logo + Mantenedora + Secretaria + "LIVRO DE PROMOÇÃO"
    - **Info boxes**: Escola, Turma, Ano/Etapa, Turno, Página (01/02)
    - **Página 1**: Notas 1º Bimestre + 2º Bimestre + Recuperação 1º Semestre
    - **Página 2**: Notas 3º Bimestre + 4º Bimestre + Recuperação 2º Semestre + Total + Média + Resultado
    - **Assinaturas**: Secretário(a) e Diretor(a) com data por extenso
  - Resultado colorido: Verde (Aprovado), Vermelho (Reprovado), Cinza (Desistente), Amarelo (Transferido)
  - **Testado**: 100% aprovado (16 testes backend + frontend)

### 2026-01-04 (Sessão 2)
- **Correção Crítica - Backend não iniciava** (P0 - RESOLVIDO):
  - Erro: `NameError: name 'Dict' is not defined` em models.py
  - Solução: Adicionado `Dict` ao import de typing

- **Correção Página Logs de Auditoria** (P2 - RESOLVIDO):
  - Problema 1: Endpoint `/api/mantenedora` requeria autenticação desnecessária
  - Problema 2: `AuditLogs.jsx` usava `token` ao invés de `accessToken` do AuthContext
  - Solução: Removida autenticação do endpoint mantenedora e corrigido nome da variável

- **Correção Carga Horária por Série** (P0 - IMPLEMENTADO):
  - O `pdf_generator.py` agora usa `carga_horaria_por_serie` quando disponível
  - Funções corrigidas: `generate_boletim_pdf` e `generate_ficha_individual_pdf`
  - Lógica: Se o componente tem `carga_horaria_por_serie`, busca pela série do aluno

- **Refatoração Backend - Módulos** (P2 - EM PROGRESSO):
  - Criados routers modulares em `/app/backend/routers/`:
    - `auth.py` (216 linhas) - Autenticação
    - `users.py` (106 linhas) - CRUD de usuários
    - `schools.py` (100 linhas) - CRUD de escolas
    - `courses.py` (100 linhas) - CRUD de componentes curriculares
    - `classes.py` (128 linhas) - CRUD de turmas
    - `guardians.py` (92 linhas) - CRUD de responsáveis
    - `enrollments.py` (182 linhas) - CRUD de matrículas
  - **Redução**: server.py de 7.185 → 6.610 linhas (-575 linhas, -8%)

- **Refatoração Frontend - Hooks** (P3 - EM PROGRESSO):
  - Criados hooks reutilizáveis em `/app/frontend/src/hooks/`:
    - `useSchools.js` (120 linhas) - Gestão de escolas
    - `useSchoolStaff.js` (73 linhas) - Gestão de staff
    - `useCalendarioLetivo.js` (98 linhas) - Calendário letivo
    - `useSchoolForm.js` (262 linhas) - Formulário de escola
  - Total: 553 linhas de lógica extraída para reutilização

### 2026-01-04 (Sessão 1)
- **Sistema de Auditoria Completo** (P0 - IMPLEMENTADO):
  - Serviço `audit_service.py` para rastrear alterações críticas
  - Auditoria em: login, alunos, notas, frequência, matrículas, lotações
  - Página frontend `/admin/audit-logs` (apenas admin)

- **Correção Bug Componentes no Boletim** (P0 - RESOLVIDO):
  - Problema: Componentes curriculares duplicados com grade_levels diferentes
  - Solução: Endpoint `/api/maintenance/consolidate-courses` para unificar duplicados

- **Limpeza de Dados Órfãos**:
  - `GET /api/maintenance/orphan-check` - Verifica dados órfãos
  - `DELETE /api/maintenance/orphan-cleanup` - Remove dados órfãos

- **Índices MongoDB Otimizados** (P2 - IMPLEMENTADO)
- **Rate Limiting** (P2 - IMPLEMENTADO)
- **Início da Refatoração em Módulos**
- **Correção Visual do Calendário Anual**
- **Bloqueio por Data Limite de Edição**
- **Indicadores Visuais de Bloqueio por Bimestre**

### 2026-01-03
- Ordenação de Componentes Curriculares
- Condicionais para Aprovação (Mantenedora)
- Lógica de Resultado Final
- Dias Letivos por Bimestre
- Cálculo de Frequência no Boletim

## Backlog Priorizado

### P0 (Crítico)
- [x] ~~Sistema de Auditoria~~ (CONCLUÍDO)
- [x] ~~Bug componentes ausentes no Boletim~~ (RESOLVIDO - duplicados consolidados)
- [x] ~~Correção carga horária por série~~ (CONCLUÍDO 2026-01-04)
- [x] ~~Bug Lotação não reconhecida na Alocação~~ (RESOLVIDO 2026-01-06)
- [x] ~~Bug Lógica de Aprovação Ignorava Média 0.0~~ (RESOLVIDO 2026-01-06)
- [x] ~~Bug Lógica de Aprovação Ignorava Componentes Sem Nota~~ (RESOLVIDO 2026-01-06)

### P1 (Alto)
- [x] ~~Bloqueio por data limite de edição~~ (CONCLUÍDO)
- [x] ~~Verificar bug "Gerenciar Lotações"~~ (RESOLVIDO 2026-01-06)
- [x] ~~Dados de carga horária incorretos no banco~~ (MIGRAÇÃO CONCLUÍDA 2026-01-06)

### P2 (Médio)
- [x] ~~Índices MongoDB otimizados~~ (CONCLUÍDO)
- [x] ~~Rate limiting~~ (CONCLUÍDO)
- [x] ~~Limpeza de dados órfãos~~ (CONCLUÍDO - endpoints criados)
- [x] ~~Página Logs de Auditoria não carregava~~ (RESOLVIDO 2026-01-04)
- [~] Refatoração do server.py em módulos (EM PROGRESSO - 5 routers criados)

### P3 (Baixo)
- [~] Refatorar SchoolsComplete.js (EM PROGRESSO - hooks criados)
- [ ] Refatorar StudentsComplete.js
- [ ] Refatorar Calendar.js

## Arquitetura

### Backend
- FastAPI + Motor (MongoDB async) + SlowAPI (rate limiting)
- Estrutura:
  - `server.py` - Endpoints principais (em refatoração)
  - `routers/` - Routers modulares
  - `audit_service.py` - Serviço de auditoria
  - `grade_calculator.py` - Lógica de cálculo de notas
  - `pdf_generator.py` - Geração de documentos
  - `cleanup_orphans.py` - Manutenção de dados

### Frontend
- React + Vite + TailwindCSS + Shadcn/UI

## Credenciais de Teste
- Admin: gutenberg@sigesc.com / @Celta2007
- Coordenador: ricleidegoncalves@gmail.com / 007724

### P1 (Alto)
- [x] ~~Implementar bloqueio por data limite de edição~~ (CONCLUÍDO 2026-01-04)
- [x] ~~Verificar bug de "Gerenciar Lotações" não salvando~~ (RESOLVIDO 2026-01-06)
- [x] ~~Dados de carga horária incorretos no banco~~ (MIGRAÇÃO CONCLUÍDA 2026-01-06)

### P2 (Médio)
- [ ] Limpar dados órfãos de lotações

### P3 (Baixo)
- [ ] Refatorar StudentsComplete.js
- [ ] Refatorar Calendar.js
- [ ] Refatorar pdf_generator.py
- [ ] Deletar arquivo obsoleto Courses.js

## Arquitetura

### Backend
- FastAPI + Motor (MongoDB async)
- Arquivos principais: server.py, models.py, pdf_generator.py, grade_calculator.py

### Frontend
- React + Vite + TailwindCSS + Shadcn/UI
- Contextos: AuthContext, MantenedoraContext

### Banco de Dados
- MongoDB
- Coleções: users, schools, classes, students, courses, grades, attendance, mantenedora, calendario_letivo, etc.

## Credenciais de Teste
- Admin: gutenberg@sigesc.com / @Celta2007
- Coordenador: ricleidegoncalves@gmail.com / 007724
