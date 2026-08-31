# MT-0 — Auditoria de aderência à Política Canônica Multi-Tenant

**Data:** 31/08/2026  
**Issue:** #296  
**Base auditada:** `main@90a2e2797166ed79550b43bc01d02d6a01e2dc8e`  
**Natureza:** somente leitura / documentação  
**Efeito em runtime:** nenhum

---

## 1. Decisão canônica

A política anterior, segundo a qual `super_admin` podia operar sem mantenedora selecionada e portanto em modo cross-tenant nas páginas de negócio, está **revogada como arquitetura-alvo**.

A regra canônica passa a ser:

> **Super Administrador enxerga qualquer mantenedora, mas uma por vez no plano operacional.**

Cross-tenant continua possível somente em funcionalidades explicitamente classificadas como **CONTROL_PLANE_CROSS_TENANT**, por exemplo gestão de mantenedoras e, futuramente, uma visão global de plataforma desenhada para esse fim.

---

## 2. Invariantes MT-01…MT-12

### MT-01 — exatamente uma mantenedora ativa no plano operacional
Toda operação institucional autenticada deve resolver exatamente um `active_mantenedora_id`. Para não-super_admin, ele coincide com o tenant cadastral do usuário. Para `super_admin`, corresponde à mantenedora selecionada. Sem tenant operacional válido, a operação falha fechada.

### MT-02 — isolamento absoluto de escolas
Nenhuma escola de uma mantenedora pode aparecer em listagem, busca, autocomplete, relatório, PDF, exportação, cache ou relacionamento de outra mantenedora. Acesso direto a objeto de outro tenant deve ser negado sem revelar informação útil ao chamador.

### MT-03 — tenant antes de RBAC
Autorização efetiva = usuário autenticado ∩ usuário ativo ∩ mantenedora ativa ∩ vínculo com tenant ∩ permissão funcional ∩ escopo de escola/objeto. Papel nunca remove o filtro de tenant.

### MT-04 — criação herda o tenant ativo no backend
Servidor, usuário, escola, turma, estudante, matrícula, lotação, alocação e demais documentos de domínio devem persistir `mantenedora_id` resolvido pelo servidor. Payload do cliente não é fonte de autoridade para tenant. Sem tenant válido, não há escrita.

### MT-05 — tenant-scoped por padrão
Todas as páginas/rotas institucionais atuais e futuras são tenant-scoped, incluindo Auditoria, Usuários Online, MEC, Dashboard Analítico, Transferências Institucionais, Auditoria de Matrículas, Calendário, RH/Folha, AEE, Bolsa Família, PME, documentos e relatórios.

### MT-06 — tenant + permissão
O tenant correto é condição necessária, mas não suficiente. A API deve também validar a permissão funcional correspondente. Ocultação de menu no frontend é apenas UX.

### MT-07 — transferência institucional intratenant
O fluxo normal de transferência institucional opera somente dentro da mantenedora ativa. Uma eventual transferência inter-tenant deve ser outro caso de uso, explicitamente governado e auditado.

### MT-08 — documento sem tenant falha fechado
Documento de domínio sem `mantenedora_id` não é automaticamente associado à primeira mantenedora durante uma operação normal. Saneamento de legado exige processo governado, com inventário, preflight e evidência.

### MT-09 — tenant acompanha o ciclo completo
Auditoria, sessões, WebSocket, jobs, schedulers, filas MEC, snapshots, PDFs, exportações, cache e offline devem transportar e validar tenant. Chaves de cache com dados institucionais devem incluir tenant.

### MT-10 — cross-tenant só no control plane
Ausência de `active_mantenedora_id` nunca significa “todas” numa rota operacional. Endpoints globais devem ser explicitamente identificados como control plane.

### MT-11 — tenant operacional precisa estar ativo
A mantenedora deve existir e estar ativa. Tenant inativo não pode ser usado em novas operações de negócio.

