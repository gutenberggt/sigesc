# SIGESC - Sistema Integrado de Gestao Escolar

## Problema Original
Sistema full-stack (React + FastAPI + MongoDB) para gestao escolar municipal.

## Arquitetura
- **Frontend:** React com Shadcn/UI, react-router-dom, React.lazy (code splitting)
- **Backend:** FastAPI com Motor (MongoDB async), cache in-memory TTL
- **DB:** MongoDB

## Implementado

### Sessao 09/03/2026 - Otimizacao de Performance

**P0 - Paginacao Server-Side (DONE):**
- Backend GET /api/students com paginacao (page, page_size, school_id, class_id, status, search)
- Frontend StudentsComplete.js refatorado: removido offlineStudentsService e filtragem client-side
- Busca server-side com debounce 500ms, controles de paginacao, skeleton loading
- Corrigidos 8 arquivos para lidar com formato paginado {items, total, page, page_size, total_pages}

**P1 - Cache Server-Side (DONE):**
- Utilitario TTLCache in-memory em /app/backend/utils/cache.py
- Escolas (3min TTL), Turmas (2min TTL), Componentes Curriculares (5min TTL)
- Invalidacao automatica no create/update/delete

**P1 - Lazy Loading React (DONE):**
- React.lazy + Suspense em App.js para todas as 25+ paginas
- Apenas Login carrega no bundle inicial
- PageLoader com skeleton como fallback durante carregamento

**UI - Skeleton Loading (DONE):**
- Tabela de alunos com 8 skeleton rows durante carregamento

### Sessao 08-09/03/2026 - Turmas Multisseriadas
27-30. Selecao e exibicao de serie individual (student_series) em turmas multisseriadas

## Regras de Negocio - student_series
- Cada aluno tem seu student_series individual armazenado na enrollment
- Para turma nao-multisseriada: auto-set para grade_level da turma
- Para turma multisseriada: usuario escolhe via dropdown

## Issues Pendentes
- P1: Alterar carga horaria de componentes curriculares em producao (BLOCKED - dados apenas em producao)
- P2: Dashboard Analitico (pendente verificacao do usuario)

## Tarefas Futuras
- P2: Remover offlineStudentsService.js (agora obsoleto)
- P2: Envio de e-mail na pre-matricula
- P2: Refatoracao backend (mover rotas do server.py)

## Bug Recorrente Conhecido
- format_data_uppercase causa falhas com campos Literal do Pydantic
- Solucao: adicionar @validator no modelo Pydantic

## Credenciais
- Admin: gutenberg@sigesc.com / @Celta2007
- SEMED 3: semed3@sigesc.com / semed123
