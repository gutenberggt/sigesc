# AEE V2 — Fase 6.6C: Plano Executivo do Cutover Controlado da Leitura/UX

**Data-base:** 2026-08-23  
**Status:** PLANO EXECUTIVO — SEM IMPLEMENTAÇÃO  
**Pré-requisitos:** Fase 6.6 aprovada; 6.6A, 6.6B homologadas em produção  
**Superfícies-alvo futuras:** `GET /api/aee/planos`, aba Planos do Diário AEE e visualização read-only  
**Natureza:** cutover de leitura / sem writes / sem governança de escrita  
**Fase seguinte:** 6.6D — Governança de escrita

## 1. Objetivo

Definir, antes de qualquer alteração de runtime, como a Fase 6.6C fará a listagem e a visualização tradicional do Plano AEE passarem a obedecer à **Fonte Efetiva** já exposta e homologada na 6.6B.

A 6.6C deve corrigir quatro inconsistências de leitura:

1. a situação visual da listagem ainda usa `plano.status` legado;
2. os dias mostrados na listagem ainda usam `dias_atendimento` legado;
3. a visualização abre diretamente o objeto legado cru recebido na lista;
4. `status_filter`, `total` e paginação ainda são calculados pelo status legado antes de a Fonte Efetiva ser resolvida.

Princípio central:

> **na 6.6C, a Fonte Efetiva passa a governar leitura e apresentação; a âncora legado permanece disponível para compatibilidade e diagnóstico, mas deixa de definir silenciosamente a situação operacional quando existe `sidecar_active`.**

A 6.6C continua **read-only** em relação aos dados persistidos. Bloqueio de PUT/duplicação e alinhamento das ações mutáveis permanecem reservados à 6.6D.

---

## 2. Evidência de produção que autoriza a 6.6C

A Fase 6.6B foi homologada em produção em 23/08/2026 na escola Dr. Almir Gabriel, ano letivo 2026.

Universo observado:

```text
Planos totais                   = 23
legacy_allowed                  = 20
dossier_v2_required             = 3
v2_managed                      = 3
working_only                    = 2
sidecar_active                  = 1
integrity errors                = 0
working integrity errors        = 0
dias iguais                     = 23
dias divergentes                = 0
```

Caso sentinela:

```text
legacy_plano_id = 6a70538e-88a8-4691-b9fe-cf627b5f6cdc
legacy.status = rascunho
effective_source = sidecar_active
effective_summary.lifecycle_status = active
effective_summary.legacy_compatible_status = ativo
mutation_policy = dossier_v2_required
```

A 6.6B corretamente manteve a UI exibindo **Em elaboração**, pois ainda não havia cutover visual.

A 6.6A já havia demonstrado o impacto futuro de filtros:

```text
status_filter=ativo:
  legacy_total = 0
  effective_total = 1
  false_negative = 1

status_filter=rascunho:
  legacy_total = 23
  effective_total = 22
  false_positive = 1
```

Portanto, a 6.6C possui evidência real suficiente para substituir a leitura visual legado pela leitura efetiva.

---

## 3. Escopo exato da futura implementação

### 3.1 Entra na 6.6C

- situação mostrada na listagem passa a usar `effective_summary.legacy_compatible_status`;
- resumo de dias passa a usar `effective_summary.schedule_summary.days`;
- indicação visual compacta de Plano gerenciado pelo Dossiê V2;
- indicação segura de erro de integridade, sem fallback visual silencioso;
- visualização passa a buscar o `GET /api/aee/planos/{plano_id}` e usar `effective_dossier`;
- `status_filter` passa a ser aplicado sobre status efetivo;
- `total` passa a refletir o resultado efetivamente filtrado;
- `skip` e `limit` são aplicados depois do filtro efetivo;
- preservação dos seis campos 6.6B;
- preservação dos campos legado no JSON;
- observabilidade `AEE_V2_PLAN_LIST_EFFECTIVE`;
- testes de RBAC, filtro, paginação, integridade, UI e performance;
- substituição operacional do adapter 6.6B pelo adapter 6.6C, sem empilhamento.