### MT-12 — regressão permanente no CI
O CI deve provar isolamento com pelo menos `TENANT_A` e `TENANT_B`, cobrindo leitura, ID direto, escrita, atualização, exclusão, agregações, relatórios, auditoria, sessões e integrações críticas.

---

## 3. Vocabulário da auditoria

| Status | Significado |
|---|---|
| `OK` | Aderente aos invariantes auditados no trecho examinado. |
| `PARCIAL` | Há scoping, mas existe pelo menos uma exceção, bypass ou caminho não coberto. |
| `FAIL-OPEN` | Ausência/erro de tenant pode ampliar o escopo ou existe caminho operacional global. |
| `SEM TENANT` | O módulo não persiste/aplica tenant de forma útil no caminho auditado. |
| `CONTROL_PLANE` | Cross-tenant é esperado e aceitável por desenho, desde que isolado do plano operacional. |

---

## 4. Resultado executivo

A fundação multi-tenant existe e já protege alguns fluxos, especialmente não-super_admin em `/schools`, refresh de JWT e designação de gerente. Entretanto, **o isolamento ainda não é uma propriedade sistêmica**.

Os riscos principais não são apenas filtros ausentes em telas: há caminhos centrais em que o `super_admin` sem tenant vira cross-tenant por definição, serviços críticos fazem agregações globais e algumas coleções sequer persistem `mantenedora_id` de forma consistente.

### Prioridade P0 confirmada

1. `tenant_scope.py` + `AuthMiddleware`: semântica cross-tenant implícita para `super_admin`.
2. `TenantSwitcher`: opção operacional “Todas (cross-tenant)”.
3. criação automática de usuário professor em `staff.py` sem `mantenedora_id`.
4. Auditoria: logs novos não registram tenant e consultas são globais.
5. Usuários Online / revogação remota: sessões e alvos não são filtrados por tenant.
6. Calendário: rotas de leitura/escrita sem tenant.
7. RH/Folha: competências, pré-folhas e consultas globais por desenho atual.
8. MEC: configuração global e caminhos `sync_status`/`students_mapping`/dead-letter sem isolamento integral.
9. Auditoria de Matrículas / integridade: fluxos explicitamente globais para super_admin.
10. Dashboard Analítico: parte dos indicadores é tenant-scoped, mas transferências, desistências, frequência e notas podem agregar globalmente.

---

## 5. Matriz inicial de aderência

