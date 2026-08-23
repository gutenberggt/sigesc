# AEE V2 — Fase 6.6B: Homologação em Produção do Contrato Aditivo da Listagem

**Data:** 2026-08-23  
**Status:** ✅ HOMOLOGADA EM PRODUÇÃO  
**PR de implementação:** #110 — `feat(aee): implementar contrato aditivo da listagem 6.6B`  
**Commit de merge:** `3b3be4fe32379ad236bdf107620e8d9221221fd9`  
**Natureza:** read-only / contrato HTTP aditivo / sem cutover visual  
**Superfície:** `GET /api/aee/planos`

## 1. Objetivo da homologação

Comprovar em produção que a Fase 6.6B substitui operacionalmente o Shadow Mode 6.6A na listagem de Planos AEE, reutiliza uma única resolução batch da Fonte Efetiva, preserva integralmente os campos legado e acrescenta os seis campos públicos aprovados:

```text
v2_managed
effective_source
effective_version
effective_summary
effective_error
mutation_policy
```

A homologação também verifica que a 6.6B **não** ativa ainda o cutover visual, não altera `status_filter`, `total`, `skip`, `limit`, ordenação, fluxo de edição ou duplicação, não faz writes e não empilha o wrapper 6.6A.

---

## 2. Deployment validado

O merge do PR #110 acionou o deployment automático da produção.

Container backend observado durante a homologação:

```text
38887362919e bww8wogkcs0sws8sc80s4k4c-backend-1 Up ... (healthy)
```

O arquivo de instalação carregado no container confirmou somente a 6.6B:

```text
84:from aee_v2.plan_list_contract import install_aee_v2_plan_list_contract_setup
106:install_aee_v2_plan_list_contract_setup(_aee_mod)
```

Não havia instalação ativa de `plan_list_shadow`.

---

## 3. Rota FastAPI efetivamente registrada

A rota foi inspecionada no runtime do container.

Resultado:

```text
endpoint_file = /app/aee_v2/plan_list_contract.py
endpoint_name = list_planos_aee
contract_installed = True
shadow_installed = False
```

Portanto:

- o endpoint efetivo da listagem está envolvido pela 6.6B;
- o installer do contrato está ativo;
- o Shadow 6.6A não está empilhado;
- a resolução V2 não é duplicada por dois wrappers.

Durante a inspeção manual por `import server`, apareceram os avisos:

```text
Falha ao iniciar scheduler PMPI: no running event loop
[interventions] Scheduler não pôde iniciar: no running event loop
```

Esses avisos decorrem da importação manual do módulo fora do ciclo normal do Uvicorn e não representam falha do backend em produção.

---

## 4. Escopo real da homologação

Escola sentinela:

```text
E M E I E F DR ALMIR JOSE DE OLIVEIRA GABRIEL
school_id = 6e7aae6a-7b7b-42c7-a963-cac755b17ab4
academic_year = 2026
```

Requisição observada:

```text
GET /api/aee/planos?school_id=6e7aae6a-7b7b-42c7-a963-cac755b17ab4&academic_year=2026 HTTP/1.1 200 OK
```

A UI carregou normalmente a listagem após o deployment.

---

## 5. Telemetria online da 6.6B

Evento observado:

```text
AEE_V2_PLAN_LIST_ADDITIVE
```

Payload consolidado:

```json
{
  "filter_preview": {
    "population_audit_required": false,
    "returned_effective_mismatch": 0
  },
  "integrity": {
    "by_code": {},
    "errors": 0,
    "working_errors": 0
  },
  "mode": "additive_contract",
  "mutation_policies": {
    "dossier_v2_required": 3,
    "legacy_allowed": 20
  },
  "page": {
    "items_returned": 23,
    "legacy_total": 23,
    "limit": 100,
    "skip": 0
  },
  "performance": {
    "batch_ms": 10.719,
    "contract_ms": 20.229,
    "head_queries": 1,
    "snapshot_queries": 1
  },
  "phase": "6.6B",
  "schedule_compare": {
    "days_compared": 23,
    "days_divergent": 0,
    "days_equal": 23,
    "heterogeneous_v2": 0
  },
  "scope": {
    "academic_year": 2026,
    "professor_filter": false,
    "role": "super_admin",
    "school_filter": true,
    "status_filter": null,
    "student_filter": false
  },
  "sources": {
    "legacy_effective": 22,
    "sidecar_active": 1,
    "v2_managed": 3,
    "working_only": 2
  },
  "status": "divergent",
  "status_compare": {
    "compared": 23,
    "divergent": 1,
    "equal": 22,
    "transitions": {
      "rascunho->ativo": 1
    }
  }
}
```

