# AEE V2 — Fase 6.6A: Plano Executivo da Listagem em Shadow Mode

**Data-base:** 2026-08-23  
**Status:** PLANO EXECUTIVO — SEM IMPLEMENTAÇÃO  
**Pré-requisito:** Fase 6.6 aprovada arquiteturalmente  
**Superfície-alvo futura:** `GET /api/aee/planos`  
**Natureza da futura subfase:** read-only / observacional / fail-open para a resposta legado

## 1. Objetivo

Definir, antes de qualquer alteração de runtime, como a Fase 6.6A deverá observar a listagem de Planos AEE e comparar o que o endpoint legado devolve com a Fonte Efetiva V2.

A 6.6A não corrige ainda a listagem. Ela produz evidência operacional suficiente para autorizar ou bloquear a 6.6B.

O princípio central é:

> **executar o legado primeiro, observar em lote depois e devolver exatamente a mesma resposta legado.**

Nenhum campo `effective_*` será adicionado ao JSON na 6.6A. Nenhum status visual será alterado. Nenhum filtro, total, paginação, botão ou fluxo de edição será modificado.

## 2. Evidências que determinam o desenho

O endpoint legado atual:

1. monta `filter_query` com `school_id`, `student_id`, `academic_year`, `status_filter` e `professor_aee_id`;
2. acrescenta o escopo especial do professor (`professor_aee_id == uid OR created_by == uid`);
3. aplica `skip` e `limit` diretamente em `planos_aee`;
4. enriquece cada item com nome do estudante;
5. calcula `total` com o mesmo filtro legado;
6. retorna `{items, total}`.

Consequência importante: quando `status_filter` é usado, um Plano `rascunho` no legado e `active` no V2 pode ser incluído ou excluído antes de qualquer camada V2 observar a requisição.

Por isso a 6.6A terá **dois planos de evidência complementares**:

- **Plano A — Shadow online da página retornada:** observa somente os itens que o endpoint legado já autorizou, filtrou e paginou.
- **Plano B — Auditor populacional read-only:** mede, fora do caminho online, falsos positivos/negativos de status e impacto potencial em total/paginação.

Essa separação evita duplicar RBAC, filtro e paginação dentro do wrapper de produção.

## 3. Escopo exato da futura implementação 6.6A

Entrará:

- resolução batch read-only de heads/snapshots para uma coleção de Planos legado já autorizados;
- summary técnico mínimo por Plano para diagnóstico;
- comparação de status legado × efetivo;
- comparação do resumo de agenda que a listagem representa;
- identificação de Planos legacy-only, working-only e sidecar-active;
- detecção de falhas de integridade;
- métricas de custo/round-trips do batch;
- log estruturado `AEE_V2_PLAN_LIST_SHADOW`;
- auditor de população executável manualmente em modo read-only;
- testes permanentes no `AEE v2 - Contract Guard`.

Não entrará:

- alteração do JSON de `GET /aee/planos`;
- alteração de `status_filter`, `total`, `skip` ou `limit`;
- alteração do frontend;
- alteração do `PlanoAEEModal`;
- bloqueio de PUT/duplicate;
- qualquer write no MongoDB;
- criação de índices no caminho de leitura;
- backfill, bootstrap ou migração;
- refatoração geral de `backend/routers/aee.py`;
- 6.6B, 6.6C ou 6.6D.

## 4. Componentes planejados para a futura PR de implementação

A implementação deverá preferir novos arquivos isolados.

### 4.1 `backend/aee_v2/plan_list_effective.py`

Responsabilidade:

- resolver summaries em lote;
- consultar heads em lote;
- consultar snapshots necessários em lote;
- validar integridade;
- produzir resultado técnico sem instalar rota ou logger.

Esse módulo deve ser reutilizável posteriormente pela 6.6B/6.6C, evitando que o algoritmo batch seja reescrito no cutover.

### 4.2 `backend/aee_v2/plan_list_shadow.py`

Responsabilidade:

- envolver somente `GET /aee/planos`;
- executar o endpoint atual primeiro;
- entregar os itens retornados ao resolver batch;
- calcular métricas de paridade/divergência;
- registrar observabilidade;
- devolver o mesmo objeto do legado.

### 4.3 `backend/scripts/audit_aee_v2_plan_list_6_6a.py`

Responsabilidade:

- auditoria populacional manual read-only;
- analisar universo de candidatos sem `status_filter` legado;
- medir diferença entre conjuntos legado e efetivo;
- não fazer insert/update/delete/create_index.

### 4.4 `backend/tests/test_aee_v2_plan_list_shadow.py`

Cobertura unitária e de integração do batch + wrapper + observabilidade.

Poderá ser separado em dois arquivos se o volume de casos justificar, mas não deve haver fragmentação desnecessária.

### 4.5 `.github/workflows/aee-v2-contract.yml`

Adicionar compile/test dos novos módulos e do auditor.

### 4.6 `backend/routers/__init__.py`

Único ponto de instalação runtime planejado para a 6.6A.

`backend/routers/aee.py` deve permanecer intacto.

## 5. Algoritmo batch canônico

### 5.1 Entrada

O resolver recebe uma sequência dos Planos legado que já pertencem ao escopo analisado.

Cada item precisa, no mínimo, de:

- `id`;
- `student_id`;
- `school_id`;
- `academic_year`;
- `status`;
- `dias_atendimento`;
- campos de agenda necessários ao diagnóstico técnico.

O resolver não consulta novamente `planos_aee` item a item.

### 5.2 Deduplicação

1. extrair `legacy_plano_id` válidos;
2. deduplicar IDs preservando associação com os itens de origem;
3. Plano sem `id` gera diagnóstico local de erro e não provoca query individual.

### 5.3 Round-trip 1 — heads

Executar **uma única consulta**:

```text
aee_dossier_v2_heads.find({
  legacy_plano_id: { $in: [...] }
})
```

Usar projeção somente com os campos necessários ao read model:

- `legacy_plano_id`;
- identidades do head;
- `active_snapshot_id`;
- `working_snapshot_id`;
- `head_revision`;
- metadados estritamente necessários.

Não chamar `ensure_indexes()` no Shadow. GET observacional não pode produzir `create_index`.

### 5.4 Round-trip 2 — snapshots

Construir a união deduplicada dos IDs apontados por:

- `active_snapshot_id`;
- `working_snapshot_id`.

Se a união estiver vazia, nenhuma query de snapshot deve ocorrer.

Caso exista conteúdo, executar **uma única consulta**:

```text
aee_dossier_v2_snapshots.find({
  id: { $in: [...] }
})
```

O snapshot deve ser carregado com todos os campos necessários à verificação do SHA-256; projeção parcial que inviabilize o hash é proibida.

### 5.5 Validação

Para cada snapshot necessário:

1. verificar hash com a função canônica já existente;
2. validar contrato persistido `AEEV2Snapshot`;
3. verificar `snapshot.legacy_plano_id == head.legacy_plano_id`;
4. verificar coerência das identidades estruturais relevantes com a âncora legado;
5. classificar ausência, corrupção ou mismatch sem fallback silencioso falso.

A semântica de Fonte Efetiva deve permanecer equivalente à 6.1A:

- sem head → `legacy`;
- head working-only → Fonte Efetiva ainda `legacy`;
- active íntegro → `sidecar_active`;
- active ausente/corrompido/mismatch → erro de integridade e `effective_source = null`.

Falha do working snapshot deve ser registrada separadamente. Ela não transforma um active íntegro em legado, mas indica problema de governança da cadeia.

### 5.6 Limite de round-trips V2

Para N Planos analisados:

- heads: 0 ou 1 query;
- snapshots: 0 ou 1 query;
- total V2: **máximo 2 queries**, independentemente de N.

Fica proibido no resolver batch:

- `find_one` dentro de loop de Planos;
- resolver individual 6.1A chamado N vezes;
- query individual por snapshot;
- `create_index` no request;
- qualquer escrita.

A 6.6A não corrige o N+1 já existente do enriquecimento de estudantes no endpoint legado; apenas não acrescenta novo N+1 V2.

