# AEE V2 — Fase 6.6D: Plano Executivo da Governança de Escrita

**Data-base:** 2026-08-23  
**Status:** PLANO EXECUTIVO — SEM IMPLEMENTAÇÃO  
**Pré-requisitos:** Fase 6.6 aprovada; 6.6A, 6.6B e 6.6C homologadas em produção  
**Natureza:** governança de mutações / fail-closed / sem dual-write  
**Superfícies-alvo futuras:** edição, duplicação e proteção de exclusão do Plano AEE legado; editor Dossiê AEE V2  
**Princípio:** quando existe head V2, `planos_aee` deixa de ser autoridade de edição e permanece somente como âncora histórica/compatibilidade

## 1. Objetivo

Fechar a última forma relevante de **dupla autoridade operacional** do Plano AEE.

Após a 6.6C, a Fonte Efetiva governa corretamente:

- listagem;
- situação visual;
- agenda resumida;
- `status_filter`;
- `total` e paginação;
- visualização individual;
- PDF.

Entretanto, o router legado ainda possui mutações diretas sobre `planos_aee`, principalmente:

```text
PUT    /api/aee/planos/{plano_id}
POST   /api/aee/planos/{plano_id}/duplicate
DELETE /api/aee/planos/{plano_id}
```

O risco é objetivo: um Plano pode ser lido como `sidecar_active / active` e, ao mesmo tempo, continuar tecnicamente editável ou removível pela âncora legado.

Princípio central da 6.6D:

> **se existe head V2, nenhuma mutação de conteúdo pode continuar tratando `planos_aee` como segunda autoridade silenciosa. A edição passa obrigatoriamente pelo Dossiê V2; operações sem semântica V2 segura devem ser bloqueadas.**

A 6.6D não converte o sistema em dual-write e não sincroniza o legado com snapshots V2.

---

## 2. Evidência de produção que autoriza a 6.6D

A Fase 6.6C foi homologada em produção em 23/08/2026 com o universo:

```text
Planos totais                   = 23
legacy_allowed                  = 20
dossier_v2_required             = 3
v2_managed                      = 3
working_only                    = 2
sidecar_active                  = 1
integrity errors                = 0
working integrity errors        = 0
```

Caso sentinela:

```text
legacy_plano_id = 6a70538e-88a8-4691-b9fe-cf627b5f6cdc
legacy.status = rascunho
effective_source = sidecar_active
effective lifecycle = active
document_version = 2
revision = 2
```

Na UI, no viewer e no PDF, esse Plano aparece corretamente como:

```text
Vigente
```

Ao mesmo tempo, a âncora legado preserva:

```text
status = rascunho
```

Essa divergência intencional prova por que a governança de escrita não pode continuar dependendo do estado legado.

---

## 3. Estado atual das mutações legado

O router `backend/routers/aee.py` é um **módulo bloqueado** e só pode ser alterado com autorização explícita.

Atualmente, o endpoint de atualização executa, em essência:

```text
check_aee_write_access
find planos_aee by id
model_dump(exclude_unset=True)
update_one($set)
audit
```

O endpoint de duplicação:

```text
check_aee_write_access
find original in planos_aee
clone legacy document
new id
status = rascunho
insert new legacy plan
```

O delete guard atual decide a possibilidade de exclusão com base no `existing.status` legado.

Esse comportamento era coerente antes do cutover, mas deixa de ser suficiente quando existe head V2.

---

## 4. Escopo exato da futura implementação

### 4.1 Entra na 6.6D

- enforcement backend da política `mutation_policy`;
- bloqueio de `PUT` legado quando existe head V2;
- redirecionamento do botão **Editar** para `DossieAEEV2Modal` quando `dossier_v2_required`;
- bloqueio de duplicação legado quando existe head V2;
- proteção fail-closed contra exclusão da âncora legado quando existe head V2;
- bloqueio de todas essas mutações quando houver erro de integridade;
- preservação integral das mutações legado quando `mutation_policy = legacy_allowed`;
- preservação dos endpoints de escrita próprios do Dossiê V2;
- observabilidade agregada da decisão de governança;
- testes de RBAC, integridade, no-write-on-block, compatibilidade e performance;
- implementação preferencial por adapter/installer AEE V2, sem editar `backend/routers/aee.py`.