### 3.2 Não entra na 6.6C

- bloqueio de `PUT /aee/planos/{plano_id}`;
- bloqueio de `POST /aee/planos/{plano_id}/duplicate`;
- mudança do delete guard 6.0A;
- redirecionamento obrigatório do botão Editar;
- remoção do PlanoAEEModal legado;
- criação de duplicação V2-aware;
- dual-write V2 ↔ legado;
- migração/backfill;
- alteração de snapshots existentes;
- write provocado por GET;
- alteração do Diário AEE ou PDFs já homologados;
- refatoração geral do módulo AEE;
- criação de novo controle visual de filtro por status se ele não existir atualmente.

A 6.6C corrige a **semântica do parâmetro HTTP `status_filter`**, mas não cria por iniciativa própria um novo filtro visual no frontend.

---

## 4. Fronteira de arquivos bloqueados

`frontend/src/pages/DiarioAEE.js` é explicitamente marcado como módulo bloqueado.

A implementação da 6.6C só poderá alterar esse arquivo depois de autorização explícita específica para a implementação da 6.6C.

O plano preferencial **não exige editar `backend/routers/aee.py`**. A intenção é manter o router legado bloqueado e realizar o cutover por adapter, como nas fases anteriores.

Se durante a implementação surgir uma necessidade comprovada de tocar `backend/routers/aee.py`, a execução deve parar e obter autorização adicional antes da alteração.

---

## 5. Invariante de autoridade

A 6.6C deverá obedecer exatamente à regra já homologada:

### 5.1 Sem head V2

```text
v2_managed = false
effective_source = legacy
```

Leitura operacional continua refletindo o legado.

### 5.2 Working-only íntegro

```text
v2_managed = true
effective_source = legacy
```

A Fonte Efetiva oficial ainda é a projeção legado, embora a governança de edição já pertença ao Dossiê.

### 5.3 Active íntegro

```text
v2_managed = true
effective_source = sidecar_active
```

A listagem, filtros e visualização devem refletir o snapshot ativo.

### 5.4 Integridade comprometida

```text
effective_source = null
effective_error != null
```

A UI e o backend não podem fingir que o legado voltou a ser a Fonte Efetiva.

---

## 6. Situação operacional na listagem

O frontend deverá derivar uma situação de apresentação sem sobrescrever o campo legado.

Regra:

```text
se effective_error != null:
    situação visual = Integridade pendente
senão se effective_summary.legacy_compatible_status existir:
    situação visual = status efetivo
senão se o contrato 6.6B estiver ausente por compatibilidade de deployment/rollback:
    situação visual = plano.status legado
```

O fallback para `plano.status` só é permitido quando os campos efetivos **não existem** por compatibilidade com versão anterior.

É proibido usar `plano.status` como fallback quando existe `effective_error`.

Mapeamento visual canônico:

```text
rascunho  -> Em elaboração
ativo     -> Vigente
revisao   -> Em revisão
encerrado -> Encerrado
cancelado -> Cancelado
```

A 6.6C deve acrescentar explicitamente o label `cancelado`, hoje ausente do mapa visual legado.

---

## 7. Indicação de governança V2

Quando `v2_managed = true`, a linha deverá ter indicação compacta e não ambígua de que existe Dossiê V2.

Comportamento recomendado:

```text
working_snapshot_id presente e active_snapshot_id ausente:
  badge = Dossiê V2 · Em trabalho

active_snapshot_id presente e íntegro:
  badge = Dossiê V2 · v<document_version>.r<revision>

integridade comprometida:
  badge = Dossiê V2 · Verificar integridade
```

A indicação é informativa. Ela não substitui ainda os botões de escrita, que serão governados na 6.6D.

---

## 8. Resumo de agenda na listagem

A coluna atual de dias usa:

```text
plano.dias_atendimento
```

Na 6.6C deverá usar:

```text
plano.effective_summary.schedule_summary.days
```

quando o contrato efetivo estiver presente e íntegro.

### 8.1 Agenda legado/working-only

```text
shape = legacy_projection
```

