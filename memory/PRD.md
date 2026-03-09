# SIGESC - Sistema Integrado de Gestao Escolar

## Problema Original
Sistema full-stack (React + FastAPI + MongoDB) para gestao escolar municipal.

## Arquitetura
- **Frontend:** React com Shadcn/UI, react-router-dom, React.lazy (code splitting)
- **Backend:** FastAPI com Motor (MongoDB async), cache in-memory TTL, arquitetura modular de roteadores
- **DB:** MongoDB

## Implementado

### Sessao 09/03/2026 (Fork 2) - Finalizacao da Refatoracao e Limpeza

**P0 - Refatoracao Backend Fase 2 (DONE):**
- Registrados todos os 17+ roteadores extraidos no server.py
- Criados modulos utilitarios compartilhados:
  - `utils/connection_manager.py` - ConnectionManager e ActiveSessionsTracker
  - `utils/academic_year.py` - Validadores de ano letivo e bimestre (factory pattern)
- Corrigidos bugs: debug.py, audit_logs.py, social.py, analytics.py
- Teste de regressao: 95.8% backend, 100% frontend

**Limpeza e Organizacao (DONE):**
- 16 roteadores: imports nao utilizados removidos (ftplib, re, io, os, etc.)
- 14 roteadores: kwargs blocks nao utilizados removidos
- server.py: imports reduzidos de ~67 linhas para ~19 linhas
- Endpoints movidos de server.py para roteadores:
  - sandbox/status, sandbox/reset → routers/sandbox.py
  - admin/migrate-uppercase, admin/online-users → routers/admin.py
- Arquivos obsoletos removidos: app_factory.py, server_backup.py
- Scripts utilitarios movidos para backend/scripts/
- server.py reduzido de ~7600 → 488 linhas (93.6% reducao)

### Sessao 09/03/2026 - Otimizacao de Performance e Refatoracao

**P0 - Paginacao Server-Side (DONE)**
**P1 - Cache Server-Side (DONE)**
**P1 - Lazy Loading React (DONE)**
**P2 - Refatoracao Backend Fase 1 (DONE)**

### Sessao 08-09/03/2026 - Turmas Multisseriadas (DONE)

## Estrutura Backend (Final)
```
backend/
├── server.py (488 linhas - registro de roteadores, middleware, websocket, health)
├── routers/ (39 arquivos)
│   ├── admin.py, admin_messages.py, aee.py, analytics.py
│   ├── announcements.py, assignments.py, attendance.py, attendance_ext.py
│   ├── audit_logs.py, auth.py, calendar.py, calendar_ext.py
│   ├── class_details.py, class_schedule.py, classes.py, courses.py
│   ├── debug.py, diary_dashboard.py, documents.py, enrollments.py
│   ├── grades.py, guardians.py, learning_objects.py, maintenance.py
│   ├── mantenedora.py, medical_certificates.py, notifications.py
│   ├── pre_matricula.py, professor.py, profiles.py, sandbox.py
│   ├── schools.py, social.py, staff.py, students.py
│   ├── sync.py, uploads.py, users.py
│   └── __init__.py
├── utils/ (cache.py, connection_manager.py, academic_year.py, text_utils.py)
└── scripts/ (cadastrar_escolas.py, cleanup_orphans.py, etc.)
```

## Issues Pendentes
- P1: Alterar carga horaria de componentes curriculares em producao (BLOCKED)
- P2: Dashboard Analitico (pendente verificacao do usuario)
- NOTA: Credenciais SEMED3 (semed3@sigesc.com / semed123) retornando 401

## Tarefas Futuras
- P2: Envio de e-mail na pre-matricula

## Bug Recorrente Conhecido
- format_data_uppercase causa falhas com campos Literal do Pydantic
- Solucao: adicionar @validator no modelo Pydantic

## Credenciais
- Admin: gutenberg@sigesc.com / @Celta2007
- SEMED 3: semed3@sigesc.com / semed123 (pode estar desatualizada)
