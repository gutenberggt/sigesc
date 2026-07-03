# ENTREGA 06 — APIs

> Auditoria READ-ONLY · Jun/2026. **574 endpoints** em **89 routers**, todos sob
> prefixo **`/api`**. Classificação 🟢🟡🔴⚫.

## 1. Panorama quantitativo
| Verbo | Qtde |
|---|---|
| GET | 319 |
| POST | 158 |
| PUT | 54 |
| DELETE | 43 |
| **Total** | **574** |

- **Autenticação:** JWT (cookie HttpOnly `sigesc_access` → header `Bearer` → `?token=`),
  validado por `AuthMiddleware.get_current_user` em praticamente todos os endpoints.
- **Autorização:** **50 routers** usam `require_roles`/`require_permission`
  (RBAC + matriz de overrides). Os demais usam `get_current_user` (qualquer autenticado)
  e/ou filtragem tenant/escola no corpo do handler.
- **Rate limiting:** `slowapi` configurado globalmente; uso explícito de `@limiter.limit`
  hoje é pontual (**1 router**) — oportunidade de ampliar em endpoints sensíveis (login, export).
- **Tenant scope:** RLS aplicado nas queries (não por decorator), fail-closed.

## 2. Principais grupos de endpoints (amostra por domínio)
| Domínio | Router(s) | ~Endpoints | Auth | Consumidor (frontend) |
|---|---|---|---|---|
| Auth/sessão | `auth.py` | 11 | público (login/register) + JWT | `AuthContext`, `Login` |
| Alunos | `students.py` | 18 | JWT + RBAC + tenant | `Students*`, `Promotion` |
| Frequência | `attendance.py`(16) + `attendance_ext.py` | ~25 | JWT + RBAC | `Attendance`, offline hooks |
| Notas | `grades.py` | 8 | JWT + RBAC | `Grades`, `GradesContext` |
| Turmas | `classes.py`(7) + `class_details.py` + `class_schedule.py` | ~20 | JWT + RBAC | `Classes` |
| Matrículas | `enrollments.py` | 6 | JWT | `Enrollments`, `Promotion` |
| Escolas | `schools.py` | 7 | JWT + tenant | `Schools*` |
| Documentos/PDF | `documents.py`(14) + `bulletins`/`history_pdf`/`render_jobs`/`verifiable_docs` | ~50 | JWT + `?token=` p/ PDF | `SchoolDocuments`, `Promotion`, viewers |
| Professor (portal) | `professor.py` | 6 | `require_roles(['professor'])` | `ProfessorDashboard` |
| Aluno/Responsável | `student_portal.py`, `admin_student_users.py` | ~15 | JWT | `AlunoDashboard`, `BoletimAluno` |
| Analytics/PME | `analytics.py`(11) + `pme_anos_finais.py` + `monthly_reports.py` | ~35 | JWT + RBAC | dashboards |
| PMPI/risco/IA | `pmpi_engine.py`(10) + `pmpi_ai.py` + `pmpi.py` + `interventions.py` | ~40 | JWT + RBAC | `PmpiEngine`, `Interventions` |
| Transferência | `school_transfer.py` | ~12 | `super_admin` + re-auth | wizard/painel |
| Multi-tenant | `mantenedoras.py`, `tenant_admin.py`, `mantenedora.py` | ~30 | `super_admin`/`gerente` | `Mantenedoras`, `TenantAdmin` |
| RH/Folha | `hr.py`, `staff.py`, `assignments.py` | ~40 | JWT + RBAC | `HRPayroll`, `Staff` |
| Manutenção/migração | `maintenance.py`, `grade_legacy_migration.py`, `dedup_enrollments.py`, `student_series_backfill.py` | ~25 | `super_admin` + `with_critical_mutation` | `AdminTools` |

## 3. Endpoints públicos (sem JWT) — 🟢
- `POST /api/auth/login`, `POST /api/auth/register`, `POST /api/auth/refresh`.
- Verificação pública de documentos: `public_verify.py`, `verifiable_docs.py`
  (rotas `/v/{token}`, verificação de boletim/diário/histórico via QR).
- `GET /api/health` (healthcheck do container).
- Branding público de tenant (`/api/tenant/branding/public`).

## 4. Convenções e padrões observados
- **Setup de router injetável:** muitos routers expõem `setup_router(db, audit_service,
  sandbox_db, **kwargs)` — permite **sandbox** (homologação isolada) trocando o `db`.
- **PDFs assíncronos:** padrão job (`POST .../jobs/...` → `GET .../jobs/{id}/status` →
  `GET .../jobs/{id}/download`) para não estourar timeout de proxy.
- **Mutações críticas:** `with_critical_mutation` (idempotency-key + lock + audit + rollback).
- **Idempotência:** operações destrutivas retornam o mesmo protocolo em replays.

## 5. Riscos / oportunidades (API)
- 🟡 **Cobertura de RBAC desigual:** ~39 routers dependem só de `get_current_user` +
  filtragem manual. Recomenda-se auditar caso a caso (o bug histórico do `curriculum_v2`
  `require_permission(None)` mostra o risco de padrões locais).
- 🟡 **Rate limiting subutilizado:** ampliar em login, refresh, exports e geração de PDF.
- 🟡 **Documentação viva de contrato:** não há OpenAPI curado/publicado; FastAPI gera
  `/docs`, mas convém versionar um contrato para consumidores externos (futuro MEC/BI).
- 🟢 **Segurança de operações destrutivas:** transfer/rollback/migrações estão bem cobertas.

> Inventário endpoint-a-endpoint (tabela completa dos 574) é um artefato extenso;
> pode ser gerado sob demanda a partir de `grep` dos decorators por router.