### 4.2 Não entra na 6.6D

- dual-write V2 -> legado;
- dual-write legado -> V2;
- sincronização automática de `status`;
- migração/backfill em massa;
- alteração de snapshots existentes;
- duplicação V2-aware de Dossiês/snapshots;
- exclusão física de head ou snapshots V2;
- implementação de workflow completo de arquivamento/cancelamento V2;
- mudança em Atendimentos AEE;
- mudança no Diário/PDF/Fonte Efetiva já homologados;
- refatoração geral de `backend/routers/aee.py`;
- mudança de regras de ownership/RBAC além da paridade necessária;
- bootstrap automático ao clicar em Editar;
- criação automática de head V2 para Planos puramente legado.

---

## 5. Decisão sobre DELETE: proteção da âncora V2

A arquitetura original da 6.6D destacava principalmente PUT e duplicação. A homologação real da 6.6C tornou explícito um risco adicional:

```text
legacy.status = rascunho
effective status = ativo
```

O delete guard legado ainda enxerga `rascunho`.

Permitir que uma âncora com head V2 seja removida pela regra legado pode romper:

- `legacy_plano_id`;
- provenance dos snapshots;
- vínculos de Atendimentos;
- PDF/consultas por ID legado;
- rastreabilidade histórica.

Portanto, a 6.6D deve aplicar uma proteção mínima e fail-closed:

> **qualquer Plano com `v2_managed = true` não pode ser excluído pelo endpoint DELETE legado.**

Isso **não implementa exclusão V2**. Apenas impede destruição da âncora enquanto não existir um lifecycle V2 próprio e seguro para essa operação.

Para `legacy_allowed`, o delete continua delegado ao guard legado existente, sem mudança de papéis ou regras.

---

## 6. Matriz canônica de mutação

### 6.1 Plano sem head V2

```text
v2_managed = false
mutation_policy = legacy_allowed
```

Comportamento:

| Ação | Resultado 6.6D |
|---|---|
| Editar legado (PUT) | permitido, regra existente |
| Duplicar legado | permitido, regra existente |
| Excluir legado | regra existente do delete guard |
| Inicializar Dossiê V2 | permitido pelo fluxo V2 já existente |

Nenhum bootstrap deve ser automático.

### 6.2 Working-only íntegro

```text
v2_managed = true
effective_source = legacy
mutation_policy = dossier_v2_required
```

Embora a Fonte Efetiva de leitura ainda seja a projeção legado, a governança de edição já pertence ao Dossiê V2.

| Ação | Resultado 6.6D |
|---|---|
| Editar legado (PUT) | bloqueado |
| Editar pelo Dossiê V2 | permitido |
| Duplicar legado | bloqueado |
| Excluir âncora legado | bloqueado |

### 6.3 Active íntegro

```text
v2_managed = true
effective_source = sidecar_active
mutation_policy = dossier_v2_required
```

| Ação | Resultado 6.6D |
|---|---|
| Editar legado (PUT) | bloqueado |
| Abrir/editar revisão V2 | permitido |
| Duplicar legado | bloqueado |
| Excluir âncora legado | bloqueado |

Se não houver working snapshot, o Dossiê V2 já possui a ação canônica **Abrir nova versão para revisão**.

### 6.4 Integridade comprometida

```text
mutation_policy = blocked_integrity
```

| Ação | Resultado 6.6D |
|---|---|
| PUT legado | bloqueado |
| Duplicação legado | bloqueada |
| DELETE legado | bloqueado |
| Edição V2 potencialmente destrutiva | deve respeitar os guards V2 existentes |

A UI deve indicar que a integridade precisa ser resolvida antes de uma mutação administrada pela 6.6D.

---

## 7. Autoridade do backend

A política recebida no JSON da listagem é útil para UX, mas **não é autoridade de segurança**.

O frontend pode usar `mutation_policy` para decidir quais controles mostrar, porém cada mutação legado deve ser reavaliada no backend imediatamente antes de executar o endpoint original.

É proibido confiar apenas em:

```text
plano.v2_managed
plano.mutation_policy
```

recebidos anteriormente pelo navegador.

A decisão final precisa usar o estado atual persistido no servidor.

---

## 8. Estratégia backend preferencial

Criar adapter dedicado, por exemplo:

```text
backend/aee_v2/plan_write_governance.py
```