| Área | Classificação MT-0 | Evidência / GAP principal |
|---|---|---|
| `tenant_scope.py` | **FAIL-OPEN** | `super_admin` sem header/query retorna scope `None`; `apply_tenant_filter` remove o filtro; `assert_same_tenant` permite bypass; existe fallback para primeira mantenedora. |
| `AuthMiddleware` | **FAIL-OPEN** | `super_admin` passa `require_roles`/`require_permission` automaticamente; `verify_school_access` só valida tenant quando há scope; escola legado sem tenant pode passar. |
| Login/refresh | **PARCIAL** | preserva `mantenedora_id` no JWT, mas não valida se a mantenedora existe/está ativa. |
| `/auth/register` | **PARCIAL** | deriva tenant do criador, mas ainda aceita fallback para a única mantenedora; onboarding e criação operacional estão misturados. |
| TenantSwitcher | **FAIL-OPEN** | oferece “Todas (cross-tenant)” e remove `activeMantenedoraId`. |
| TenantSyncBoundary | **OK** | remonta a árvore ao trocar tenant, reduzindo estado visual obsoleto. |
| Gestão de mantenedoras | **CONTROL_PLANE** | listagem global para super_admin é apropriada; designação de gerente filtra school links e revoga tokens. |
| Escolas | **PARCIAL** | create exige tenant; list/get usam helpers; porém super_admin sem scope continua global e rota pública de pré-matrícula não usa contexto por tenant. |
| Servidores | **PARCIAL / P0 write** | list/get/update usam scoping; criação automática de usuário professor não grava tenant no `new_user` antes do insert. |
| Usuários | **PARCIAL** | list/count usam tenant para perfis normais; super_admin sem seleção permanece global; operações dependem do bypass atual de `assert_same_tenant`. |
| Auditoria | **SEM TENANT / FAIL-OPEN** | `AuditService.log` não persiste `mantenedora_id`; `get_logs` não filtra tenant; PDF usa fallback de mantenedora/legado. |
| Usuários Online | **FAIL-OPEN** | `active_sessions.get_online()` retorna conjunto global; escolas e contadores são globais; force logout não prova tenant do alvo. |
| Dashboard Analítico | **PARCIAL** | escolas/turmas/alunos/matrículas usam `apply_tenant_filter`; outros blocos de overview podem contar transferidos/desistentes/frequência/notas sem tenant. |
| MEC / CMDE | **PARCIAL / FAIL-OPEN** | guard produz tenant, mas config é global; `sync_status` e `students_mapping` não recebem contexto; dead-letter só filtra quando tenant é truthy e reprocessa por ID sem assert tenant. |
| Transferência Institucional | **PARCIAL** | valida origem/destino na mesma mantenedora, mas não exige que essa mantenedora seja a ativa da sessão. |
| Calendário | **SEM TENANT / FAIL-OPEN** | consultas e CRUD de `calendar_events`/`calendario_letivo` não aplicam tenant; create não persiste tenant no trecho auditado. |
| RH/Folha | **SEM TENANT / FAIL-OPEN** | permission guard existe, porém competências/folhas/itens/auditoria HR não são tenant-scoped no caminho auditado; geração de pré-folha alcança rede global. |
| Auditoria de Matrículas | **FAIL-OPEN** | frontend principal usa `fetch` fora do interceptor de tenant; semântica backend exclui tenant para super_admin; integridade administrativa é global. |
| Testes existentes | **PARCIAL** | `test_multi_tenant_isolation.py` prova A/B para gerente + escolas + refresh/fail-closed sem tenant, mas não cobre super_admin nem módulos críticos. |
| Toolkit `/tenant/audit` | **PARCIAL / CONTROL_PLANE** | bom inventário/backfill dry-run, mas lista de coleções é incompleta; backfill real é alto impacto. |
| `_heal` / migração legado | **ALTO RISCO** | caminho autenticado pode realizar backfill amplo para a primeira mantenedora; incompatível com MT-08 como comportamento operacional. |
| PDF/cache | **PENDENTE MT-6** | documentação atual já reconhece cache PDF global; exige inventário completo por tenant. |

---

## 6. Constatações detalhadas

### 6.1 Core de autorização

A causa estrutural mais importante está em `get_mantenedora_scope()`/`apply_tenant_filter()`: `None` possui dois significados incompatíveis — “não há tenant operacional” e “super_admin pode ver todos”. A política canônica elimina essa ambiguidade.

O desenho-alvo deverá separar explicitamente:

- `OperationalTenantContext`: exige um tenant ativo e validado;
- `ControlPlaneContext`: permite operações globais somente em endpoints classificados;
- ausência/tenant inválido: erro fail-closed.

`AuthMiddleware.get_current_user()` hoje confia nos claims do access token. Para cumprir MT-03/MT-11, as operações sensíveis deverão assegurar também que o usuário e a mantenedora continuam ativos, sem depender exclusivamente de claims possivelmente emitidos minutos antes.

### 6.2 Identidade e criação de usuários/servidores

`staff.py` persiste o tenant do servidor, mas no caminho que cria automaticamente a conta de professor o documento `new_user` é inserido sem `mantenedora_id`. Isso quebra a invariância pai/identidade: servidor e usuário podem nascer com escopos diferentes.

`/auth/register` possui fallback para a única mantenedora do banco. Esse mecanismo deve ficar restrito a bootstrap/onboarding explicitamente classificado como control plane; criação operacional não poderá inferir tenant pela cardinalidade do banco.