## 6. Read model interno do Shadow

A 6.6A não expõe esse modelo ao HTTP. Ele existe apenas em memória para diagnóstico.

Por Plano:

```text
legacy_plano_id
v2_managed
management_state:
  legacy_only | working_only | active | integrity_error

effective_source:
  legacy | sidecar_active | null

effective_version:
  active_snapshot_id
  document_version
  revision
  working_snapshot_id

legacy_status
effective_lifecycle_status
effective_legacy_status

legacy_days
effective_days
schedule_shape

status_parity
days_parity
integrity_error
working_integrity_error
```

Esse objeto nunca deve conter nome do estudante para logging técnico.

## 7. Comparação de status

### 7.1 Vocabulário

O Shadow deve comparar o status efetivo projetado para o vocabulário legado usado pela listagem.

O mapeamento deve permanecer semanticamente idêntico ao já usado na 6.5B, incluindo:

```text
draft     -> rascunho
active    -> ativo
review    -> revisao
closed    -> encerrado
cancelled -> cancelado
```

A 6.6A não deve refatorar a 6.5B apenas para compartilhar essa constante. Se houver duplicação temporária, um teste de contrato deve exigir paridade entre os mapeamentos para evitar drift.

### 7.2 Métrica de transição

Cada comparação válida gera:

```text
<legacy_status> -> <effective_legacy_status>
```

Exemplo sentinela esperado:

```text
rascunho -> ativo
```

A transição é divergência funcional esperada, não erro de integridade.

## 8. Comparação de agenda da listagem

A 6.6A deve medir primeiro o que a listagem efetivamente representa hoje.

A tabela atual usa `dias_atendimento`; portanto a métrica principal será a paridade dos dias.

### 8.1 Normalização de dias

- remover valores vazios;
- normalizar whitespace;
- deduplicar somente para comparação semântica;
- ordenar pela ordem canônica segunda → sexta quando possível;
- valores desconhecidos permanecem explicitamente comparáveis, não são descartados silenciosamente.

### 8.2 V2

`effective_days` será derivado de `dossier.schedule.sessions[*].weekday`.

### 8.3 Métricas

- `days_compared_count`;
- `days_equal_count`;
- `days_divergent_count`;
- `schedule_heterogeneous_count`.

`schedule_heterogeneous_count` é informacional: indica sessões V2 com horários/local/modalidade diferentes. Isso não é erro da 6.6A, mas antecipa a necessidade de um resumo neutro na 6.6B/6.6C.

A 6.6A não deve declarar divergência da listagem por campos que a listagem atual não mostra.

## 9. Plano A — Shadow online da página retornada

### 9.1 Ordem de execução

O wrapper deve obedecer:

1. executar `GET /aee/planos` legado;
2. capturar o objeto retornado;
3. validar defensivamente se existe `dict` com `items` list;
4. resolver os `items` em batch;
5. calcular diagnóstico agregado;
6. registrar log;
7. devolver **o mesmo resultado legado**.

O Shadow não pode alterar:

- `items`;
- ordem dos itens;
- `student_name` já enriquecido;
- `total`;
- headers;
- status HTTP;
- exceções normais do endpoint legado.

### 9.2 Falha do Shadow

Qualquer falha inesperada do adapter:

- gera log visível;
- nunca converte um 200 legado em 5xx;
- nunca injeta erro no corpo;
- retorna o resultado legado sem modificação.

A exceção é apenas estrutural de instalação: se a rota alvo não existir no startup, o installer deve falhar rápido, como os adapters AEE v2 anteriores.

## 10. Limitação deliberada do Shadow online

Se a requisição contém `status_filter`, o endpoint legado já filtrou antes do Shadow.

Assim, o runtime consegue detectar **falsos positivos entre os itens retornados**, por exemplo:

```text
status_filter=rascunho
legado=rascunho
effective=ativo
```

Esse item foi retornado pelo filtro legado, mas não pertenceria ao filtro efetivo.

O runtime **não consegue detectar falsos negativos** sem executar uma segunda listagem fora do filtro legado.

