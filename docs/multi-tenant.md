# 🏢 Multi-Tenancy (Mantenedoras) — Política Canônica

> **Decisão arquitetural aprovada em 31/08/2026.**  
> Esta página define a arquitetura-alvo obrigatória para código novo e para a remediação do legado.
> O estado atual ainda possui GAPs; consulte `memory/audit/MT0_CANONICAL_MULTI_TENANT_AUDIT_2026-08-31.md` e a issue #296.

## Regra principal

> **Super Administrador enxerga qualquer mantenedora, mas uma por vez no plano operacional.**

A ausência de mantenedora ativa **não** significa acesso a todas as mantenedoras em uma rota de negócio.
Cross-tenant só é permitido em endpoints explicitamente classificados como **CONTROL_PLANE_CROSS_TENANT**.

---

## Modelo

Cada **Mantenedora** é um tenant logicamente isolado:

- coleção `mantenedoras` com identidade e configuração próprias;
- escolas, servidores, estudantes, turmas, matrículas e demais documentos de domínio carregam `mantenedora_id`;
- relações entre documentos precisam preservar o mesmo tenant;
- uma mantenedora operacional precisa existir e estar ativa (`ativo != false` enquanto o legado de schema é saneado);
- documentos de domínio sem tenant são tratados como **não autorizados / não resolvidos**, nunca como pertencentes automaticamente à primeira mantenedora.

## Papéis e contexto

| Papel | Escopo canônico |
|---|---|
| `super_admin` | Autoridade global para escolher/administrar tenants, porém opera **uma mantenedora por vez** nas páginas institucionais. |
| `gerente` | Administrador restrito à própria mantenedora. |
| `admin`, `secretario`, `diretor`, `professor`, etc. | Restritos à mantenedora do usuário e, quando aplicável, às escolas/objetos autorizados. |

O JWT pode carregar `mantenedora_id`, mas o claim não elimina a obrigação de validar o contexto operacional. O header `X-Mantenedora-Id` é transporte de contexto para o `super_admin`, não uma autorização autossuficiente.

---

## Invariantes obrigatórios

### MT-01 — exatamente um tenant no plano operacional

Toda operação institucional autenticada resolve exatamente um tenant ativo. Para `super_admin`, o tenant vem da seleção explícita; para os demais, do vínculo cadastral do usuário. Sem tenant válido, **fail-closed**.

### MT-02 — isolamento absoluto de escolas

Escola de uma mantenedora nunca pode aparecer em listagem, busca, autocomplete, relatório, PDF, exportação, cache ou relacionamento de outra mantenedora.

### MT-03 — tenant antes de RBAC

A ordem lógica é:

```text
autenticação
→ usuário ativo
→ tenant operacional válido/ativo
→ vínculo do usuário com o tenant
→ permissão funcional
→ escopo de escola/objeto
→ operação
```

Papel `super_admin` não remove o filtro de tenant de uma rota operacional.

### MT-04 — criação herda tenant no backend

O servidor determina e persiste `mantenedora_id`. Nunca confiar em `mantenedora_id` enviado livremente no payload de uma rota de domínio.

### MT-05 — tenant-scoped por padrão

Todo módulo institucional atual ou futuro é tenant-scoped por padrão, incluindo Auditoria, Usuários Online, MEC, Analytics, Transferências, Auditoria de Matrículas, Calendário, RH/Folha, AEE, Bolsa Família, PME, documentos, relatórios e jobs.

### MT-06 — tenant + permissão

Frontend ocultar menu é UX. A API sempre revalida tenant e permissão funcional.

### MT-07 — transferência normal é intratenant

Origem e destino devem pertencer à mantenedora ativa. Eventual transferência inter-tenant será outro fluxo, com governança própria.

### MT-08 — legado sem tenant não ganha fallback implícito

`mantenedora_id` ausente/nulo não pode ampliar acesso. Saneamento exige inventário, preflight e backfill governado.

### MT-09 — tenant acompanha o ciclo completo

Auditoria, sessões, WebSocket, jobs, scheduler, filas MEC, snapshots, PDFs, exports, cache e offline devem carregar/validar tenant. Cache de dados institucionais deve incluir tenant na chave.

### MT-10 — cross-tenant só no control plane

Exemplos aceitáveis: listagem/CRUD de mantenedoras para `super_admin`, gestão global de domínios e eventual dashboard global de plataforma explicitamente construído para isso.

### MT-11 — tenant precisa estar ativo

Tenant inexistente ou inativo não pode ser usado em operações institucionais novas.

### MT-12 — CI prova isolamento

A suíte permanente deve usar pelo menos `TENANT_A` e `TENANT_B` e provar ausência de vazamento em leitura, escrita, ID direto, agregações, relatórios e módulos críticos.

---

## API de tenant — arquitetura-alvo