### 6.3 Auditoria e observabilidade

A página de Auditoria tem permission guard, porém `AuditService.log()` não grava tenant e `get_logs()` não aceita tenant. Portanto, a correção futura precisa começar na **persistência do audit record**, e não apenas adicionar um filtro na UI.

Logs históricos sem tenant precisam de política própria. Não se deve associá-los à primeira mantenedora sem evidência. Possíveis evidências: `school_id`, documento auditado, usuário/tenant histórico, `extra_data`, ou classificação como `UNRESOLVED_TENANT` até saneamento governado.

Usuários Online possuem problema semelhante: o tracker é global. A sessão precisa carregar tenant efetivo de modo confiável, e a listagem/revogação remota deve validar o tenant ativo antes de revelar ou alterar a sessão alvo.

### 6.4 MEC

A integração já possui vários objetos com campo `tenant`, especialmente auditoria, flags, fila e batch. Contudo, a configuração CMDE ainda está em `mec_integration.find_one({})`, global, e alguns relatórios leem estudantes/escolas sem tenant. Essa mistura impede afirmar isolamento da integração como um todo.

O tenant precisa ser obrigatório também para config, status, mapping, queue/dead-letter e scheduler. Um item de fila de outro tenant jamais pode ser reprocessado apenas por conhecer seu ID.

### 6.5 Dashboard Analítico

O router já usa `apply_tenant_filter` em partes importantes. Porém o `overview` combina esses resultados com agregações que não carregam tenant em todos os blocos. Uma única métrica global torna a resposta multi-tenant inconsistente, mesmo que os cards de escola/aluno estejam corretos.

Além disso, o endpoint `overview` auditado não chama o helper de permissão `_require_admin_tier`, embora outros endpoints do mesmo router o façam.

### 6.6 Transferência institucional

O motor já bloqueia origem/destino de mantenedoras diferentes, o que é uma boa salvaguarda. Falta vincular ambos ao tenant **ativo**. Com o desenho atual, um super_admin operando no contexto A ainda pode fornecer IDs da B e passar na validação se origem/destino forem ambas B.

### 6.7 Calendário

O router auditado não importa `tenant_scope`. Eventos e calendário letivo são lidos/escritos por ano, data, ID e escola, mas sem `mantenedora_id` como invariante. É um dos GAPs mais diretos da regra MT-05.

### 6.8 RH/Folha

O módulo usa `nav-hr-payroll-button`, portanto a camada de permissão funcional existe. O isolamento tenant, porém, não está presente no caminho auditado. Competências mensais e geração de pré-folha devem ser pertencentes a um único tenant; a geração automática não pode percorrer todas as escolas da instalação.

### 6.9 Auditoria de Matrículas e ferramentas globais

A página `EnrollmentAudit.jsx` faz uma chamada principal via `fetch` manual, fora do interceptor que injeta `X-Mantenedora-Id`, enquanto chamadas auxiliares usam o serviço compartilhado. Isso gera semântica de tenant inconsistente dentro da mesma tela.

O endpoint administrativo de integridade é explicitamente “global”. Se ainda for útil como ferramenta de plataforma, deve migrar para um namespace/control plane distinto e nunca ser a fonte da Auditoria de Matrículas operacional.

---

## 7. Plano de remediação recomendado

### MT-1 — Tenant Context canônico e fail-closed **[alto impacto]**

- introduzir resolução canônica de `OperationalTenantContext`;
- validar existência + status ativo da mantenedora;
- remover semântica “super_admin sem seleção = global” das rotas de negócio;
- remover “Todas (cross-tenant)” do TenantSwitcher operacional;
- preservar cross-tenant apenas em uma allowlist explícita de control plane;
- endurecer `verify_school_access` para escola sem tenant e tenant divergente;
- testes unitários e HTTP para super_admin em A/B.

**Gate:** exige autorização explícita antes de implementação.