Responsabilidades:

1. instalar-se depois de `setup_aee_router`;
2. localizar as rotas legado de PUT, duplicate e DELETE;
3. substituir `route.endpoint` e `route.dependant.call` por wrappers mínimos;
4. autenticar/autorizAR antes de consultar dados do Plano;
5. carregar o Plano legado mínimo por ID;
6. resolver a Fonte Efetiva/política atual reutilizando os componentes 6.6A/6.6B;
7. permitir ou bloquear a chamada do endpoint original;
8. não executar nenhuma mutação V2 por conta própria;
9. não editar `backend/routers/aee.py` se tecnicamente evitável.

Padrão de instalação deve seguir os adapters anteriores da Fase 6.6.

---

## 9. Reutilização obrigatória da política existente

A 6.6D não deve criar uma segunda implementação independente de `mutation_policy`.

Preferir reutilizar:

```text
resolve_plan_list_effective_batch(...)
project_plan_list_contract_item(...)
```

ou extrair um helper puro compartilhado que preserve exatamente a semântica já homologada:

```text
sem head                    -> legacy_allowed
working-only íntegro        -> dossier_v2_required
active íntegro              -> dossier_v2_required
integridade primária        -> blocked_integrity
active íntegro + working ruim -> blocked_integrity
```

A resolução para uma mutação é unitária (`N=1`), mas deve manter os mesmos invariantes de hash, identidade e lifecycle do resolver homologado.

---

## 10. RBAC e ordem de avaliação

A 6.6D não deve ampliar nem reduzir os papéis atuais.

O adapter deve receber do módulo legado a configuração canônica:

```text
ROLES_AEE_WRITE
```

Ordem obrigatória:

```text
autenticação
  -> autorização de escrita
  -> localizar plano legado
  -> resolver policy V2
  -> permitir/bloquear
  -> somente então chamar endpoint legado original
```

Isso evita usar a governança V2 como canal lateral para revelar a existência de Planos a usuários sem permissão.

Quando permitido, o endpoint legado original continua executando sua própria validação/auditoria, preservando defesa em profundidade e compatibilidade.

A 6.6D não introduz nova regra de ownership para professor; qualquer revisão desse comportamento deve ocorrer em fase própria.

---

## 11. Contrato HTTP de bloqueio

### 11.1 PUT legado em Plano V2-managed

Resposta recomendada:

```text
HTTP 409 Conflict
```

```json
{
  "detail": {
    "code": "AEE_V2_PLAN_LEGACY_WRITE_REQUIRES_DOSSIER_V2",
    "message": "Este Plano é gerenciado pelo Dossiê AEE V2 e não pode mais ser editado pelo formulário legado.",
    "next_action": "open_dossier_v2"
  }
}
```

### 11.2 Duplicate legado em Plano V2-managed

```text
HTTP 409 Conflict
```

```json
{
  "detail": {
    "code": "AEE_V2_PLAN_LEGACY_DUPLICATE_BLOCKED",
    "message": "A duplicação do Plano legado não é permitida após o início da governança pelo Dossiê AEE V2."
  }
}
```

A 6.6D **não cria automaticamente uma cópia V2**.

### 11.3 DELETE legado em Plano V2-managed

```text
HTTP 409 Conflict
```

```json
{
  "detail": {
    "code": "AEE_V2_PLAN_LEGACY_DELETE_BLOCKED",
    "message": "A âncora histórica deste Plano é utilizada pelo Dossiê AEE V2 e não pode ser excluída pelo fluxo legado."
  }
}
```

### 11.4 Integridade comprometida

```text
HTTP 409 Conflict
```

```json
{
  "detail": {
    "code": "AEE_V2_PLAN_WRITE_INTEGRITY_BLOCKED",
    "message": "A mutação foi bloqueada porque a integridade da Fonte Efetiva precisa ser verificada."
  }
}
```

### 11.5 Falha global da governança

É proibido permitir a escrita legado quando o resolver da política falhar de forma inesperada.

```text
HTTP 503 Service Unavailable
```

```json
{
  "detail": {
    "code": "AEE_V2_PLAN_WRITE_GOVERNANCE_UNAVAILABLE",
    "message": "A governança de escrita do Plano AEE está temporariamente indisponível."
  }
}
```

