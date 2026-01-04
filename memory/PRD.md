# SIGESC - Sistema de Gestão Escolar

## Problema Original
Sistema de gestão escolar para a Secretaria Municipal de Educação, com funcionalidades de:
- Cadastro de escolas, turmas, alunos, professores
- Registro de notas e frequência
- Geração de documentos (boletins, fichas individuais, certificados, declarações)
- Controle de ano letivo
- Gestão de lotações de servidores

## Implementações Recentes

### 2026-01-04
- **Sistema de Auditoria Completo** (P0 - IMPLEMENTADO):
  - Serviço `audit_service.py` para rastrear alterações críticas
  - Auditoria integrada em: login, alunos, notas, frequência, matrículas, lotações
  - Endpoints de consulta, estatísticas e eventos críticos
  - Página frontend `/admin/audit-logs` (apenas admin)

- **Endpoint de Limpeza de Dados Órfãos**:
  - `GET /api/maintenance/orphan-check` - Verifica dados órfãos
  - `DELETE /api/maintenance/orphan-cleanup` - Remove dados órfãos
  - Script standalone `cleanup_orphans.py` para execução manual

- **Início da Refatoração em Módulos**:
  - Criada estrutura `/app/backend/routers/`
  - Router de autenticação separado (modelo para demais)

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
- [x] ~~Limpeza de dados órfãos~~ (CONCLUÍDO)
- [ ] Investigar bug de componentes ausentes no Boletim

### P1 (Alto)
- [x] ~~Bloqueio por data limite de edição~~ (CONCLUÍDO)
- [ ] Verificar bug de "Gerenciar Lotações" não salvando

### P2 (Médio)
- [ ] Rate limiting para endpoints sensíveis
- [ ] Índices MongoDB otimizados
- [ ] Continuar refatoração do server.py em módulos

### P3 (Baixo)
- [ ] Refatorar StudentsComplete.js
- [ ] Refatorar Calendar.js

## Arquitetura

### Backend
- FastAPI + Motor (MongoDB async)
- Estrutura:
  - `server.py` - Endpoints principais (em refatoração)
  - `routers/` - Routers modulares (auth.py)
  - `audit_service.py` - Serviço de auditoria
  - `grade_calculator.py` - Lógica de cálculo de notas
  - `pdf_generator.py` - Geração de documentos
  - `cleanup_orphans.py` - Manutenção de dados

### Frontend
- React + Vite + TailwindCSS + Shadcn/UI
- Páginas: AuditLogs.jsx
- Hooks: useBimestreEditStatus.js
- Componentes: BimestreStatus.jsx

## Credenciais de Teste
- Admin: gutenberg@sigesc.com / @Celta2007
- Coordenador: ricleidegoncalves@gmail.com / 007724

### P1 (Alto)
- [x] ~~Implementar bloqueio por data limite de edição~~ (CONCLUÍDO 2026-01-04)
- [ ] Verificar bug de "Gerenciar Lotações" não salvando

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
