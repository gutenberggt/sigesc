# SIGESC - Sistema Integrado de Gestao Escolar

## Problema Original
Sistema full-stack (React + FastAPI + MongoDB) para gestao escolar municipal.

## Arquitetura
- **Frontend:** React com Shadcn/UI, react-router-dom, React.lazy (code splitting)
- **Backend:** FastAPI com Motor (MongoDB async), cache in-memory TTL, arquitetura modular de roteadores
- **DB:** MongoDB

## Implementado

### Sessao 09/03/2026 (Fork 2) - Finalizacao da Refatoracao Backend

**P0 - Refatoracao Backend Fase 2 (DONE):**
- Registrados todos os 17+ roteadores extraidos no server.py
- Criados modulos utilitarios compartilhados:
  - `utils/connection_manager.py` - ConnectionManager e ActiveSessionsTracker
  - `utils/academic_year.py` - Validadores de ano letivo e bimestre (factory pattern)
- Corrigido `debug.py` - removido codigo duplicado, @app.get → @router.get
- Corrigido `audit_logs.py` - removido codigo de setup de outros roteadores
- Corrigido `social.py` - adicionado connection_manager via kwargs
- Corrigido `analytics.py` - campo 'name' → 'full_name' para students
- Teste de regressao completo: 95.8% backend, 100% frontend

### Sessao 09/03/2026 - Otimizacao de Performance e Refatoracao

**P0 - Paginacao Server-Side (DONE):**
- Backend GET /api/students com paginacao (page, page_size, school_id, class_id, status, search)
- Frontend StudentsComplete.js refatorado: removido offlineStudentsService e filtragem client-side
- Busca server-side com debounce 500ms, controles de paginacao, skeleton loading

**P1 - Cache Server-Side (DONE):**
- TTLCache in-memory: Escolas (3min), Turmas (2min), Cursos (5min)
- Invalidacao automatica no create/update/delete

**P1 - Lazy Loading React (DONE):**
- React.lazy + Suspense para todas as 25+ paginas

**P2 - Refatoracao Backend Fase 1 (DONE):**
- Auth routes movidas para routers/auth.py
- CPF validation movido para routers/students.py
- offlineStudentsService.js removido

### Sessao 08-09/03/2026 - Turmas Multisseriadas
- Selecao e exibicao de serie individual (student_series) em turmas multisseriadas

## Estrutura Backend (Modular)
```
backend/
├── server.py (central - registro de roteadores, middleware, websocket)
├── routers/
│   ├── __init__.py
│   ├── admin_messages.py, announcements.py, assignments.py
│   ├── attendance.py, attendance_ext.py, audit_logs.py
│   ├── auth.py, calendar.py, calendar_ext.py
│   ├── class_details.py, class_schedule.py, classes.py
│   ├── courses.py, debug.py, diary_dashboard.py
│   ├── documents.py, enrollments.py, grades.py
│   ├── guardians.py, learning_objects.py, maintenance.py
│   ├── mantenedora.py, medical_certificates.py, notifications.py
│   ├── pre_matricula.py, professor.py, profiles.py
│   ├── schools.py, social.py, staff.py
│   ├── students.py, sync.py, uploads.py, users.py
│   └── aee.py
└── utils/
    ├── cache.py, connection_manager.py, academic_year.py
    └── text_utils.py
```

## Issues Pendentes
- P1: Alterar carga horaria de componentes curriculares em producao (BLOCKED - dados apenas em producao)
- P2: Dashboard Analitico (pendente verificacao do usuario)
- NOTA: Credenciais SEMED3 (semed3@sigesc.com / semed123) retornando 401 - senha pode ter sido alterada

## Tarefas Futuras
- P2: Envio de e-mail na pre-matricula

## Bug Recorrente Conhecido
- format_data_uppercase causa falhas com campos Literal do Pydantic
- Solucao: adicionar @validator no modelo Pydantic

## Credenciais
- Admin: gutenberg@sigesc.com / @Celta2007
- SEMED 3: semed3@sigesc.com / semed123 (pode estar desatualizada)
