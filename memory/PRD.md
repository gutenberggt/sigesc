# SIGESC - Sistema de Gestão Escolar

## Problema Original
Sistema de gestão escolar para a Secretaria Municipal de Educação, com funcionalidades de:
- Cadastro de escolas, turmas, alunos, professores
- Registro de notas e frequência
- Geração de documentos (boletins, fichas individuais, certificados, declarações)
- Controle de ano letivo
- Gestão de lotações de servidores

## Implementações Recentes

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
