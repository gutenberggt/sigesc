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
  - Novo serviço `audit_service.py` para rastrear alterações críticas
  - Modelo `AuditLog` para armazenar registros
  - Auditoria integrada em:
    - Login (sucesso e falha)
    - Criação, edição e exclusão de alunos
    - Edição de notas em lote
  - Novos endpoints:
    - `GET /api/audit-logs` - Lista logs com filtros
    - `GET /api/audit-logs/user/{id}` - Histórico por usuário
    - `GET /api/audit-logs/document/{collection}/{id}` - Histórico de documento
    - `GET /api/audit-logs/critical` - Eventos críticos
    - `GET /api/audit-logs/stats` - Estatísticas
  - Nova página frontend `/admin/audit-logs` com:
    - Tabela de logs com paginação
    - Filtros por ação, coleção, severidade
    - Estatísticas de eventos
  - Acessível no Dashboard via botão "Auditoria"

- **Correção Visual do Calendário Anual**:
  - Cores uniformizadas: dias letivos e sábados letivos com mesma cor verde (bg-green-100)
  - Removida legenda duplicada, mantida apenas a legenda original de tipos de eventos

- **Bloqueio por Data Limite de Edição** (P1 - IMPLEMENTADO):
  - Nova função `check_bimestre_edit_deadline()` verifica data limite por bimestre
  - Verificação aplicada em: `/api/grades/batch`, `/api/attendance`, `/api/learning-objects`
  - Novo endpoint `/api/calendario-letivo/{ano}/status-edicao`

- **Indicadores Visuais de Bloqueio por Bimestre** (IMPLEMENTADO):
  - Novo hook `useBimestreEditStatus` 
  - Integrado nas páginas de Notas e Frequência

### 2026-01-03
- Ordenação de Componentes Curriculares
- Condicionais para Aprovação (Mantenedora)
- Lógica de Resultado Final
- Dias Letivos por Bimestre
- Cálculo de Frequência no Boletim

## Backlog Priorizado

### P0 (Crítico)
- [x] ~~Sistema de Auditoria~~ (CONCLUÍDO 2026-01-04)
- [ ] Investigar bug de componentes ausentes no Boletim

### P1 (Alto)
- [x] ~~Bloqueio por data limite de edição~~ (CONCLUÍDO 2026-01-04)
- [ ] Verificar bug de "Gerenciar Lotações" não salvando

### P2 (Médio)
- [ ] Rate limiting para endpoints sensíveis
- [ ] Índices MongoDB otimizados
- [ ] Limpar dados órfãos de lotações

### P3 (Baixo)
- [ ] Refatorar server.py em módulos
- [ ] Refatorar StudentsComplete.js
- [ ] Refatorar Calendar.js

## Arquitetura

### Backend
- FastAPI + Motor (MongoDB async)
- Arquivos: server.py, models.py, pdf_generator.py, grade_calculator.py, audit_service.py

### Frontend
- React + Vite + TailwindCSS + Shadcn/UI
- Páginas novas: AuditLogs.jsx
- Hooks novos: useBimestreEditStatus.js
- Componentes novos: BimestreStatus.jsx

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
