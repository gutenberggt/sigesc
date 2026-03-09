# SIGESC - Sistema Integrado de Gestao Escolar

## Problema Original
Sistema full-stack (React + FastAPI + MongoDB) para gestao escolar municipal.

## Arquitetura
- **Frontend:** React com Shadcn/UI, react-router-dom
- **Backend:** FastAPI com Motor (MongoDB async)
- **DB:** MongoDB

## Implementado

### Sessao 09/03/2026 - Otimizacao de Performance P0
31. **Paginacao Server-Side na Lista de Alunos (DONE):**
    - Backend GET /api/students ja suportava paginacao (page, page_size, school_id, class_id, status, search)
    - Frontend StudentsComplete.js refatorado: removido offlineStudentsService, carregamento client-side e dropdowns de sugestao
    - Agora usa busca server-side paginada com debounce de 500ms na busca por nome/CPF
    - Controles de paginacao (Primeira/Anterior/Proxima/Ultima) com total do servidor
    - Removidos indicadores de modo offline (CloudOff, Cloud, sincronizacao)
    - Corrigido Dashboard.js, AnalyticsDashboard.jsx, Grades.js, Enrollments.js, Promotion.jsx, AssocialDashboard.js, Students.js, Guardians.js, useOfflineSync.js para lidar com novo formato de resposta paginada {items, total, page, page_size, total_pages}
    - Testes: 100% backend (9/9), 100% frontend

### Sessao 08-09/03/2026 - Turmas Multisseriadas
27-30. Selecao e exibicao de serie individual (student_series) em turmas multisseriadas

## Regras de Negocio - student_series
- Cada aluno tem seu student_series individual armazenado na enrollment
- Para turma nao-multisseriada: auto-set para grade_level da turma
- Para turma multisseriada: usuario escolhe via dropdown
- Listagem de alunos: backend busca student_series das enrollments ativas via batch query
- Detalhes da turma: contagem por serie usa comparacao case-insensitive
- Fallback: se student_series nao definido e turma nao-multi, usa grade_level; se multi, mostra '-'

## Issues Pendentes
- P1: Alterar carga horaria de componentes curriculares em producao (BLOCKED - dados apenas em producao)
- P2: Dashboard Analitico (pendente verificacao do usuario)

## Tarefas Futuras
- P1: Cache server-side (Redis/memcached) para dados frequentemente acessados
- P1: Lazy loading para componentes pesados (React.lazy)
- P2: Refatorar StudentsComplete.js (componente monolitico)
- P2: Envio de e-mail na pre-matricula
- P2: Refatoracao backend (mover rotas do server.py)
- P2: Remover offlineStudentsService.js (agora obsoleto)

## Bug Recorrente Conhecido
- format_data_uppercase (backend/utils/text_utils.py) causa falhas com campos Literal do Pydantic
- Solucao: adicionar @validator no modelo Pydantic para normalizar para minusculas

## Credenciais
- Admin: gutenberg@sigesc.com / @Celta2007
- SEMED 3: semed3@sigesc.com / semed123