### MT-2 — Identidade e writes **[alto impacto]**

- corrigir criação de servidor + conta automática de professor;
- separar `/auth/register` operacional de onboarding/bootstrap;
- exigir tenant ativo para todos os creates de domínio;
- validar tenant de parent IDs antes de persistir relações;
- revisar unicidade global versus por-tenant de CPF/email/matrícula.

### MT-3 — Auditoria, sessões e observabilidade **[alto impacto]**

- persistir `mantenedora_id` em todo audit record novo;
- tenant-scoped queries/PDF de auditoria;
- projetar política governada para logs históricos sem tenant;
- incluir tenant em sessão/presença/WebSocket;
- restringir Online Users, login-count e force logout ao tenant ativo.

### MT-4 — Módulos institucionais críticos **[alto impacto]**

- Calendário;
- RH/Folha;
- Auditoria de Matrículas;
- Dashboard Analítico;
- Transferência Institucional.

Cada módulo deve receber testes A/B de leitura e escrita antes do merge.

### MT-5 — MEC/CMDE **[alto impacto]**

- config por tenant;
- status/mapping tenant-scoped;
- scheduler/fila/dead-letter com tenant obrigatório;
- reprocessamento com assert tenant;
- auditoria/flags/metrics consistentes.

### MT-6 — Long tail e ciclo completo

Inventariar todos os routers/serviços restantes, documentos/PDFs, cache, jobs, PWA/offline, notificações, relatórios públicos e resolução por domínio. Nenhuma coleção nova nasce sem classificação `TENANT_SCOPED` ou `CONTROL_PLANE`.

### MT-7 — Guard permanente no CI

Expandir a regressão existente para uma suíte `Multi-Tenant Isolation Guard`, com TENANT_A/B e testes negativos por ID, writes, agregações, PDF/export, auditoria, sessões e integrações.

---

## 8. Critérios de aceite da migração arquitetural

A Política Canônica será considerada efetivamente implantada quando:

1. não houver caminho operacional em que ausência de tenant signifique acesso global;
2. `super_admin` precisar selecionar uma mantenedora antes de abrir módulos institucionais;
3. qualquer objeto retornado em rota tenant-scoped pertencer ao tenant ativo ou ser metadado global explicitamente permitido;
4. todo create de domínio persistir `mantenedora_id` derivado no backend;
5. parent IDs de outro tenant forem rejeitados;
6. Auditoria/Online/MEC/Analytics/Transfer/Calendar/HR/Enrollment Audit passarem por isolamento A/B;
7. documentos sem tenant permanecerem invisíveis até saneamento governado;
8. o CI impedir regressões automaticamente.

---

## 9. Decisões que ainda precisam ser tomadas antes das respectivas fases

- **Unicidade de CPF de servidor:** global na instalação ou por tenant? Um mesmo profissional pode trabalhar para mantenedoras diferentes.
- **Email de usuário:** recomenda-se manter globalmente único por ser credencial de login, salvo adoção futura de login qualificado por tenant.
- **Logs históricos sem tenant:** definir evidências aceitáveis para atribuição e tratamento dos não resolvidos.
- **Configuração MEC:** confirmar se credenciais/config são por mantenedora ou por instalação/provedor; dados e operações continuam tenant-scoped em qualquer caso.
- **Ferramenta global de integridade:** manter como control plane separado ou eliminar visão agregada global.

Essas decisões não bloqueiam MT-1, exceto onde explicitamente relacionadas.

---

## 10. Conclusão MT-0

A política canônica está definida e a auditoria inicial confirma que a mudança deve ser tratada como **migração arquitetural de autorização**, não como série de filtros de frontend.

O próximo passo recomendado é **MT-1 — Tenant Context canônico e fail-closed**. Por alterar autenticação/autorização e o comportamento do `super_admin`, MT-1 é classificado como **alto impacto** e não será implementado sem autorização explícita para essa fase.
