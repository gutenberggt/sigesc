# AEE V2 — Fase 6.6A: Homologação em Produção da Listagem em Shadow Mode

**Data:** 2026-08-23  
**Status:** ✅ HOMOLOGADA EM PRODUÇÃO  
**PR de implementação:** #108 — `feat(aee): implementar Listagem em Shadow Mode 6.6A`  
**Commit de merge:** `80cbd542563a6ec8b1a526821ceffbe5ce82ec4c`  
**Natureza:** read-only / observacional / fail-open para a resposta legado  
**Superfície:** `GET /api/aee/planos`

## 1. Objetivo da homologação

Comprovar em produção que a Fase 6.6A observa a listagem legado de Planos AEE, resolve a Fonte Efetiva V2 em lote, mede divergências e integridade e registra telemetria sem alterar a resposta HTTP, a UI, filtros, total, paginação ou dados persistidos.

A homologação foi executada após merge do PR #108 e redeploy automático pelo Coolify.

## 2. Estado do deployment

O deployment automático concluiu com o backend em estado `healthy`.

Container backend observado durante a homologação:

```text
43ba07b0b837 bww8wogkcs0sws8sc80s4k4c-backend-1 Up ... (healthy)
```

O runtime confirmou a instalação da 6.6A em `backend/routers/__init__.py`:

```text
82:from aee_v2.plan_list_shadow import install_aee_v2_plan_list_shadow_setup
104:install_aee_v2_plan_list_shadow_setup(_aee_mod)
```

A rota FastAPI efetivamente registrada também foi inspecionada:

```text
endpoint = /app/aee_v2/plan_list_shadow.py
wrapped = True
shadow_installed = True
```

A cadeia de closures confirmou que tanto o wrapper quanto o endpoint legado usam o mesmo objeto `server.db`:

```text
level=0 file=/app/aee_v2/plan_list_shadow.py db_name=sigesc db_same_as_server=True
level=1 file=/app/routers/aee.py db_name=sigesc db_same_as_server=True
```

## 3. Caso sentinela de produção

A homologação funcional foi realizada na escola Dr. Almir Gabriel, ano letivo 2026, utilizando o universo real de Planos AEE já existente.

A requisição observada foi:

```text
GET /api/aee/planos?school_id=6e7aae6a-7b7b-42c7-a963-cac755b17ab4&academic_year=2026 HTTP/1.1 200 OK
```

O evento estruturado produzido pela 6.6A registrou:

```json
{
  "phase": "6.6A",
  "mode": "shadow_read_only",
  "status": "divergent",
  "page": {
    "items_returned": 23,
    "legacy_total": 23,
    "limit": 100,
    "skip": 0
  },
  "sources": {
    "legacy_effective": 22,
    "sidecar_active": 1,
    "v2_managed": 3,
    "working_only": 2
  },
  "status_compare": {
    "compared": 23,
    "equal": 22,
    "divergent": 1,
    "transitions": {
      "rascunho->ativo": 1
    }
  },
  "schedule_compare": {
    "days_compared": 23,
    "days_equal": 23,
    "days_divergent": 0,
    "heterogeneous_v2": 0
  },
  "integrity": {
    "errors": 0,
    "working_errors": 0,
    "by_code": {}
  },
  "performance": {
    "head_queries": 1,
    "snapshot_queries": 1,
    "batch_ms": 27.953,
    "shadow_ms": 37.539
  }
}
```

## 4. Resultado funcional

A evidência confirma o GAP que motivou a Fase 6.6:

- a listagem legado considera os 23 Planos como `rascunho`;
- a Fonte Efetiva considera 22 como `rascunho` e 1 como `ativo`;
- existe exatamente uma transição real `rascunho -> ativo`;
- esse Plano é o caso sentinela `sidecar_active` já usado nas fases anteriores;
- dois Planos possuem cadeia V2 em trabalho, mas sem snapshot ativo, portanto continuam com Fonte Efetiva `legacy`;
- não houve qualquer erro de integridade.

A divergência observada é funcional e esperada. Não representa corrupção ou falha da 6.6A.

