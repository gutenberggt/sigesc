# AEE V2 — Fase 6.6B: Plano Executivo do Contrato Aditivo da Listagem

**Data-base:** 2026-08-23  
**Status:** PLANO EXECUTIVO — SEM IMPLEMENTAÇÃO  
**Pré-requisitos:** Fase 6.6 aprovada arquiteturalmente e Fase 6.6A homologada em produção  
**Superfície-alvo futura:** `GET /api/aee/planos`  
**Natureza da futura subfase:** read-only / contrato HTTP aditivo / sem cutover visual

## 1. Objetivo

Definir, antes de qualquer alteração de runtime, como a Fase 6.6B deverá expor na listagem de Planos AEE os metadados canônicos da Fonte Efetiva V2 sem remover, renomear ou reinterpretar os campos legado já consumidos pela interface atual.

A 6.6B é a ponte entre o Shadow Mode homologado na 6.6A e o cutover funcional futuro da 6.6C.

Princípio central:

> **resolver uma vez, preservar o legado e acrescentar um contrato explícito de Fonte Efetiva que o frontend ainda não é obrigado a consumir.**

A 6.6B não altera a autoridade visual da tela. O campo legado `status` continua existindo com o mesmo valor e o frontend pode continuar exibindo esse valor até a 6.6C.

## 2. Evidência de produção que autoriza a 6.6B

A 6.6A foi homologada em produção em 23/08/2026 sobre 23 Planos AEE reais da escola Dr. Almir Gabriel.

Resultado observado:

```text
legacy_status_distribution:
  rascunho = 23

effective_status_distribution:
  rascunho = 22
  ativo = 1

sources:
  legacy_only = 20
  working_only = 2
  active = 1

transitions:
  rascunho->rascunho = 22
  rascunho->ativo = 1

integrity.errors = 0
head_queries = 1
snapshot_queries = 1
```

O auditor populacional também comprovou que o caso sentinela produzirá impacto futuro nos filtros:

```text
status_filter=ativo:
  legacy_total = 0
  effective_total = 1
  false_negative_count = 1

status_filter=rascunho:
  legacy_total = 23
  effective_total = 22
  false_positive_count = 1
```

Essa evidência autoriza expor o contrato efetivo, mas não autoriza ainda aplicar o filtro efetivo no runtime. O cutover de `status_filter`, `total` e paginação permanece reservado à 6.6C.

## 3. Escopo exato da futura implementação 6.6B

Entrará:

- reutilização do resolver batch homologado da 6.6A;
- inclusão aditiva dos campos públicos de Fonte Efetiva em cada item retornado;
- política de mutação informativa por Plano;
- resumo mínimo de status e agenda;
- erro efetivo estruturado quando houver integridade comprometida;
- observabilidade própria da 6.6B;
- testes de compatibilidade estrutural e semântica;
- testes preparatórios de filtro efetivo sem ativar o cutover;
- substituição operacional do wrapper 6.6A pelo adapter 6.6B, garantindo uma única resolução batch por request.

Não entrará:

- alteração do valor legado `status`;
- alteração de `dias_atendimento` legado;
- alteração de `status_filter` no runtime;
- alteração de `total`, `skip` ou `limit`;
- reordenação efetiva da listagem;
- alteração do frontend;
- alteração do `PlanoAEEModal`;
- redirecionamento do botão Editar para o Dossiê;
- bloqueio real de PUT legado;
- bloqueio real de duplicação legado;
- migração/backfill;
- writes provocados pelo GET;
- dual-write;
- alteração de snapshots existentes;
- refatoração geral de `backend/routers/aee.py`.

## 4. Contrato HTTP aditivo por item

Cada item legado continuará contendo todos os campos atuais e receberá exclusivamente os seguintes campos novos:

```json
{
  "v2_managed": true,
  "effective_source": "sidecar_active",
  "effective_version": {
    "active_snapshot_id": "<uuid-ou-null>",
    "document_version": 1,
    "revision": 14,
    "working_snapshot_id": "<uuid-ou-null>"
  },
  "effective_summary": {
    "lifecycle_status": "active",
    "legacy_compatible_status": "ativo",
    "schedule_summary": {
      "days": ["segunda", "quarta"],
      "shape": "homogeneous"
    }
  },
  "effective_error": null,
  "mutation_policy": "dossier_v2_required"
}
```

O contrato é aditivo. Nenhum consumidor existente deve precisar mudar para continuar funcionando.

## 5. Semântica dos campos públicos

### 5.1 `v2_managed`

Booleano que informa se existe `aee_dossier_v2_head` para a âncora legado.

```text
false -> Plano ainda não ingressou na governança versionada V2
true  -> Plano já possui cadeia V2 e passa a ser administrado pelo Dossiê
```

`v2_managed=true` não significa, isoladamente, que a Fonte Efetiva seja `sidecar_active`. Um head working-only continua tendo Fonte Efetiva `legacy` conforme a 6.1A.

### 5.2 `effective_source`

Valores públicos permitidos:

```text
legacy
sidecar_active
null
```

Regras:

- sem head V2 -> `legacy`;
- head sem active íntegro, com working válido -> `legacy`;
- active íntegro -> `sidecar_active`;
- active necessário mas ausente/corrompido/mismatch -> `null`;
- falha estrutural que impeça afirmar a Fonte Efetiva -> `null`.

É proibido converter erro de integridade em `legacy` apenas para manter aparência de continuidade.

### 5.3 `effective_version`

Contrato estável:

```text
active_snapshot_id
working_snapshot_id
document_version
revision
```

Para `sidecar_active`, `document_version` e `revision` correspondem ao snapshot ativo íntegro.

Para Fonte Efetiva `legacy`, esses campos podem permanecer `null` quando não existe snapshot ativo. `working_snapshot_id` pode existir em estado working-only.

Os IDs são metadados técnicos do documento, não autorização para o frontend resolver autoridade por conta própria.

### 5.4 `effective_summary`

Objeto mínimo para consumo futuro da listagem:

```text
lifecycle_status
legacy_compatible_status
schedule_summary
```

Não deve carregar o Dossiê completo, textos pedagógicos, diagnóstico, objetivos, estratégias, avaliações ou outras seções extensas.

### 5.5 `effective_summary.lifecycle_status`

Vocabulário canônico V2 quando conhecido:

```text
draft
active
review
closed
cancelled
```

Para Fonte Efetiva legado, o valor pode ser projetado do status legado pelo mapeamento inverso canônico quando disponível.

### 5.6 `effective_summary.legacy_compatible_status`

Vocabulário já consumido pelo módulo legado:

```text
rascunho
ativo
revisao
encerrado
cancelado
```

O mapeamento deve permanecer semanticamente idêntico ao usado na 6.5B e 6.6A:

```text
draft     -> rascunho
active    -> ativo
review    -> revisao
closed    -> encerrado
cancelled -> cancelado
```

A 6.6B não deve criar uma terceira semântica de status.

### 5.7 `effective_summary.schedule_summary`

Contrato mínimo:

```json
{
  "days": ["segunda", "quarta"],
  "shape": "homogeneous"
}
```

Valores esperados de `shape`:

```text
legacy_projection
empty
homogeneous
heterogeneous
null
```

Regras:

- Fonte Efetiva legado -> dias do legado normalizados e `legacy_projection`;
- sidecar ativo -> dias derivados de `schedule.sessions[*].weekday` e shape calculado pelo resolver;
- integridade sem Fonte Efetiva -> `days` e `shape` podem ser `null`;
- agenda heterogênea nunca deve ser achatada para um horário único.

A 6.6B ainda não altera a UI; apenas torna a heterogeneidade explicitamente representável no contrato.

### 5.8 `effective_error`

Contrato:

```json
{
  "code": "AEE_V2_...",
  "message": "mensagem técnica segura"
}
```

ou `null` quando não há erro que comprometa a Fonte Efetiva.