Princípio: **falha de governança é fail-closed, nunca fallback para escrita legado.**

---

## 12. Semântica do botão Editar

A listagem 6.6C já recebe `mutation_policy`.

O botão **Editar** deverá obedecer:

### `legacy_allowed`

```text
abre o PlanoAEEModal legado atual
```

Nenhum comportamento precisa mudar para os 20 Planos puramente legado do universo homologado.

### `dossier_v2_required`

```text
abre DossieAEEV2Modal
```

Não deve abrir o editor legado.

O Dossiê V2 já possui os fluxos canônicos necessários:

- edição de working snapshot;
- gravação por seção em nova revisão imutável;
- ativação;
- quando há active sem working: **Abrir nova versão para revisão**.

### `blocked_integrity`

O botão não deve abrir nenhum editor de conteúdo como se o Plano estivesse íntegro.

Exibir mensagem clara de verificação de integridade.

---

## 13. Semântica do botão Duplicar

### `legacy_allowed`

Preservar o fluxo atual de duplicação legado.

### `dossier_v2_required`

Bloquear/desabilitar a duplicação legado e explicar o motivo.

A Fase 6.6D não deve tentar copiar:

- head;
- snapshots;
- hashes;
- histórico;
- provenance;
- versões/revisões.

Duplicação V2-aware, se desejada no futuro, deve ter contrato próprio e semântica explícita.

### `blocked_integrity`

Duplicação bloqueada.

---

## 14. Semântica do botão Excluir

### `legacy_allowed`

Continuar sujeito ao delete guard legado já existente.

### `dossier_v2_required`

Bloquear a exclusão da âncora legado.

### `blocked_integrity`

Bloquear.

A 6.6D não cria um novo botão de “Excluir Dossiê V2”.

---

## 15. POST de criação de Plano

O endpoint:

```text
POST /api/aee/planos
```

permanece fora do enforcement específico 6.6D.

Razão:

- um Plano novo nasce sem head V2;
- nessa condição a política é `legacy_allowed`;
- o fluxo V2 continua oferecendo bootstrap controlado posterior;
- não existe motivo para transformar criação em migração automática.

As validações de unicidade existentes permanecem inalteradas.

---

## 16. Dossiê V2 continua sendo o único caminho de edição após head

A 6.6D não modifica os endpoints próprios do Dossiê, como:

```text
POST  /api/aee/planos/{id}/dossie-v2/bootstrap
PATCH /api/aee/planos/{id}/dossie-v2/sections/...
POST  /api/aee/planos/{id}/dossie-v2/revisions
POST  /api/aee/planos/{id}/dossie-v2/activate
```

Esses fluxos continuam aplicando suas regras de optimistic concurrency, snapshots imutáveis, blockers de ativação e revisão.

O objetivo da 6.6D é impedir que o fluxo legado contorne esses contratos.

---

## 17. Invariantes de dados

A implementação deve provar que, em tentativa bloqueada:

```text
planos_aee update count = 0
planos_aee insert count = 0
planos_aee delete count = 0
heads write count = 0
snapshots write count = 0
```

Não pode haver atualização de `updated_at` no legado antes da decisão de policy.

Não pode existir gravação parcial seguida de 409.

---

## 18. Observabilidade

Evento recomendado:

```text
AEE_V2_PLAN_WRITE_GOVERNANCE
```

Payload agregado, sem PII:

```json
{
  "phase": "6.6D",
  "mode": "write_governance",
  "action": "update|duplicate|delete",
  "role": "...",
  "v2_managed": true,
  "effective_source": "sidecar_active",
  "mutation_policy": "dossier_v2_required",
  "decision": "allowed|blocked|unavailable",
  "reason_code": "...",
  "performance": {
    "head_queries": 1,
    "snapshot_queries": 1,
    "governance_ms": 0.0
  }
}
```

Não registrar:

- nome do estudante;
- nome de professor;
- texto pedagógico;
- conteúdo do request body;
- conteúdo de snapshot.

O ID do Plano também deve ser omitido do evento agregado sempre que não for necessário operacionalmente.

---

## 19. Hard gate de queries

Para cada mutação governada:

```text
head_queries <= 1
snapshot_queries <= 1
```

Como o universo da decisão é um único Plano, qualquer N+1 é defeito.

