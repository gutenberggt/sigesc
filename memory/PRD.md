# SIGESC - Sistema Integrado de Gestao Escolar

## Problema Original
Sistema full-stack (React + FastAPI + MongoDB) para gestao escolar municipal.

## Arquitetura
- **Frontend:** React com Shadcn/UI, react-router-dom, React.lazy (code splitting)
- **Backend:** FastAPI com Motor (MongoDB async), cache in-memory TTL
- **DB:** MongoDB

## Implementado

### Sessao 09/03/2026 - Otimizacao de Performance e Refatoracao

**P0 - Paginacao Server-Side (DONE):**
- Backend GET /api/students com paginacao (page, page_size, school_id, class_id, status, search)
- Frontend StudentsComplete.js refatorado: removido offlineStudentsService e filtragem client-side
- Busca server-side com debounce 500ms, controles de paginacao, skeleton loading
- Corrigidos 8 arquivos para formato paginado

**P1 - Cache Server-Side (DONE):**
- TTLCache in-memory: Escolas (3min), Turmas (2min), Cursos (5min)
- Invalidacao automatica no create/update/delete

**P1 - Lazy Loading React (DONE):**
- React.lazy + Suspense para todas as 25+ paginas

**P2 - Refatoracao Backend (DONE - Fase 1):**
- server.py reduzido de 7578 → 5983 linhas (-21%, -1595 linhas)
- Removidas 1182 linhas de rotas duplicadas (dead code)
- Auth routes (register, logout, logout-all, permissions) movidas para routers/auth.py
- CPF validation (validate-cpf, check-cpf-duplicate) movido para routers/students.py
- Auth router incluido no app via setup_auth_router
- offlineStudentsService.js removido

### Sessao 08-09/03/2026 - Turmas Multisseriadas
- Selecao e exibicao de serie individual (student_series) em turmas multisseriadas

## Issues Pendentes
- P1: Alterar carga horaria de componentes curriculares em producao (BLOCKED - dados apenas em producao)
- P2: Dashboard Analitico (pendente verificacao do usuario)

## Tarefas Futuras
- P2: Refatoracao backend Fase 2 - mover 86 rotas restantes do api_router para routers dedicados:
  - Class details → classes.py
  - Calendar extended (periodos, status-edicao) → calendar.py
  - Attendance extended (frequency, pdf, alerts) → attendance.py
  - Staff assignments → staff.py
  - Criar novos: documents.py, professor.py, learning_objects.py, connections.py, pre_matricula.py, notifications.py, maintenance.py, mantenedora.py, audit_logs.py
- P2: Envio de e-mail na pre-matricula

## Bug Recorrente Conhecido
- format_data_uppercase causa falhas com campos Literal do Pydantic
- Solucao: adicionar @validator no modelo Pydantic

## Credenciais
- Admin: gutenberg@sigesc.com / @Celta2007
- SEMED 3: semed3@sigesc.com / semed123