`effective_error` deve representar o erro principal que impede afirmar a Fonte Efetiva. Erros de working que não invalidam um active íntegro não devem falsificar `effective_source`; porém precisam influenciar a política de mutação conforme seção 6.

A mensagem não deve conter PII ou conteúdo pedagógico.

## 6. `mutation_policy` — política informativa da 6.6B

Valores públicos permitidos:

```text
legacy_allowed
dossier_v2_required
blocked_integrity
```

A 6.6B apenas informa a política. O enforcement backend de PUT/duplicate será implementado na 6.6D.

### 6.1 Sem head V2

```text
v2_managed = false
effective_source = legacy
mutation_policy = legacy_allowed
```

A edição legado continua tecnicamente disponível conforme RBAC atual.

### 6.2 Working-only íntegro

```text
v2_managed = true
effective_source = legacy
mutation_policy = dossier_v2_required
```

O conteúdo oficial ainda é legado, mas a governança já migrou para a cadeia versionada.

### 6.3 Active íntegro

```text
v2_managed = true
effective_source = sidecar_active
mutation_policy = dossier_v2_required
```

### 6.4 Erro de integridade principal

Quando `integrity_error` compromete head/active/resolução:

```text
mutation_policy = blocked_integrity
```

### 6.5 Working quebrado com active íntegro

O active continua sendo a Fonte Efetiva:

```text
effective_source = sidecar_active
```

Porém a cadeia de trabalho está degradada. Para não sugerir uma mutação V2 segura sobre uma cadeia inconsistente:

```text
mutation_policy = blocked_integrity
```

Assim, a 6.6B distingue autoridade de leitura de segurança de mutação.

## 7. Compatibilidade com o contrato legado

A futura implementação deve garantir, para cada item, que todos os pares chave/valor legado permaneçam idênticos aos produzidos pelo endpoint original antes da adição dos novos campos.

Exemplo sentinela:

```json
{
  "status": "rascunho",
  "v2_managed": true,
  "effective_source": "sidecar_active",
  "effective_summary": {
    "lifecycle_status": "active",
    "legacy_compatible_status": "ativo",
    "schedule_summary": {"days": ["..."], "shape": "homogeneous"}
  },
  "mutation_policy": "dossier_v2_required"
}
```

Na 6.6B é correto que `status` e `effective_summary.legacy_compatible_status` sejam diferentes. Essa diferença é justamente o GAP tornado explícito.

O frontend não deve ser alterado para trocar qual campo renderiza nesta subfase.

## 8. Estratégia de runtime: substituir, não empilhar, a 6.6A

A 6.6A atualmente instala um wrapper que:

1. executa o endpoint legado;
2. chama `resolve_plan_list_effective_batch()`;
3. registra diagnóstico;
4. devolve a resposta legado.

Se a 6.6B fosse simplesmente instalada por cima desse wrapper e chamasse novamente o resolver, cada request poderia executar:

```text
2 queries de heads
2 queries de snapshots
```

Isso duplicaria trabalho e violaria o hard gate arquitetural.

A 6.6B deverá portanto **substituir operacionalmente o installer 6.6A**, não empilhá-lo.

Estratégia planejada:

- `backend/aee_v2/plan_list_shadow.py` permanece no repositório como implementação e referência da 6.6A;
- `backend/routers/__init__.py` deixa de instalar `install_aee_v2_plan_list_shadow_setup(_aee_mod)`;
- passa a instalar apenas o adapter 6.6B;
- o adapter 6.6B executa o endpoint legado diretamente;
- chama `resolve_plan_list_effective_batch()` exatamente uma vez;
- projeta o contrato público aditivo;
- registra observabilidade 6.6B;
- retorna a resposta aditiva.

Não é necessário apagar a 6.6A para avançar a cadeia. O marco permanece testável e documentado, mas deixa de ser o wrapper ativo.

## 9. Reutilização obrigatória do resolver homologado

A 6.6B deve reutilizar `backend/aee_v2/plan_list_effective.py`.