A 6.6A não deverá duplicar a consulta completa/RBAC dentro do request apenas para preencher essa lacuna. Em vez disso, usará o Plano B.

## 11. Plano B — Auditor populacional read-only

O auditor manual deve consultar o universo base sem `status_filter` e sem paginação funcional, respeitando escopo explicitamente informado.

Parâmetros previstos:

- `--school-id` opcional;
- `--academic-year` obrigatório para auditoria de produção normal;
- `--student-id` opcional para caso sentinela;
- `--professor-user-id` opcional para simular o escopo professor;
- limite de segurança configurável para impedir varredura acidental irrestrita.

Ele deve calcular:

- distribuição de status legado;
- distribuição de status efetivo;
- transições legado → efetivo;
- legacy-only / working-only / sidecar-active;
- erros de integridade;
- paridade de dias;
- heterogeneidade de agenda;
- para cada status conhecido:
  - conjunto que o filtro legado selecionaria;
  - conjunto que o filtro efetivo selecionaria;
  - `false_positive_count`;
  - `false_negative_count`;
- diferença de `total` que existiria após cutover;
- simulação opcional de páginas para `skip/limit`, sem alterar endpoint.

O auditor é proibido de:

- `insert_one`;
- `update_one`/`update_many`;
- `delete_one`/`delete_many`;
- `find_one_and_update`;
- `create_index`;
- bootstrap;
- ativação/revisão de Dossiê.

## 12. Métricas do evento online

Evento:

```text
AEE_V2_PLAN_LIST_SHADOW
```

Payload mínimo:

```json
{
  "phase": "6.6A",
  "mode": "shadow_read_only",
  "status": "parity|divergent|partial_error",
  "scope": {
    "academic_year": 2026,
    "school_filter": true,
    "student_filter": false,
    "professor_filter": false,
    "status_filter": "rascunho|null",
    "role": "<role>"
  },
  "page": {
    "skip": 0,
    "limit": 100,
    "items_returned": 0,
    "legacy_total": 0
  },
  "sources": {
    "v2_managed": 0,
    "legacy_effective": 0,
    "working_only": 0,
    "sidecar_active": 0
  },
  "status_compare": {
    "compared": 0,
    "equal": 0,
    "divergent": 0,
    "transitions": {}
  },
  "schedule_compare": {
    "days_compared": 0,
    "days_equal": 0,
    "days_divergent": 0,
    "heterogeneous_v2": 0
  },
  "filter_shadow": {
    "returned_effective_mismatch": 0,
    "population_audit_required": false
  },
  "integrity": {
    "errors": 0,
    "working_errors": 0,
    "by_code": {}
  },
  "performance": {
    "head_queries": 0,
    "snapshot_queries": 0,
    "batch_ms": 0.0,
    "shadow_ms": 0.0
  }
}
```

## 13. Privacidade e cardinalidade de logs

O log agregado não deve carregar:

- nome do estudante;
- nome do professor;
- texto pedagógico;
- diagnóstico/laudo;
- conteúdo do Dossiê;
- student_id;
- professor_aee_id.

Pode registrar:

- `academic_year`;
- role;
- presença/ausência de filtros;
- `status_filter`;
- contagens;
- códigos técnicos de erro;
- métricas de tempo.

`legacy_plano_id` não entra no evento agregado.

Quando um erro de integridade precisar de rastreabilidade operacional, poderá existir evento técnico separado e restrito com `legacy_plano_id` + código, sem PII textual.

## 14. Política de níveis de logging

O ambiente de produção atual opera com root efetivo `WARNING`. A 6.6A não deve repetir o GAP de observabilidade encontrado na 6.5B.

Política proposta:

- página totalmente legacy-only e sem anomalia → `INFO`;
- `sidecar_active > 0` → `WARNING` durante a janela temporária de homologação 6.6A;
- qualquer divergência de status/dias → `WARNING`;
- qualquer mismatch de filtro entre itens retornados → `WARNING`;
- qualquer erro de integridade → `WARNING`;
- falha inesperada do adapter → `ERROR/exception`.