Os dias permanecem semanticamente iguais ao legado normalizado.

### 8.2 Agenda sidecar homogênea

```text
shape = homogeneous
```

Mostrar os dias efetivos.

### 8.3 Agenda sidecar heterogênea

```text
shape = heterogeneous
```

A listagem pode mostrar os dias, mas deve acrescentar indicação como:

```text
Agenda variável
```

É proibido inventar um horário único.

### 8.4 Integridade

Se `effective_error != null` ou `schedule_summary.days = null`, exibir estado neutro/indisponível e não voltar silenciosamente a `dias_atendimento` legado.

---

## 9. Visualização do Plano

A visualização tradicional atualmente executa essencialmente:

```text
setViewingPlano(plano_da_lista)
```

Isso deve deixar de ocorrer na 6.6C.

### 9.1 Nova regra

Ao clicar em **Visualizar**:

1. usar apenas o `id` da linha;
2. executar `GET /api/aee/planos/{plano_id}`;
3. usar o contrato individual 6.4B já homologado;
4. renderizar a Fonte Efetiva resolvida;
5. não utilizar o objeto cru da listagem como conteúdo oficial do modal.

### 9.2 Fonte `legacy`

O `effective_dossier` é a projeção canônica do legado. A visualização pode renderizar esse Dossiê read-only e identificar a origem como legado.

### 9.3 Fonte `sidecar_active`

A visualização deve renderizar o `effective_dossier` do snapshot ativo e identificar versão/revisão vigente.

### 9.4 Erro de integridade

Se o GET individual retornar:

```text
effective_source = null
effective_error != null
```

A visualização deve:

- mostrar aviso claro de integridade;
- não afirmar que o legado é vigente;
- permitir referência visual mínima dos metadados históricos quando necessário para suporte;
- não oferecer um falso status efetivo.

### 9.5 Componente de leitura recomendado

Preferir um componente read-only dedicado, por exemplo:

```text
frontend/src/components/PlanoAEEEffectiveViewer.jsx
```

Responsabilidades:

- renderizar `effective_dossier` sem controles de gravação;
- mostrar Fonte Efetiva e versão;
- organizar Estudo de Caso, PAEE, PEI, Agenda e Lifecycle;
- preservar botão de gerar PDF usando o `plano_id` já existente;
- não substituir o editor Dossiê V2;
- não gravar dados.

Não se recomenda usar o `DossieAEEV2Modal` editável como visualizador efetivo, pois ele possui responsabilidades de edição/working snapshot que não devem ser confundidas com a leitura oficial do snapshot ativo.

---

## 10. Problema crítico de `status_filter`

A 6.6B executa o endpoint legado primeiro.

O endpoint legado atualmente aplica:

```text
filter_query['status'] = status_filter
```

antes de:

```text
.skip(skip).limit(limit)
```

Somente depois a 6.6B resolve a Fonte Efetiva da página retornada.

Isso significa que não basta, na 6.6C, trocar o campo visual.

Caso real:

```text
legacy.status = rascunho
effective_status = ativo
status_filter = ativo
```

Se o Mongo legado filtrar primeiro por `status=ativo`, o caso sentinela nunca chega ao resolver e continua falso negativo.

Portanto:

> **na 6.6C, quando existe `status_filter`, a resolução efetiva precisa acontecer antes de total e paginação.**

---

## 11. Estratégia backend para filtro efetivo

A estratégia deverá ser híbrida para preservar performance.

### 11.1 Requisição sem `status_filter`

Continuar usando o fluxo eficiente homologado da 6.6B:

```text
endpoint legado autorizado/paginado
    -> página legado
    -> resolve_plan_list_effective_batch(página)
    -> contrato aditivo
    -> resposta
```

Como não há filtro por status, `total` legado e `total` efetivo são iguais por definição do universo de identidade.

Não há razão para resolver toda a população nessa situação.

### 11.2 Requisição com `status_filter`

Fluxo obrigatório:

```text
request + RBAC
    -> filtro candidato SEM status
    -> candidatos mínimos em ordem estável
    -> resolve_plan_list_effective_batch(candidatos) UMA VEZ
    -> validar integridade necessária ao filtro
    -> selecionar IDs pelo effective_legacy_status
    -> effective_total
    -> aplicar skip/limit
    -> materializar documentos completos da página
    -> preservar ordem dos IDs selecionados
    -> enriquecer student_name
    -> anexar contrato 6.6B da página
    -> resposta efetiva
```

É proibido aplicar `skip/limit` antes de selecionar pelo status efetivo.

---

## 12. Query de candidatos

Para o caminho com `status_filter`, a consulta candidato deve trazer somente o mínimo necessário para resolver a Fonte Efetiva:

```text
id
student_id
school_id
academic_year
status
dias_atendimento
```

O filtro candidato preserva os filtros de identidade/escopo atuais:

```text
school_id
student_id
academic_year
professor_aee_id
escopo do professor autenticado
```

O `status_filter` é deliberadamente removido desta query inicial.

### 12.1 Paridade RBAC obrigatória

O adapter 6.6C deve reproduzir exatamente o escopo hoje aplicado pelo endpoint legado.

Para `role = professor`, continua obrigatória a regra:

```text
professor_aee_id == current_user.id
OU
created_by == current_user.id
```

Se `professor_aee_id` explícito também for informado, ele continua sendo combinado com as demais condições da mesma forma que hoje.

A implementação preferencial deve manter `backend/routers/aee.py` intacto e materializar esse filtro em helper puro testado por paridade.

Qualquer divergência entre o helper e o comportamento legado é bloqueador de merge.

---

## 13. Integridade durante filtro efetivo

Sem `status_filter`, um item com erro de integridade pode continuar aparecendo na listagem com:

```text
effective_source = null
effective_error != null
```

A UI o apresenta como **Integridade pendente**.

Com `status_filter`, um candidato sem situação efetiva confiável torna o total filtrado semanticamente indeterminado.

Regra proposta:

> **filtro efetivo é fail-closed quando qualquer candidato dentro do universo autorizado necessário ao cálculo possui Fonte Efetiva irresolúvel.**

Resposta funcional sugerida:

```text
HTTP 409 Conflict
code = AEE_V2_PLAN_LIST_EFFECTIVE_FILTER_INTEGRITY_BLOCKED
```

O backend não deve excluir silenciosamente o item incerto nem assumir seu status legado.

---

## 14. `total`, `skip` e `limit`

Com `status_filter`:

```text
effective_total = quantidade de candidatos cujo effective_legacy_status == status_filter
```

Depois:

```text
page_ids = effective_ids[skip : skip + limit]
```

A resposta mantém o envelope atual:

```json
{
  "items": [...],
  "total": 1
}
```

Não criar envelope paralelo nem campo alternativo de total.

Sem `status_filter`, o `total` continua o total legado do escopo porque nenhum Plano é removido por situação.

---

## 15. Ordem da listagem

O endpoint legado atual não declara `sort` explícito.

A 6.6C não deve introduzir uma ordenação funcional nova.

No caminho filtrado:

1. preservar a ordem em que os candidatos foram lidos;
2. selecionar os IDs efetivos mantendo essa ordem;
3. aplicar paginação sobre essa sequência;
4. se a query de materialização por `$in` retornar em outra ordem, reconstruir a página em memória usando `page_ids`.

Não ordenar por nome, status, versão ou data nesta fase.

---

## 16. Enriquecimento de `student_name`

A listagem legado atualmente realiza enriquecimento de estudante após recuperar a página.

A 6.6C deve preservar o contrato:

```text
student_name
```

A otimização geral desse N+1 legado continua fora de escopo.

A 6.6C não pode criar N+1 de heads/snapshots. O enriquecimento atual de estudantes pode permanecer restrito aos itens materializados da página.

---

## 17. Reutilização obrigatória da 6.6A/6.6B

A 6.6C deve reutilizar:

```text
backend/aee_v2/plan_list_effective.py
backend/aee_v2/plan_list_contract.py
```

Em especial:

- `resolve_plan_list_effective_batch()` continua sendo a única resolução batch;
- `select_effective_ids_for_status()` já introduzido na 6.6B deve ser reutilizado ou evoluído sem criar algoritmo paralelo;
- `project_plan_list_contract_item()`/contrato 6.6B continuam canônicos;
- mapeamento de lifecycle continua idêntico à 6.5B/6.6A/6.6B.

É proibido criar outro resolver de head/snapshot.

---

## 18. Substituir, não empilhar, a 6.6B

O runtime 6.6C deve ter **um único adapter da listagem**.

Fluxo de instalação esperado:

```text
6.6B deixa de ser installer ativo
6.6C passa a ser installer ativo
```

O código 6.6B permanece no repositório para teste, rollback lógico e reutilização de helpers.

É proibido:

```text
6.6C -> 6.6B wrapper -> resolver
```

se isso provocar uma segunda resolução batch.

O hard gate continua:

```text
head_queries <= 1
snapshot_queries <= 1
```

por request que execute resolução V2.

---

## 19. Fronteira preferencial da PR futura

Arquivos preferenciais:

```text
backend/aee_v2/plan_list_effective_cutover.py          novo
backend/tests/test_aee_v2_plan_list_effective_cutover.py novo
backend/routers/__init__.py                            troca de installer
.github/workflows/aee-v2-contract.yml                  incluir suíte 6.6C
frontend/src/pages/DiarioAEE.js                        mudança mínima autorizada
frontend/src/components/PlanoAEEEffectiveViewer.jsx    novo
backend/tests/test_aee_v2_fase6_6c_ui_contract.py      novo
```

`backend/aee_v2/plan_list_contract.py` pode receber apenas helpers aditivos se necessários.

`backend/routers/aee.py` permanece fora da fronteira preferencial.

Nenhum outro módulo do Diário AEE deve ser refatorado.

---

## 20. Observabilidade

Evento principal:

```text
AEE_V2_PLAN_LIST_EFFECTIVE
```

Payload agregado recomendado:

```text
phase = 6.6C
mode = effective_read_cutover
status = effective | divergent | integrity_blocked | unavailable
scope.academic_year
scope.school_filter
scope.student_filter
scope.professor_filter
scope.status_filter
scope.role
page.skip
page.limit
page.items_returned
page.effective_total
candidates.total
sources.legacy_effective
sources.sidecar_active
sources.v2_managed
sources.working_only
status_compare.equal
status_compare.divergent
status_compare.transitions
filter.requested_status
filter.effective_matches
filter.legacy_matches_preview
filter.total_delta
integrity.errors
integrity.working_errors
integrity.by_code
performance.candidate_query_ms
performance.batch_ms
performance.materialize_ms
performance.total_ms
performance.head_queries
performance.snapshot_queries
```

Sem PII:

- não logar nome de estudante;
- não logar professor;
- não logar diagnóstico;
- não logar textos pedagógicos;
- não logar `student_id`;
- não logar `professor_aee_id`;
- não logar `legacy_plano_id` no evento agregado.

Durante a homologação, requests com `sidecar_active`, delta de filtro ou integridade devem permanecer visíveis no nível operacional da produção.

---

## 21. Falhas inesperadas

A 6.6C já será autoridade de leitura operacional.

Portanto, uma falha inesperada do adapter não deve remover silenciosamente os campos efetivos e devolver uma página que pareça legado normal.

Regra:

```text
falha global do adapter/resolver -> 503
```

Código sugerido:

```text
AEE_V2_PLAN_LIST_EFFECTIVE_UNAVAILABLE
```

Erros de integridade representáveis por item continuam retornando `200` na listagem sem `status_filter`, com `effective_error` explícito.

No filtro efetivo, aplica-se a regra fail-closed da seção 13.

---

## 22. Compatibilidade e rollback lógico

Mesmo após o cutover visual:

- `status` legado permanece no JSON;
- `dias_atendimento` legado permanece no JSON;
- campos históricos continuam disponíveis;
- os seis campos da 6.6B permanecem;
- não há migração;
- não há write.