É proibido criar um segundo algoritmo independente para:

- buscar heads;
- buscar snapshots;
- validar hash;
- validar contrato persistido;
- validar identidade;
- mapear status;
- determinar Fonte Efetiva.

Mudanças no resolver só são aceitáveis se forem aditivas e necessárias para materializar o contrato público, mantendo paridade com a semântica homologada.

## 10. Componentes planejados para a futura PR de implementação

Fronteira preferencial:

### 10.1 `backend/aee_v2/plan_list_contract.py` — novo

Responsabilidades:

- instalar o adapter 6.6B;
- executar o legado primeiro;
- chamar o resolver batch uma vez;
- casar summaries por `legacy_plano_id` sem N+1;
- copiar/preservar cada item legado;
- acrescentar os seis campos públicos;
- derivar `mutation_policy`;
- produzir observabilidade agregada;
- não fazer writes.

### 10.2 `backend/aee_v2/plan_list_effective.py` — apenas se necessário

Mudanças permitidas:

- enriquecer o summary técnico com informação mínima necessária ao contrato;
- extrair helper puro reutilizável;
- manter integralmente as invariantes 6.6A.

Mudanças proibidas:

- alterar semântica da Fonte Efetiva;
- adicionar query por item;
- escrever no banco;
- criar índices;
- relaxar validação de integridade.

### 10.3 `backend/tests/test_aee_v2_plan_list_contract.py` — novo

Cobertura específica da 6.6B.

### 10.4 `backend/tests/test_aee_v2_plan_list_shadow.py`

Manter a suíte 6.6A verde. Alteração somente se estritamente necessária para garantir coexistência histórica/testes do adapter desinstalado do runtime.

### 10.5 `.github/workflows/aee-v2-contract.yml`

Adicionar compile/test da 6.6B sem remover os testes anteriores.

### 10.6 `backend/routers/__init__.py`

Trocar o installer runtime 6.6A pelo installer 6.6B.

### 10.7 Arquivos explicitamente fora da fronteira

Não tocar na 6.6B:

- `backend/routers/aee.py`;
- `frontend/src/pages/DiarioAEE.js`;
- `frontend/src/components/PlanoAEEModal.js`;
- PDFs;
- modelos persistidos;
- scripts de migração;
- dados existentes.

Qualquer necessidade de tocar nesses caminhos exige reavaliação e autorização explícita.

## 11. Construção da resposta aditiva

A resposta legado atual é:

```json
{
  "items": [...],
  "total": 23
}
```

A 6.6B deve preservar o top-level exatamente, salvo pelos campos adicionados dentro de cada item.

Algoritmo:

1. executar endpoint legado;
2. validar defensivamente `dict` + `items` list;
3. chamar resolver batch sobre a página já autorizada/filtrada/paginada;
4. indexar summaries por `legacy_plano_id` em memória;
5. para cada item legado, criar cópia rasa do item;
6. adicionar os campos públicos;
7. manter ordem original;
8. manter `total` original;
9. retornar novo objeto top-level semanticamente compatível.

A cópia evita que o adapter precise alterar objetos que outras camadas possam manter como referência interna.

## 12. Tratamento de falhas

A 6.6B não pode usar o fail-open silencioso da 6.6A para qualquer erro V2, porque os campos aditivos passam a fazer parte do contrato HTTP.

Devem existir duas classes de falha.

### 12.1 Erro de integridade por Plano — representável

Exemplos:

- active snapshot ausente;
- hash inválido;
- identity mismatch;
- status V2 não mapeado.

O endpoint continua `200` se o legado foi listado com sucesso, mas o item deve expor:

```text
effective_source = null
effective_error = {...}
mutation_policy = blocked_integrity
```

O legado do item continua disponível como referência, sem ser promovido falsamente a Fonte Efetiva.

### 12.2 Falha inesperada do adapter/resolver inteiro

Exemplos:

- exceção de programação;
- retorno estruturalmente inválido do resolver;
- impossibilidade de casar summaries com a página.