Se for possível derivar uma política equivalente com menos consultas sem duplicar a lógica de integridade, isso pode ser otimizado, mas o teto acima é o gate obrigatório.

---

## 20. Arquivos preferenciais da implementação

Escopo esperado:

```text
backend/aee_v2/plan_write_governance.py
backend/tests/test_aee_v2_plan_write_governance.py
backend/routers/__init__.py
.github/workflows/aee-v2-contract.yml
frontend/src/pages/DiarioAEE.js
backend/tests/test_aee_v2_fase6_6d_ui_contract.py
```

Possível ajuste em helper existente, somente se necessário para eliminar duplicação de policy:

```text
backend/aee_v2/plan_list_contract.py
```

### Arquivos bloqueados

`backend/routers/aee.py` e `frontend/src/pages/DiarioAEE.js` pertencem a superfícies protegidas do módulo AEE.

A autorização específica concedida para editar `DiarioAEE.js` na 6.6C **não se estende automaticamente à 6.6D**.

Antes da implementação 6.6D deve existir autorização explícita nova para:

- alteração mínima de `frontend/src/pages/DiarioAEE.js`;
- e, somente se tecnicamente inevitável, `backend/routers/aee.py`.

O plano preferencial mantém `backend/routers/aee.py` intacto.

---

## 21. Testes backend obrigatórios

### 21.1 `legacy_allowed`

- PUT chama endpoint original exatamente uma vez;
- duplicate chama endpoint original exatamente uma vez;
- DELETE chama endpoint original e preserva o guard atual;
- policy não cria head/snapshot;
- auditoria legado continua pertencendo ao endpoint original.

### 21.2 `dossier_v2_required`

Para working-only e active:

- PUT retorna 409 e não chama original;
- duplicate retorna 409 e não chama original;
- DELETE retorna 409 e não chama original;
- nenhuma coleção mutável é alterada.

### 21.3 `blocked_integrity`

- PUT/duplicate/DELETE retornam 409;
- nenhum fallback para `legacy_allowed`;
- nenhuma escrita.

### 21.4 Falha global

- resolver inesperadamente indisponível -> 503;
- endpoint legado original não é chamado;
- zero writes.

### 21.5 RBAC

- roles de leitura continuam 403 nas mutações;
- roles de escrita preservam comportamento atual;
- autenticação ocorre antes de revelar policy/Plano.

### 21.6 Installer

- idempotente;
- não empilha múltiplos wrappers 6.6D;
- encontra exatamente PUT/duplicate/DELETE esperados;
- falha explicitamente se a superfície esperada mudou;
- funciona depois do `setup_aee_router` real.

### 21.7 Query budget

Testar políticas:

```text
legacy-only
working-only
active
active + working integrity error
primary integrity error
```

com:

```text
head_queries <= 1
snapshot_queries <= 1
```

---

## 22. Testes frontend obrigatórios

Cobrir pelo menos:

### Editar

```text
legacy_allowed          -> PlanoAEEModal legado
dossier_v2_required     -> DossieAEEV2Modal
blocked_integrity       -> aviso / sem editor destrutivo
```

### Duplicar

```text
legacy_allowed          -> fluxo existente
dossier_v2_required     -> bloqueado
blocked_integrity       -> bloqueado
```

### Excluir

```text
legacy_allowed          -> comportamento existente
dossier_v2_required     -> bloqueado na UI
blocked_integrity       -> bloqueado na UI
```

### Compatibilidade

- botão Visualizar continua usando o viewer efetivo 6.6C;
- PDF continua inalterado;
- Novo Atendimento continua inalterado;
- filtros/listagem continuam 6.6C;
- a UI não altera `mutation_policy` recebida;
- o frontend não é a única barreira: respostas 409 backend devem ser tratadas corretamente.

---

## 23. Gate de CI

O PR de implementação 6.6D deverá exigir, no mínimo:

- AEE v2 Contract Guard verde;
- CI Build & Lint verde;
- Gate Transferência verde;
- testes 6.6D backend verdes;
- testes UI-contract 6.6D verdes;
- frontend build verde;
- nenhuma alteração em Assessment Policy para contornar `FAIL_UNKNOWN_PHASE` se o guard continuar não reconhecendo a fase AEE.