O uso de `WARNING` para sidecar ativo na 6.6A é telemetria temporária de cutover, não indicação automática de falha funcional. A política deve ser revista na 6.6B para evitar ruído permanente.

## 15. Estado global do diagnóstico

Precedência:

1. se houver erro de integridade/resolução → `partial_error`;
2. senão, se houver divergência de status, dias ou filtro retornado → `divergent`;
3. caso contrário → `parity`.

`sidecar_active` em paridade continua com `status=parity`; sua presença altera apenas o nível do log durante homologação.

## 16. Testes obrigatórios — resolver batch

### 16.1 Base

- entrada vazia: zero queries;
- um Plano sem head: uma query de heads, zero snapshots;
- vários Planos sem head: uma query de heads, zero snapshots;
- IDs duplicados: consulta deduplicada.

### 16.2 Working

- head working-only: `v2_managed=true`, Fonte Efetiva `legacy`;
- working snapshot válido contabilizado;
- working pointer inexistente gera `working_integrity_error`, sem falso `sidecar_active`;
- working snapshot adulterado é detectado.

### 16.3 Active

- active íntegro: `sidecar_active`;
- active inexistente: erro, sem fallback legado falso;
- active adulterado: erro de hash;
- active pertencente a outro `legacy_plano_id`: erro de identidade;
- contrato de snapshot inválido: erro de integridade;
- active + working coexistentes são resolvidos no mesmo lote.

### 16.4 Paridade com 6.1A

Para cenários suportados, o resultado do batch deve concordar com `resolve_effective_dossier()` quanto a:

- Fonte Efetiva;
- snapshot ativo;
- versão/revisão;
- lifecycle efetivo.

O teste evita criação de uma segunda semântica de Fonte Efetiva.

### 16.5 N+1

Com 1, 10 e 100 Planos:

- `head_queries <= 1`;
- `snapshot_queries <= 1`;
- nenhuma chamada `find_one` por Plano;
- zero writes;
- zero `create_index`.

## 17. Testes obrigatórios — diagnóstico Shadow

- resultado legado é devolvido sem mutação;
- idealmente o mesmo objeto retornado pelo endpoint original é preservado;
- ordem de `items` permanece idêntica;
- `total` permanece idêntico;
- nenhum `effective_*` aparece no HTTP;
- legacy `rascunho` × V2 `active` gera transição `rascunho->ativo`;
- status iguais geram paridade;
- dias iguais geram paridade;
- dias divergentes são contabilizados;
- agenda heterogênea é contada sem inventar horário único;
- `status_filter=rascunho` + efetivo `ativo` incrementa `returned_effective_mismatch`;
- sem `status_filter`, `population_audit_required=false`;
- com `status_filter`, o payload reconhece que auditor populacional é necessária;
- erro do Shadow preserva resposta legado;
- rota alvo ausente falha no startup/installer;
- instalação é idempotente;
- wrapper sobrevive ao `FastAPI.include_router()` 0.110.1.

## 18. Testes de observabilidade

- legacy-only limpo → INFO;
- sidecar-active → WARNING;
- divergência → WARNING;
- integridade quebrada → WARNING;
- falha inesperada → ERROR/exception;
- payload agregado não contém nomes, student_id ou professor_aee_id;
- transições de status têm cardinalidade limitada ao vocabulário conhecido.

## 19. Testes do auditor populacional

- dry/read-only por construção;
- mesma população base produz conjuntos legado/efetivo reproduzíveis;
- falso positivo de filtro é identificado;
- falso negativo de filtro é identificado;
- total legado × total efetivo calculado corretamente;
- simulação de paginação não escreve nem altera documentos;
- escopo professor simulado usa a mesma regra `professor_aee_id OR created_by`;
- limite de segurança impede varredura irrestrita acidental.

## 20. Gate CI

A futura PR 6.6A deverá atualizar `AEE v2 - Contract Guard` para:

- compilar novos módulos;
- compilar o auditor;
- executar os testes 6.6A;
- manter todos os testes AEE v2 anteriores.

Gates críticos obrigatórios:

- `AEE v2 - Contract Guard`;
- `CI - Build & Lint`;
- `Gate - Transferência (Regressão)`.

Também devem permanecer verdes os guards correlatos já acionados pelo repositório.

## 21. Limites de performance

### Hard gate arquitetural

- no máximo 2 round-trips Mongo V2 por lote;
- nenhuma consulta V2 por item;
- nenhum write;
- nenhum index build.

### Guardrail operacional

Durante homologação, coletar `batch_ms` e `shadow_ms` no servidor.

Critérios iniciais:

- página `limit <= 100` não deve apresentar aumento recorrente de latência que descaracterize o endpoint;
- como guardrail, `batch_ms` deve permanecer preferencialmente abaixo de 100 ms em condições normais;
- comparar mediana de requisições equivalentes antes/depois do deploy; regressão sustentada superior a 20% exige investigação antes da 6.6B.

Os valores de 100 ms/20% são guardrails operacionais, não autorização para mascarar N+1 ou erros. O hard gate de quantidade de queries prevalece.

## 22. Homologação em produção da 6.6A

### 22.1 Antes do deploy

Registrar:

- commit atualmente em produção;
- container backend ativo;
- baseline de resposta do endpoint para escola/ano do caso sentinela;
- baseline de latência aproximada;
- contagem de heads e snapshots, somente leitura.

### 22.2 Caso sentinela

Reutilizar o Plano técnico já homologado na 6.5B:

```text
legacy_plano_id = 6a70538e-88a8-4691-b9fe-cf627b5f6cdc
```

Sem registrar nome do estudante no documento operacional.

Esperado no Shadow:

```text
v2_managed = true
effective_source = sidecar_active
legacy_status = rascunho
effective_lifecycle_status = active
effective_legacy_status = ativo
status_parity = false
integrity_error = null
```

### 22.3 Comportamento HTTP esperado

Mesmo com a divergência detectada:

- HTTP continua 200;
- JSON continua legado;
- o item continua apresentando `status=rascunho` na 6.6A;
- a UI continua **Em elaboração** nesta fase;
- nenhum `effective_*` aparece no body.

Isso é deliberado. A correção visual pertence à 6.6C.

### 22.4 Log esperado

Deve aparecer `AEE_V2_PLAN_LIST_SHADOW` em nível visível com, no mínimo:

- `phase=6.6A`;
- `mode=shadow_read_only`;
- `sidecar_active >= 1`;
- `status_compare.divergent >= 1`;
- transição `rascunho->ativo`;
- `integrity.errors=0` para o caso homologado;
- `head_queries <= 1`;
- `snapshot_queries <= 1`.

### 22.5 Auditor populacional

Executar o script read-only para o mesmo ano/escola e registrar:

- quantidade legacy-only;
- working-only;
- sidecar-active;
- transições de status;
- false positives/negatives por status;
- erros de integridade;
- divergências de dias;
- heterogeneidade de schedule.

## 23. Critérios de aceite da 6.6A

Todos devem ser satisfeitos:

1. Shadow instalado apenas em `GET /aee/planos`;
2. resposta HTTP legado permanece sem alteração de contrato;
3. nenhum campo novo chega ao frontend;
4. caso sentinela é resolvido como `sidecar_active`;
5. `rascunho -> ativo` é detectado sem alterar a UI;
6. zero fallback silencioso em erro de active snapshot;
7. lote misto legacy/working/active é resolvido corretamente;
8. no máximo 2 queries V2 por lote;
9. zero writes/create_index no caminho do Shadow;
10. observabilidade fica visível em produção;
11. auditor populacional consegue detectar falsos positivos e falsos negativos de `status_filter`;
12. nenhum erro de integridade V2-managed fica sem classificação;
13. falha inesperada do Shadow não derruba o legado;
14. FastAPI 0.110.1 preserva o wrapper após `include_router()`;
15. AEE v2 Contract Guard verde;
16. CI Build & Lint verde;
17. Gate Transferência verde;
18. sem regressão observada em Diário, PDFs e Dossiê V2;
19. relatório de homologação 6.6A é criado antes de autorizar 6.6B.