Como a 6.6B anuncia um contrato aditivo canônico, não deve devolver silenciosamente uma resposta sem os campos novos e fingir sucesso contratual.

Plano proposto:

- preservar a exceção/HTTP normal do endpoint legado quando ela ocorre antes da camada V2;
- se o legado retornou sucesso mas a camada 6.6B falha globalmente, registrar `ERROR` estruturado;
- retornar falha controlada `503 Service Unavailable` com código funcional estável, por exemplo `AEE_V2_PLAN_LIST_CONTRACT_UNAVAILABLE`, em vez de contrato parcialmente ausente.

Esse comportamento deverá ser confirmado na revisão de implementação. A razão é evitar que consumidores futuros passem a interpretar ausência dos campos como `legacy`.

## 13. Observabilidade

Evento proposto:

```text
AEE_V2_PLAN_LIST_ADDITIVE
```

Payload agregado mínimo:

```text
phase = 6.6B
mode = additive_contract
status = effective | divergent | partial_error
scope
page
sources
mutation_policies
status_compare
schedule_compare
integrity
performance
```

Regras:

- nenhum nome de estudante/professor;
- nenhum texto pedagógico;
- nenhum diagnóstico clínico;
- nenhum `student_id`/`professor_aee_id` no agregado;
- nenhuma URI/credencial;
- `sidecar_active`, divergência ou integridade devem permanecer visíveis no nível de logging usado em produção durante homologação.

A 6.6B poderá reutilizar helpers puros de diagnóstico da 6.6A, desde que isso não instale o wrapper antigo nem execute o resolver duas vezes.

## 14. Hard gate de performance

Por request da listagem:

```text
heads:     0 ou 1 query
snapshots: 0 ou 1 query
total V2:  máximo 2 queries
```

Casos obrigatórios de teste:

```text
N=0
N=1
N=10
N=100
```

Todos devem respeitar o mesmo teto.

O adapter 6.6B não corrige o N+1 legado de enriquecimento de estudantes; essa dívida permanece fora do escopo.

## 15. Testes obrigatórios

### 15.1 Contrato aditivo

- item legacy-only recebe os seis campos novos;
- item working-only recebe Fonte Efetiva legado e `dossier_v2_required`;
- item active recebe `sidecar_active`;
- item de integridade recebe `effective_source=null`, `effective_error` e `blocked_integrity`;
- active íntegro + working quebrado preserva `sidecar_active` e usa `blocked_integrity`;
- nenhum campo legado é removido ou sobrescrito;
- ordem dos itens é preservada;
- `total` legado é preservado;
- `status`, `dias_atendimento`, `student_name` e demais campos legado permanecem idênticos.

### 15.2 Status

- mapa V2->legado idêntico à 6.5B/6.6A;
- sentinela `rascunho + active -> effective ativo`;
- status legado continua `rascunho` na resposta 6.6B;
- status efetivo aparece somente no campo aditivo.

### 15.3 Agenda

- legacy_projection;
- active sem sessões -> empty;
- active homogêneo -> homogeneous;
- active heterogêneo -> heterogeneous;
- dias normalizados e ordenados conforme helper homologado;
- nenhuma invenção de horário único para agenda heterogênea.

### 15.4 Política de mutação

- sem head -> legacy_allowed;
- working-only íntegro -> dossier_v2_required;
- active íntegro -> dossier_v2_required;
- erro principal -> blocked_integrity;
- active íntegro + working quebrado -> blocked_integrity.

### 15.5 Performance

- no máximo 1 query heads;
- no máximo 1 query snapshots;
- nenhum resolver individual em loop;
- nenhum `find_one` V2 por Plano;
- nenhum `create_index`;
- zero writes.

### 15.6 Instalação

- installer idempotente;
- FastAPI 0.110.1 / `include_router()` preservado;
- exatamente uma camada de listagem V2 ativa;
- installer 6.6A não fica empilhado sob a 6.6B;
- testes históricos 6.6A permanecem verdes.

### 15.7 Preparação da 6.6C sem cutover