Isso permite rollback de código sem restauração de banco.

---

## 23. Testes backend obrigatórios

### 23.1 Escopo/RBAC

Cobrir:

- super_admin;
- admin/admin_teste;
- gerente;
- coordenador;
- apoio pedagógico;
- auxiliar secretaria;
- secretário;
- diretor;
- SEMED roles;
- professor;
- role sem acesso -> 403.

Para professor, validar explicitamente `professor_aee_id OR created_by`.

### 23.2 Filtro efetivo

Cenário sentinela:

```text
legacy = rascunho
effective = ativo
```

Assertivas:

```text
status_filter=ativo     -> inclui o sentinela
status_filter=rascunho  -> exclui o sentinela
```

### 23.3 Total

Cenário 23 Planos:

```text
legacy rascunho = 23
effective rascunho = 22
effective ativo = 1
```

Assertivas:

```text
status_filter=ativo.total = 1
status_filter=rascunho.total = 22
```

### 23.4 Paginação

Cobrir:

```text
skip = 0/1/N
limit = 1/10/100
```

aplicados **depois** da seleção efetiva.

### 23.5 Ordem

Garantir ordem dos IDs antes/depois da materialização por `$in`.

### 23.6 Integridade

Cobrir:

- active missing;
- active hash inválido;
- identity mismatch;
- lifecycle sem projeção;
- working inválido com active íntegro.

Sem filtro:

```text
item permanece visível + effective_error
```

Com filtro e status indeterminado:

```text
409 AEE_V2_PLAN_LIST_EFFECTIVE_FILTER_INTEGRITY_BLOCKED
```

### 23.7 Query budget

Para candidatos:

```text
N = 1
N = 10
N = 100
N = 1000
```

Hard gate:

```text
heads <= 1
snapshots <= 1
```

### 23.8 Zero writes

Garantir ausência de:

```text
insert_one
update_one
update_many
delete_one
delete_many
replace_one
bulk_write
create_index
```

provocados pela listagem.

---

## 24. Testes frontend obrigatórios

Validar:

- status `ativo` efetivo renderiza **Vigente** mesmo com `plano.status = rascunho`;
- `rascunho` efetivo renderiza **Em elaboração**;
- `revisao`, `encerrado` e `cancelado` possuem labels corretos;
- `effective_error` renderiza aviso de integridade e não usa `plano.status` como fallback;
- dias vêm de `effective_summary.schedule_summary.days`;
- agenda heterogênea recebe indicação neutra sem horário inventado;
- `v2_managed` recebe badge apropriado;
- clicar Visualizar executa GET individual;
- visualização não usa o objeto cru da listagem como autoridade;
- `sidecar_active` renderiza `effective_dossier` do active;
- Fonte `legacy` renderiza a projeção efetiva legado;
- versão/revisão do active ficam identificáveis;
- botão PDF continua funcional;
- Editar/Duplicar/Excluir não têm enforcement novo nesta fase;
- ausência completa dos campos 6.6B permite fallback compatível para frontend antigo/rollback;
- presença de `effective_error` nunca permite fallback silencioso.

---

## 25. Gates obrigatórios

Antes de merge da futura implementação:

```text
AEE v2 - Contract Guard          = success
CI - Build & Lint                = success
Gate - Transferência             = success
```

Além disso:

- testes 6.6A continuam verdes;
- testes 6.6B continuam verdes;
- nova suíte 6.6C verde;
- build frontend verde;
- nenhum arquivo fora da fronteira aprovada sem justificativa/autorização;
- nenhum write/migração;
- hard gate de consultas V2 comprovado.

Um gate de outro módulo que rejeite genericamente arquivos AEE por scope não deve provocar mudanças fora do AEE. A causa deve ser classificada antes de qualquer correção.

---

## 26. Homologação futura em produção

A homologação 6.6C deverá usar novamente:

```text
school_id = 6e7aae6a-7b7b-42c7-a963-cac755b17ab4
academic_year = 2026
```

### 26.1 Listagem visual

Esperado no universo atual:

```text
22 Planos -> Em elaboração
1 Plano   -> Vigente
```