## 24. Condições que bloqueiam avanço para 6.6B

A 6.6B não deve iniciar se houver:

- erro de integridade não explicado em head/active snapshot;
- mismatch de identidade não resolvido;
- evidência de query N+1 V2;
- alteração acidental do JSON legado;
- aumento de 5xx/timeout relacionado ao wrapper;
- log técnico contendo PII indevida;
- diferença de filtro/população não classificada;
- regressão em RBAC professor;
- regressão em Diário/PDF/Dossiê;
- performance operacional persistentemente degradada sem causa definida.

Divergência legítima `rascunho legado -> ativo V2` **não bloqueia**; ela é precisamente a evidência que justifica a 6.6B/6.6C.

## 25. Rollback da 6.6A

Como a subfase é read-only, rollback não envolve banco.

### Rollback técnico

1. retirar o installer 6.6A do bootstrap;
2. redeployar commit anterior/commit de revert;
3. confirmar ausência de `AEE_V2_PLAN_LIST_SHADOW` em novas requisições;
4. confirmar `GET /aee/planos` no comportamento legado normal.

Os módulos podem permanecer no repositório sem instalação, caso seja útil manter testes/análise, mas o caminho runtime deve ficar desarmado.

### Gatilhos imediatos de rollback

- Shadow provoca 5xx no endpoint;
- quebra de autorização/escopo;
- mutação inesperada de resposta;
- qualquer write Mongo originado da 6.6A;
- crescimento de consultas proporcional a N;
- degradação operacional grave;
- volume de log inviável sem ajuste seguro.

## 26. Sequência de implementação futura

Quando houver autorização explícita para código:

1. criar branch exclusiva 6.6A;
2. implementar resolver batch puro e testes;
3. implementar comparação de status/dias;
4. implementar wrapper Shadow sem installer ativo inicialmente, se necessário para revisão intermediária;
5. implementar auditor populacional read-only;
6. cobrir não-mutação e query budget;
7. atualizar AEE v2 Contract Guard;
8. instalar 6.6A em `routers/__init__.py` somente na etapa final da PR;
9. conferir diff — nenhum `aee.py`, frontend ou write path;
10. executar gates;
11. merge somente após autorização explícita;
12. redeploy;
13. homologar caso sentinela + auditor populacional;
14. registrar documento de homologação;
15. somente então submeter proposta executiva da 6.6B.

## 27. Arquivos permitidos na futura PR 6.6A

Escopo esperado:

```text
backend/aee_v2/plan_list_effective.py
backend/aee_v2/plan_list_shadow.py
backend/scripts/audit_aee_v2_plan_list_6_6a.py
backend/tests/test_aee_v2_plan_list_shadow.py
backend/routers/__init__.py
.github/workflows/aee-v2-contract.yml
```

Um segundo arquivo de teste é aceitável se necessário para separar auditor/batch.

Qualquer mudança fora desse conjunto exige justificativa explícita na revisão.

Arquivos bloqueados que **não devem** ser alterados na 6.6A:

```text
backend/routers/aee.py
frontend/src/pages/DiarioAEE.js
frontend/src/components/PlanoAEEModal.js
backend/pdf/*AEE*
```

## 28. Definição de pronto do plano executivo

Este plano é considerado completo quando:

- o algoritmo batch está especificado;
- o limite de queries está definido;
- a lacuna de `status_filter` está coberta por auditor populacional, sem duplicar RBAC online;
- métricas e níveis de log estão definidos;
- testes têm critérios objetivos;
- homologação possui caso sentinela e resultados esperados;
- rollback é livre de restauração de banco;
- a futura PR possui fronteira de arquivos e sequência de execução claras.

## 29. Decisão

> **PLANO EXECUTIVO 6.6A DEFINIDO, SEM IMPLEMENTAÇÃO E SEM ALTERAÇÃO DE RUNTIME.**

A próxima ação, se aprovada, será somente autorizar a construção da PR de implementação da **6.6A — Listagem em Shadow Mode** conforme este contrato.