Se o Assessment Policy acusar apenas o mesmo `FAIL_UNKNOWN_PHASE` por escopo AEE, documentar como sinal conhecido; não adulterar a policy para tornar o PR verde artificialmente.

---

## 24. Homologação futura em produção

Se a população permanecer equivalente à observada na 6.6C, validar:

### 24.1 Runtime

```text
installer 6.6D ativo exatamente uma vez
6.6C leitura continua ativa
backend healthy
```

### 24.2 Caso sentinela active

Sem efetuar mutação bem-sucedida:

```text
Editar na UI -> abre Dossiê V2
legacy PUT direto -> 409 AEE_V2_PLAN_LEGACY_WRITE_REQUIRES_DOSSIER_V2
legacy duplicate direto -> 409 AEE_V2_PLAN_LEGACY_DUPLICATE_BLOCKED
legacy DELETE direto -> 409 AEE_V2_PLAN_LEGACY_DELETE_BLOCKED
```

As três chamadas devem deixar banco inalterado.

### 24.3 Working-only

- Editar abre Dossiê V2 na versão em trabalho;
- PUT/duplicate/DELETE legado bloqueados.

### 24.4 Plano puramente legado

- botão Editar continua abrindo editor legado;
- botão Duplicar continua disponível;
- delete continua sujeito ao guard legado;
- não é necessário salvar ou excluir dados para homologar a compatibilidade visual.

### 24.5 Integridade e performance

```text
integrity errors inesperados = 0
head_queries <= 1
snapshot_queries <= 1
```

### 24.6 Regressão de leitura

Confirmar novamente:

```text
listagem = 23, se população não tiver mudado
sentinela visual = Vigente
viewer = Fonte Efetiva
PDF = Vigente
filtro ativo = 1
filtro rascunho = 22
```

Os números são condicionais à população não ter mudado entre homologações.

---

## 25. Rollback

A 6.6D não migra nem reescreve dados, portanto o rollback deve ser **somente de código**.

Rollback esperado:

1. remover/desativar installer 6.6D;
2. restaurar semântica anterior dos botões;
3. manter heads/snapshots e legado intactos.

Não há rollback de banco.

Observação: rollback da 6.6D reabre deliberadamente a possibilidade de escrita legado em Planos V2-managed; portanto só deve ser usado diante de regressão comprovada.

---

## 26. Critérios de aceite da implementação

A 6.6D só poderá ser considerada pronta para homologação quando:

- [ ] `legacy_allowed` preserva PUT/duplicate/delete atual;
- [ ] `dossier_v2_required` bloqueia PUT legado;
- [ ] `dossier_v2_required` bloqueia duplicate legado;
- [ ] `dossier_v2_required` protege DELETE da âncora;
- [ ] `blocked_integrity` bloqueia todas as mutações governadas;
- [ ] falha de resolver retorna 503 fail-closed;
- [ ] zero write ocorre antes da decisão;
- [ ] Editar direciona V2-managed ao Dossiê V2;
- [ ] Plano legado puro continua usando editor legado;
- [ ] frontend não é barreira única;
- [ ] Dossiê V2 continua usando snapshots/revisões existentes;
- [ ] não existe dual-write;
- [ ] não existe migração/backfill;
- [ ] `backend/routers/aee.py` permanece intacto, salvo autorização adicional e necessidade comprovada;
- [ ] heads queries <= 1;
- [ ] snapshot queries <= 1;
- [ ] 6.6C, viewer e PDF não regrediram;
- [ ] CI crítico verde.

---

## 27. Decisão executiva

A Fase 6.6D deve ser implementada como **camada de governança**, não como refatoração do router legado.

A regra de produto/arquitetura passa a ser:

```text
SEM HEAD V2
  -> legado pode continuar sendo editado normalmente

COM HEAD V2
  -> legado é âncora histórica
  -> edição obrigatoriamente pelo Dossiê V2
  -> duplicação legado bloqueada
  -> exclusão da âncora bloqueada

COM ERRO DE INTEGRIDADE
  -> mutações governadas bloqueadas fail-closed
```

Isso encerra a dupla autoridade de edição sem apagar o legado, sem sincronização bidirecional e sem invalidar a rastreabilidade já construída.

> **Este documento autoriza apenas o planejamento. Nenhum código da 6.6D deve ser implementado ou mergeado sem autorização explícita posterior.**