O caso sentinela deverá passar de **Em elaboração** para **Vigente** na tela **sem alterar o campo legado persistido `status=rascunho`**.

### 26.2 Badge V2

Esperado:

```text
3 Planos com indicação Dossiê V2
20 Planos sem governança V2
```

### 26.3 Filtro API efetivo

Requisição:

```text
GET /api/aee/planos?...&status_filter=ativo
```

Esperado:

```text
HTTP 200
total = 1
sentinela presente
```

Requisição:

```text
GET /api/aee/planos?...&status_filter=rascunho
```

Esperado:

```text
HTTP 200
total = 22
sentinela ausente
```

### 26.4 Visualização efetiva

Ao abrir o sentinela:

- GET individual executado;
- `effective_source = sidecar_active`;
- Dossiê exibido é o snapshot ativo;
- status mostrado = Vigente;
- versão/revisão exibidas;
- PDF continua coerente com a Fonte Efetiva.

### 26.5 Performance

Esperado:

```text
head_queries <= 1
snapshot_queries <= 1
integrity.errors = 0
```

Medir também:

```text
candidate_query_ms
batch_ms
materialize_ms
total_ms
```

Qualquer regressão sustentada relevante deve bloquear homologação até investigação.

---

## 27. Critérios de homologação 6.6C

| Critério | Esperado |
|---|---|
| Backend healthy | ✅ |
| Installer 6.6C único | ✅ |
| 6.6B não empilhada | ✅ |
| GET sem status_filter 200 | ✅ |
| 23 Planos preservados | ✅ |
| Sentinela visual = Vigente | ✅ |
| Campo legado do sentinela continua rascunho | ✅ |
| Filtro efetivo ativo total = 1 | ✅ |
| Filtro efetivo rascunho total = 22 | ✅ |
| Paginação posterior ao filtro | ✅ |
| Visualização usa GET individual | ✅ |
| Visualização usa effective_dossier | ✅ |
| 3 badges Dossiê V2 | ✅ |
| Integridade = 0 | ✅ |
| Heads queries <= 1 | ✅ |
| Snapshot queries <= 1 | ✅ |
| Nenhum write/migração | ✅ |
| PDFs/Diário sem regressão | ✅ |
| Botões de escrita sem enforcement novo | ✅ |

---

## 28. Rollback

Rollback de código:

1. remover/desativar installer 6.6C;
2. restaurar installer 6.6B;
3. restaurar frontend anterior da listagem/visualização;
4. redeploy do commit anterior.

Não é necessário:

- restaurar MongoDB;
- regravar `planos_aee`;
- remover heads;
- remover snapshots;
- reprocessar PDFs.

A fase não persiste dados.

---

## 29. Gate de autorização para implementação

Este documento **não autoriza implementação**.

A futura autorização deverá ser explícita, por exemplo:

> **Autorizo a implementação da Fase 6.6C — Cutover Controlado da Leitura/UX, conforme o Plano Executivo aprovado, incluindo a alteração mínima autorizada de `frontend/src/pages/DiarioAEE.js`, sem autorização para alterar `backend/routers/aee.py`, writes, PUT/duplicate ou demais superfícies bloqueadas.**

Se a implementação comprovar que `backend/routers/aee.py` precisa ser alterado, deverá parar e pedir autorização adicional antes de editar esse arquivo.

---

## 30. Decisão executiva

A 6.6C deve ser implementada como **um cutover atômico de leitura**:

```text
contrato 6.6B homologado
        ↓
status/dias da listagem pela Fonte Efetiva
        ↓
status_filter/total/paginação pela Fonte Efetiva
        ↓
visualização individual pela Fonte Efetiva
        ↓
sem writes
```

Não é aceitável fazer somente o badge/status visual e deixar `status_filter` calculado pelo legado, pois isso produziria uma tela visualmente efetiva sobre uma paginação semanticamente antiga.

Também não é aceitável antecipar a governança de escrita da 6.6D.

A implementação deve permanecer separada, reversível, observável e sujeita a nova autorização de merge e homologação em produção.
