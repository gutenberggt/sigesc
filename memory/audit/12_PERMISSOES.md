# ENTREGA 12 — Sistema de Permissões

> Auditoria READ-ONLY · Jun/2026. Classificação 🟢🟡🔴⚫.

## 1. Papéis (roles) — 16 referenciados no backend
| Role | Descrição | Escopo | Frequência (refs backend) |
|---|---|---|---|
| `super_admin` | administrador da plataforma | cross-tenant (bypass RLS controlado) | 148 |
| `gerente` | gestor de mantenedora | tenant inteiro (herda poderes de admin) | 75 |
| `admin` / `admin_teste` | administrador da rede | tenant | 170 / 112 |
| `secretario` | secretário escolar | escola(s) vinculada(s) — acesso total | 110 |
| `diretor` | direção escolar | escola — visualização + aprovações | 44 |
| `coordenador` / `apoio_pedagogico` / `auxiliar_secretaria` | pedagógico/apoio | escola — **somente leitura** (configurável) | 30 / 7 / 28 |
| `professor` | docente | **apenas suas turmas/componentes** (notas, freq., conteúdo) | 44 |
| `semed` / `semed1` / `semed2` / `semed3` | SEMED (níveis crescentes) | rede — leitura ampla; edição limitada | 36 / 19 / 20 / 49 |
| `aluno` | portal do aluno | próprios dados (boletim) | 16 |
| `responsavel` | responsável/guardian | dados do(s) dependente(s) | 3 |
| `ass_social` | assistência social | módulo social | — |

> Papéis operacionais adicionais aparecem no frontend (`vacinas` etc.) via lotação/override.

## 2. Modelo de autorização (defense-in-depth) — 🟢
Quatro camadas complementares:

1. **RBAC estático** — `AuthMiddleware.require_roles([...])` (backend, 50 routers) e
   `<ProtectedRoute allowedRoles={[...]}>` (frontend). O `usePermissions` (hook central)
   deriva flags: `isAdmin` (inclui super_admin+gerente), `isSchoolStaff`
   (secretario+diretor+coordenador), `isSemed`, `isProfessor`, etc.

2. **Matriz de permissões dinâmica** — `require_permission(db, menu_key, default_roles)`
   consulta `permission_overrides` (por role × item de menu). Havendo override → honra
   `visible=true/false`; sem override → cai no `require_roles(default_roles)`. Página
   `/admin/permission-matrix` (`PermissionMatrix.js`) edita a matriz. `DASHBOARD_MENU_GROUPS`
   (em `Dashboard.js`) é a fonte declarativa dos itens/visibilidades.

3. **Row-Level Security multi-tenant** — `tenant_scope.apply_tenant_filter` injeta
   `mantenedora_id` em todas as queries. **Fail-closed:** não-super_admin sem tenant →
   filtro impossível `__INVALID_TENANT__` (zero dados). Header opcional `X-Mantenedora-Id`
   permite super_admin escolher contexto.

4. **Escopo por escola** — `check_school_access`/`verify_school_access` restringem staff
   às `school_ids` do token. `is_coordinator_read_only(user, area)` implementa a semântica
   de leitura-apenas do coordenador por área.

## 3. Heranças e regras especiais
- **Herança de poderes:** `super_admin` ⊇ `gerente` ⊇ `admin` (no frontend via `isAdmin`).
- **Role efetivo por lotação:** `school_assignments` pode dar a um usuário papel efetivo
  distinto do base (ex.: `professor` lotado como `secretario` em 2026 → age como secretário).
  Resolvido em vários routers (`hr`, `assignments`, `mantenedora`, `admin`, `medical_certificates`...).
- **Coordenador com edição pontual:** `require_roles_with_coordinator_edit(roles, area)`
  libera edição do coordenador em áreas específicas mesmo sendo read-only por padrão.
- **Professor restrito ao vínculo:** endpoints `/api/professor/*` usam
  `require_roles(['professor'])` + resolvem turmas via `teacher_assignments` do staff.

## 4. Restrições recentes (exemplos consolidados) — 🟢
- **Indicadores Externos (PME):** SEMED **somente visualiza**; edição p/ admin/super/gerente.
- **Auditoria de Matrículas:** restrita a super_admin/admin/gerente (SEMED sem acesso).
- **Transferências Institucionais:** super_admin + re-auth por senha + frase de confirmação.
- **Livro de Promoção (Jun/2026):** professor acessa, mas restrito ao vínculo
  (escolas/turmas/componentes que leciona; sem geração do PDF completo da turma).

## 5. Auditoria de segurança — 🟢
`tenant_audit.py` + coleção `tenant_security_events` registram apenas divergências:
`missing_tenant`, `tenant_mismatch`, `cross_tenant_attempt`, `invalid_token`
(com user_id, role, tenant do usuário vs. solicitado, endpoint, método, timestamp).

## 6. Riscos / oportunidades
- 🟡 **Superfície RBAC desigual:** ~39 routers dependem de checagem manual dentro do
  handler — recomenda-se padronizar via decorator/matriz e auditar caso a caso
  (precedente: bug `require_permission(db, key, None)` em `curriculum_v2` que causava
  `TypeError` para não-admin).
- 🟡 **Papéis numerosos e sobrepostos** (semed1/2/3, apoio_pedagogico/auxiliar_secretaria):
  documentar formalmente a matriz papel×capacidade evita divergência front/back.
- 🟢 **Isolamento multi-tenant** está blindado (fail-closed + auditoria + testes dedicados).

> Recomenda-se manter uma **matriz papel × recurso × ação (CRUD)** versionada como
> anexo vivo desta entrega (gerável a partir de `usePermissions` + `require_*`).