Criar helper/teste puro que demonstre sobre um universo candidato:

```text
legacy rascunho + effective ativo
```

que:

```text
filtro legado ativo -> exclui
filtro efetivo ativo -> inclui
```

E o inverso para `rascunho`.

Esse teste não deve mudar a consulta runtime da 6.6B.

## 16. Gates CI

A futura PR de implementação só poderá ser candidata a merge com:

1. **AEE v2 - Contract Guard** verde;
2. **CI - Build & Lint** verde;
3. **Gate - Transferência (Regressão)** verde.

Gates correlatos que falhem apenas por política de escopo de outro módulo devem ser analisados, não contornados mediante alteração fora da fronteira AEE.

## 17. Critérios de homologação em produção

Usar novamente a escola Dr. Almir Gabriel e o caso sentinela já homologado.

### 17.1 Página

Esperado:

```text
items = 23
total = 23
HTTP = 200
```

Nenhuma mudança visual esperada.

### 17.2 Distribuição esperada

```text
20 legacy_only
2 working_only
1 active
```

### 17.3 Sentinela active

Deve expor simultaneamente:

```text
status = rascunho
v2_managed = true
effective_source = sidecar_active
effective_summary.lifecycle_status = active
effective_summary.legacy_compatible_status = ativo
mutation_policy = dossier_v2_required
effective_error = null
```

### 17.4 Working-only

Cada um deve expor:

```text
v2_managed = true
effective_source = legacy
mutation_policy = dossier_v2_required
```

sem promover working para Fonte Efetiva.

### 17.5 Legacy-only

Os 20 restantes devem expor:

```text
v2_managed = false
effective_source = legacy
mutation_policy = legacy_allowed
```

### 17.6 Integridade

Esperado:

```text
errors = 0
```

Qualquer erro novo bloqueia homologação até investigação.

### 17.7 Performance

Esperado:

```text
head_queries <= 1
snapshot_queries <= 1
```

O batch deve permanecer dentro do guardrail operacional já estabelecido; regressão sustentada superior a 20% deve ser investigada antes de encerrar a subfase.

### 17.8 Frontend

A aba Planos deve permanecer visualmente igual à versão anterior. Em especial, o sentinela ainda pode aparecer como **Em elaboração** na 6.6B, pois o cutover visual é deliberadamente da 6.6C.

## 18. Rollback

Rollback da 6.6B não exige restauração de banco porque não haverá writes.

Procedimento conceitual:

1. retornar ao commit anterior;
2. reinstalar operacionalmente o wrapper 6.6A;
3. redeploy automático;
4. confirmar novamente `GET /api/aee/planos` e `AEE_V2_PLAN_LIST_SHADOW`.

Nenhum snapshot, head ou Plano legado deve ser alterado pelo rollback.

## 19. Invariantes finais

A implementação da 6.6B não poderá violar:

1. nenhum write provocado por `GET /aee/planos`;
2. nenhuma migração/backfill;
3. nenhum `updateMany`;
4. nenhum snapshot regravado;
5. hashes/encadeamento imutáveis;
6. nenhum dual-write;
7. nenhum fallback silencioso em erro de active;
8. working-only nunca vira Fonte Efetiva V2;
9. `legacy_plano_id` permanece âncora;
10. RBAC/professor scope não muda;
11. `status_filter`, total e paginação não mudam na 6.6B;
12. frontend não muda;
13. PUT/duplicate não são bloqueados ainda;
14. apenas uma resolução batch V2 por request;
15. no máximo duas queries V2 por lote;
16. Diário, PDFs, Dossiê, delete guard e time integrity não podem regredir;
17. `backend/routers/aee.py` permanece bloqueado e intacto salvo autorização explícita futura.

## 20. Gate de autorização

Este documento é exclusivamente planejamento.

A aprovação/merge deste plano **não autoriza implementação automática**.

Após validação documental e gates, a implementação da 6.6B deverá receber autorização explícita separada, em PR próprio, preservando a fronteira definida neste documento.