## 5. Invariante de compatibilidade HTTP

O endpoint legado permaneceu respondendo `200 OK`.

A 6.6A não alterou:

- os campos dos itens retornados;
- `status` legado;
- `dias_atendimento` legado;
- `total`;
- `skip`;
- `limit`;
- ordenação;
- frontend;
- botões ou fluxo de edição;
- filtros aplicados pelo endpoint legado.

A UI permaneceu consumindo o contrato legado, conforme planejado.

## 6. Performance e proibição de N+1

O hard gate de performance foi atendido em produção:

```text
head_queries = 1
snapshot_queries = 1
```

Portanto, o resolver V2 usou no máximo dois round-trips Mongo independentemente dos 23 Planos retornados.

O tempo observado no request real foi:

```text
batch_ms = 27.953
shadow_ms = 37.539
```

O tempo permaneceu abaixo do guardrail operacional de 100 ms definido para o batch.

## 7. Auditor populacional read-only

Além do Shadow online, foi executado o auditor populacional da 6.6A sobre a mesma escola e ano.

Comando operacional validado no container atual:

```bash
cd /app && PYTHONPATH=/app python scripts/audit_aee_v2_plan_list_6_6a.py \
  --academic-year 2026 \
  --school-id 6e7aae6a-7b7b-42c7-a963-cac755b17ab4 \
  --max-plans 2000 \
  --page-size 100
```

Resultado consolidado:

```text
plans_total = 23

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
schedule.days_equal = 23
schedule.days_divergent = 0

performance:
  head_queries = 1
  snapshot_queries = 1
  batch_ms = 3.358
```

## 8. Evidência para filtros efetivos futuros

O auditor populacional demonstrou concretamente o impacto que deverá ser tratado na Fase 6.6C.

Para `status_filter=ativo`:

```text
legacy_total = 0
effective_total = 1
false_negative_count = 1
total_delta = +1
```

Para `status_filter=rascunho`:

```text
legacy_total = 23
effective_total = 22
false_positive_count = 1
total_delta = -1
```

Isso comprova que o cutover de filtro, total e paginação não pode ser feito apenas alterando a apresentação visual. A semântica efetiva deverá ser aplicada antes da paginação na Fase 6.6C.

## 9. Observação operacional do auditor

A primeira execução direta do script sem ajuste de `PYTHONPATH` falhou com:

```text
ModuleNotFoundError: No module named 'aee_v2'
```

No layout atual do container, a execução manual deve incluir:

```text
PYTHONPATH=/app
```

Essa limitação não afeta o runtime HTTP nem a homologação funcional da 6.6A. Deve ser documentada ou eliminada em manutenção operacional futura, sem ampliar o escopo das fases de cutover.

## 10. Critérios de homologação

| Critério | Resultado |
|---|---|
| Deployment do commit correto | ✅ |
| Backend healthy | ✅ |
| Installer 6.6A carregado | ✅ |
| Rota FastAPI apontando para o wrapper | ✅ |
| `GET /api/aee/planos` 200 | ✅ |
| Resposta legado preservada | ✅ |
| Caso `sidecar_active` detectado | ✅ |
| `rascunho -> ativo` detectado | ✅ |
| Working-only tratado como Fonte Efetiva legado | ✅ |
| Erros de integridade = 0 | ✅ |
| Dias divergentes = 0 | ✅ |
| Head queries <= 1 | ✅ |
| Snapshot queries <= 1 | ✅ |
| Auditor populacional executado | ✅ |
| Falso positivo/negativo de status medido | ✅ |
| Nenhum write/migração | ✅ |

## 11. Decisão

> **Fase 6.6A HOMOLOGADA EM PRODUÇÃO em 23/08/2026.**

A evidência é suficiente para autorizar o planejamento da Fase 6.6B — Contrato Aditivo da Listagem.

A homologação da 6.6A não autoriza automaticamente a implementação da 6.6B. A próxima subfase continua sujeita a plano executivo, PR próprio, gates e autorização explícita separada.