---

## 6. Resultado populacional online

A listagem retornou:

```text
Planos totais                   = 23
V2 managed                      = 3
sidecar_active                  = 1
working_only                    = 2
Fonte Efetiva legado            = 22
legacy_allowed                  = 20
dossier_v2_required             = 3
integrity errors                = 0
working integrity errors        = 0
dias iguais                     = 23
dias divergentes                = 0
transição rascunho -> ativo     = 1
```

A distribuição é coerente com a 6.6A previamente homologada e com o contrato planejado da 6.6B.

---

## 7. Caso sentinela `sidecar_active`

Plano legado sentinela:

```text
legacy_plano_id = 6a70538e-88a8-4691-b9fe-cf627b5f6cdc
```

O payload HTTP preservou o valor legado:

```json
{
  "status": "rascunho"
}
```

E acrescentou simultaneamente:

```json
{
  "v2_managed": true,
  "effective_source": "sidecar_active",
  "effective_version": {
    "active_snapshot_id": "45ad4d04-4c8d-4568-96bb-44f6c00920de",
    "document_version": 2,
    "revision": 2,
    "working_snapshot_id": "7106f7e2-9b8c-4c5c-bbdc-7844b7100120"
  },
  "effective_summary": {
    "lifecycle_status": "active",
    "legacy_compatible_status": "ativo",
    "schedule_summary": {
      "days": ["terca"],
      "shape": "homogeneous"
    }
  },
  "effective_error": null,
  "mutation_policy": "dossier_v2_required"
}
```

Esse é o principal critério funcional da fase:

> o contrato torna explícito que o valor histórico legado é `rascunho`, enquanto a Fonte Efetiva vigente é `sidecar_active` com situação efetiva `ativo`, sem sobrescrever silenciosamente o campo legado.

---

## 8. Caso `working_only`

Foi comprovado em produção que um Plano com head V2 e snapshot de trabalho, mas sem snapshot ativo, mantém a Fonte Efetiva oficial legado.

Exemplo observado:

```json
{
  "v2_managed": true,
  "effective_source": "legacy",
  "effective_version": {
    "active_snapshot_id": null,
    "document_version": null,
    "revision": null,
    "working_snapshot_id": "db97150d-a428-425d-a00b-00fb10ee06c6"
  },
  "effective_summary": {
    "lifecycle_status": "draft",
    "legacy_compatible_status": "rascunho",
    "schedule_summary": {
      "days": ["terca"],
      "shape": "legacy_projection"
    }
  },
  "effective_error": null,
  "mutation_policy": "dossier_v2_required"
}
```

Esse comportamento confirma a distinção arquitetural entre:

- **autoridade de leitura:** ainda legado enquanto não existe active íntegro;
- **governança de edição:** já pertence ao Dossiê V2 porque o head existe.

Dois casos `working_only` foram observados no universo de 23 Planos.

---

## 9. Caso puramente legado

Um Plano sem head V2 permanece integralmente sob a governança anterior:

```json
{
  "v2_managed": false,
  "effective_source": "legacy",
  "effective_version": {
    "active_snapshot_id": null,
    "document_version": null,
    "revision": null,
    "working_snapshot_id": null
  },
  "effective_summary": {
    "lifecycle_status": "draft",
    "legacy_compatible_status": "rascunho",
    "schedule_summary": {
      "days": ["sexta"],
      "shape": "legacy_projection"
    }
  },
  "effective_error": null,
  "mutation_policy": "legacy_allowed"
}
```

Foram observados 20 Planos nessa condição.

---

## 10. Contrato aditivo comprovado no HTTP

A resposta real do navegador confirmou que os seis campos 6.6B estão materializados no JSON entregue ao cliente.

A homologação não se baseou apenas em logs internos.

Foram validados no HTTP:

- `v2_managed`;
- `effective_source`;
- `effective_version`;
- `effective_summary`;
- `effective_error`;
- `mutation_policy`.

O envelope permaneceu:

```json
{
  "items": [...],
  "total": 23
}
```

---

## 11. Preservação visual deliberada

A UI tradicional continuou exibindo o caso sentinela como:

```text
Em elaboração
```

Isso é **correto na 6.6B**.

O Plano legado foi deliberadamente mantido com:

```text
status = rascunho
```

E o frontend desta subfase ainda usa `plano.status` legado para renderizar a situação.

Portanto, o fato de a tela mostrar `Em elaboração` enquanto o contrato expõe `effective_summary.legacy_compatible_status = ativo` comprova a separação planejada entre:

- 6.6B — contrato efetivo disponível;
- 6.6C — futuro cutover controlado de leitura/UX.

Não houve cutover visual acidental.

---

## 12. Performance e hard gate de consultas V2

O hard gate permaneceu atendido:

```text
head_queries = 1
snapshot_queries = 1
```

Logo, os 23 Planos não provocaram N+1 de heads/snapshots.

Tempos observados:

```text
batch_ms    = 10.719
contract_ms = 20.229
```

Os valores permanecem confortavelmente abaixo do guardrail operacional adotado nas fases anteriores.

---

## 13. Integridade

Resultado:

```text
integrity.errors         = 0
integrity.working_errors = 0
```

Não houve:

- snapshot ativo ausente;
- hash inválido;
- contrato persistido inválido;
- mismatch de identidade;
- lifecycle sem mapeamento;
- working corrompido;
- fallback silencioso para legado.

---

## 14. Agenda

Resultado:

```text
days_compared    = 23
days_equal       = 23
days_divergent   = 0
heterogeneous_v2 = 0
```

O caso `sidecar_active` retornou agenda efetiva com:

```json
{
  "days": ["terca"],
  "shape": "homogeneous"
}
```

Nenhuma informação heterogênea precisou ser achatada durante esta homologação.

---

## 15. Semântica de `mutation_policy`

A distribuição real foi:

```text
legacy_allowed       = 20
dossier_v2_required  = 3
blocked_integrity    = 0
```

A política é **informativa** nesta fase.

A 6.6B não bloqueia ainda:

- `PUT /aee/planos/{plano_id}`;
- `POST /aee/planos/{plano_id}/duplicate`.

O enforcement continua reservado à Fase 6.6D.

---

## 16. Critérios de homologação

| Critério | Resultado |
|---|---|
| Merge do PR #110 no commit esperado | ✅ |
| Backend em estado healthy | ✅ |
| Installer 6.6B carregado | ✅ |
| Wrapper 6.6A não empilhado | ✅ |
| Rota FastAPI aponta para `plan_list_contract.py` | ✅ |
| `GET /api/aee/planos` responde 200 | ✅ |
| Contrato aditivo presente no HTTP real | ✅ |
| Envelope `items` + `total` preservado | ✅ |
| 23 Planos retornados | ✅ |
| 1 `sidecar_active` | ✅ |
| 2 `working_only` | ✅ |
| 20 Planos puramente legado | ✅ |
| 3 `dossier_v2_required` | ✅ |
| 20 `legacy_allowed` | ✅ |
| 1 transição `rascunho -> ativo` | ✅ |
| Integridade = 0 erros | ✅ |
| Agenda = 23/23 em paridade | ✅ |
| Heads queries <= 1 | ✅ |
| Snapshot queries <= 1 | ✅ |
| UI ainda usa situação legado | ✅ |
| Nenhum cutover de filtro/paginação | ✅ |
| Nenhuma mutação provocada pelo GET | ✅ |

---

## 17. Decisão

> **Fase 6.6B HOMOLOGADA EM PRODUÇÃO em 23/08/2026.**

A listagem agora possui um contrato HTTP explícito e estável da Fonte Efetiva, sem remover a compatibilidade legado e sem antecipar o cutover visual.

A evidência é suficiente para avançar ao planejamento executivo da:

> **Fase 6.6C — Cutover Controlado da Leitura/UX.**

A homologação da 6.6B não autoriza automaticamente a implementação da 6.6C. A próxima subfase continua sujeita a plano executivo, PR próprio de implementação, gates, autorização explícita e homologação em produção.