`backend/tenant_scope.py` é a fundação existente, mas sua semântica atual ainda permite `super_admin` sem seleção operar cross-tenant. Durante MT-1, a API deverá distinguir explicitamente:

```python
# Conceitual — arquitetura-alvo
ctx = await resolve_operational_tenant(db, user, request)
# ctx.id existe, é válido e ativo; ausência => erro fail-closed

query = apply_operational_tenant_filter(base_query, ctx)
assert_object_in_operational_tenant(doc, ctx)
```

Para control plane, usar uma entrada separada e explícita, nunca `tenant=None` com significado ambíguo.

---

## Padrão obrigatório para novos endpoints de domínio

### Leitura

```python
user = await AuthMiddleware.get_current_user(request)
ctx = await resolve_operational_tenant(db, user, request)
await require_permission(...)
query = {**base_query, "mantenedora_id": ctx.id}
items = await db.items.find(query, {"_id": 0}).to_list(...)
```

### Criação

```python
ctx = await resolve_operational_tenant(db, user, request)
payload = body.model_dump()
payload.pop("mantenedora_id", None)          # não confiar no cliente
payload["mantenedora_id"] = ctx.id          # autoridade no backend
await assert_parent_ids_in_tenant(db, payload, ctx.id)
await db.items.insert_one(payload)
```

### Update/Delete

```python
doc = await db.items.find_one({"id": item_id})
assert_object_in_operational_tenant(doc, ctx)
# então aplicar RBAC/escopo e mutação
```

Para acesso direto a objeto de outro tenant, a camada externa deve evitar revelar a existência do recurso; o evento de segurança pode ser auditado internamente.

---

## Frontend

- `TenantSwitcher.jsx` continua sendo o seletor de contexto do `super_admin`.
- A opção atual **“Todas (cross-tenant)” é legado e será removida do plano operacional em MT-1**.
- `activeMantenedoraId` em `localStorage` é apenas estado de UI/transporte.
- `services/api.js` envia `X-Mantenedora-Id` nas requests aplicáveis.
- `TenantSyncBoundary` remonta a árvore quando o tenant muda, obrigando recarga das consultas.
- O frontend nunca substitui a validação de tenant do backend.

---

## Control plane x plano operacional

### CONTROL_PLANE_CROSS_TENANT

Pode operar globalmente, com autorização específica:

- gestão/listagem de mantenedoras;
- gestão de domínios de tenant;
- onboarding de nova mantenedora;
- ferramentas globais explicitamente nomeadas e auditadas.

### TENANT_SCOPED_OPERATIONAL

Exige exatamente um tenant ativo:

- escolas, servidores, usuários operacionais;
- turmas, estudantes, matrículas;
- diário, frequência, notas, conteúdos;
- AEE, Bolsa Família, PME;
- Auditoria e Usuários Online;
- MEC/CMDE;
- Dashboard Analítico;
- Transferência Institucional;
- Auditoria de Matrículas;
- Calendário;
- RH/Folha;
- documentos, PDFs, exports e demais módulos institucionais.

---

## Estado da implementação em 31/08/2026

A fundação existe, mas a política canônica **ainda não está integralmente implementada**.

- [x] coleção/modelo de mantenedoras;
- [x] `mantenedora_id` em vários documentos de domínio;
- [x] JWT preserva `mantenedora_id` no login/refresh;
- [x] helper `tenant_scope.py` e fail-closed para vários perfis não-super_admin;
- [x] seletor visual de tenant para `super_admin`;
- [x] remount da UI ao trocar tenant (`TenantSyncBoundary`);
- [x] regressão básica A/B para gerente + escolas + refresh;
- [ ] **MT-1:** eliminar cross-tenant implícito do plano operacional e validar tenant ativo;
- [ ] **MT-2:** fechar todas as rotas de criação/identidade pelo tenant ativo;
- [ ] **MT-3:** tenant em auditoria, sessões e observabilidade;
- [ ] **MT-4:** Calendar, RH, Enrollment Audit, Analytics e Transferência integralmente scoped;
- [ ] **MT-5:** MEC/CMDE integralmente tenant-scoped;
- [ ] **MT-6:** long tail, PDF/cache/jobs/offline/public host routing;
- [ ] **MT-7:** Multi-Tenant Isolation Guard permanente e abrangente no CI.

**Importante:** até a conclusão das fases acima, não assumir que a mera presença de `mantenedora_id` ou `apply_tenant_filter` em alguns routers garante isolamento sistêmico.

---

## Governança de mudanças

Alterações de autenticação, autorização, multi-tenancy, migração/backfill e escopo de produção são **alto impacto**.

1. auditar e registrar causa/GAP;
2. propor invariante e fix mínimo/arquitetural;
3. obter autorização explícita para a fase de runtime;
4. implementar em branch/PR;
5. CI deve provar isolamento negativo A/B;
6. somente depois integrar/publicar conforme a política de release do projeto.

Nenhum backfill deve ser executado como efeito colateral de uma request operacional normal.
