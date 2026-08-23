# AEE V2 — Fase 6.6C: Homologação em Produção do Cutover Controlado da Leitura/UX

**Data:** 2026-08-23  
**Status:** ✅ HOMOLOGADA EM PRODUÇÃO  
**PR de implementação:** #112 — `feat(aee): implementar cutover efetivo da leitura 6.6C`  
**Commit de merge:** `fc49626a348887edc30ff16f4a0e10ce1970af43`  
**Natureza:** cutover de leitura / sem governança de escrita / sem writes por GET  
**Superfícies:** `GET /api/aee/planos`, `GET /api/aee/planos/{plano_id}`, listagem Planos AEE, viewer read-only e PDF existente

## 1. Objetivo da homologação

Comprovar em produção que a Fase 6.6C substitui a semântica legado de leitura pela **Fonte Efetiva** já consolidada nas fases 6.4B, 6.5B e 6.6B, sem alterar a âncora histórica `planos_aee` e sem antecipar a governança de escrita da 6.6D.

A homologação deveria confirmar simultaneamente:

1. listagem sem filtro preservando o universo existente;
2. situação visual governada pela Fonte Efetiva;
3. `status_filter`, `total`, `skip` e `limit` obedecendo ao status efetivo;
4. viewer tradicional buscando o Plano individual por ID e renderizando `effective_dossier`;
5. PDF permanecendo coerente com a Fonte Efetiva;
6. zero fallback silencioso diante de erro de integridade;
7. teto de uma query de heads + uma de snapshots por resolução V2;
8. nenhuma escrita provocada pelas rotas de leitura.

---

## 2. Deployment validado

O merge do PR #112 acionou o deployment automático da produção.

Container backend observado durante a homologação:

```text
4a109d326ec4 bww8wogkcs0sws8sc80s4k4c-backend-1 Up ... (healthy)
```

O runtime confirmou somente o installer 6.6C:

```text
85:from aee_v2.plan_list_effective_cutover import install_aee_v2_plan_list_effective_cutover_setup
107:install_aee_v2_plan_list_effective_cutover_setup(_aee_mod)
```

A inspeção da rota FastAPI confirmou:

```text
endpoint_file = /app/aee_v2/plan_list_effective_cutover.py
endpoint_name = list_planos_aee
cutover_installed = True
contract_installed = False
shadow_installed = False
```

Portanto, não houve empilhamento dos wrappers 6.6A/6.6B com o cutover 6.6C.

Durante a importação manual do `server` fora do ciclo normal do Uvicorn apareceram os avisos conhecidos de scheduler sem event loop. Eles não representam falha do backend em produção.

---

## 3. Escopo real de homologação

Escola sentinela:

```text
school_id = 6e7aae6a-7b7b-42c7-a963-cac755b17ab4
academic_year = 2026
```

Caso sentinela:

```text
legacy_plano_id = 6a70538e-88a8-4691-b9fe-cf627b5f6cdc
```

O caso foi escolhido porque possui divergência intencional e controlada entre a âncora legado e a Fonte Efetiva:

```text
legacy.status = rascunho
effective_source = sidecar_active
effective lifecycle = active
```

Esse cenário é o teste principal da 6.6C: a leitura operacional deve mostrar **Vigente** sem reescrever `legacy.status`.

---

## 4. Listagem sem filtro

Após atualização da aba Planos AEE, a telemetria observada foi:

```text
AEE_V2_PLAN_LIST_EFFECTIVE
phase = 6.6C
mode = effective_read_cutover
```

Resumo:

```text
candidates.total               = 23
effective_total                = 23
items_returned                 = 23
v2_managed                     = 3
sidecar_active                 = 1
working_only                   = 2
legacy_effective               = 22
legacy_allowed                 = 20
dossier_v2_required            = 3
integrity.errors               = 0
integrity.working_errors       = 0
status divergent               = 1
status equal                   = 22
transition rascunho -> ativo   = 1
head_queries                   = 1
snapshot_queries               = 1
```

A população permaneceu em 23 Planos. Nenhum Plano foi perdido ou duplicado pelo cutover.

---

## 5. Cutover visual do caso sentinela

Antes da 6.6C, a UI tradicional exibia o caso sentinela como **Em elaboração**, pois lia diretamente `plano.status = rascunho`.

Após a 6.6C, a mesma linha passou a exibir:

```text
Vigente
```

Isso comprova que a situação visual passou a usar a semântica efetiva.

A mudança ocorreu sem alterar o valor legado persistido.

---

## 6. Filtro efetivo `ativo`

Foi executada requisição autenticada real contra o domínio da API:

```text
GET /api/aee/planos?school_id=6e7aae6a-7b7b-42c7-a963-cac755b17ab4&academic_year=2026&status_filter=ativo
```

Resultado HTTP:

```text
200 OK
```

Telemetria:

```text
candidates.total          = 23
requested_status          = ativo
legacy_matches_preview    = 0
effective_matches         = 1
total_delta               = +1
effective_total           = 1
items_returned            = 1
integrity.errors          = 0
head_queries              = 1
snapshot_queries          = 1
```

Esse resultado elimina o falso negativo existente na semântica legado: o caso sentinela é encontrado como `ativo` mesmo mantendo `legacy.status = rascunho`.

---

## 7. Filtro efetivo `rascunho`

Foi executada requisição autenticada real:

```text
GET /api/aee/planos?school_id=6e7aae6a-7b7b-42c7-a963-cac755b17ab4&academic_year=2026&status_filter=rascunho
```

Resultado HTTP:

```text
200 OK
```

Telemetria:

```text
candidates.total          = 23
requested_status          = rascunho
legacy_matches_preview    = 23
effective_matches         = 22
total_delta               = -1
effective_total           = 22
items_returned            = 22
integrity.errors          = 0
head_queries              = 1
snapshot_queries          = 1
```

Como a única divergência do universo é `rascunho -> ativo`, o caso sentinela deixa corretamente de pertencer ao conjunto efetivo `rascunho`.

Isso comprova que filtro, total e paginação passam a ser calculados depois da resolução da Fonte Efetiva.

---

## 8. Viewer individual efetivo

Ao clicar em **Visualizar** no caso sentinela, o frontend realizou:

```text
GET /api/aee/planos/6a70538e-88a8-4691-b9fe-cf627b5f6cdc
```

Resultado:

```text
200 OK
```

O cabeçalho do viewer exibiu:

```text
Snapshot V2 vigente
v2.r2
Vigente
```

A resposta HTTP individual confirmou:

```text
effective_source = sidecar_active
effective_version.document_version = 2
effective_version.revision = 2
effective_dossier = presente
effective_dossier.lifecycle.status = active
effective_error = null
```

Ao mesmo tempo, o mesmo payload preservou:

```text
status = rascunho
effective_dossier.provenance.legacy_status = rascunho
```

Portanto, o viewer não está apenas trocando um label: ele está lendo o Dossiê efetivo do snapshot ativo.

---

## 9. Coerência com o PDF

A geração/abertura do PDF do mesmo Plano foi validada após o cutover.

Situação exibida no documento:

```text
Vigente
```

Isso mantém a coerência entre:

```text
listagem = Vigente
viewer   = Vigente
PDF      = Vigente
```

sem alterar a âncora histórica legado.

---

## 10. Performance e hard gate V2

Nos três caminhos observados — sem filtro, `status_filter=ativo` e `status_filter=rascunho` — o teto permaneceu:

```text
head_queries     = 1
snapshot_queries = 1
```

Não houve N+1 de heads ou snapshots.

Tempos observados ficaram na ordem de dezenas de milissegundos ou menos para a resolução V2 no universo de 23 Planos, sem sinal de regressão operacional.

---

## 11. Integridade

Todos os testes online retornaram:

```text
integrity.errors         = 0
integrity.working_errors = 0
```

Não houve fallback silencioso para legado, snapshot ativo ausente, hash inválido, mismatch de identidade ou working snapshot corrompido no universo homologado.

---

## 12. Compatibilidade legado preservada

A 6.6C não executou migração, backfill ou alteração dos documentos em `planos_aee`.

O caso sentinela continuou materialmente comprovando:

```text
legacy.status = rascunho
Fonte Efetiva = sidecar_active / active
```

Esse é um requisito, não uma inconsistência: a coleção legado permanece como âncora histórica e identificador de compatibilidade, enquanto a Fonte Efetiva passa a governar a leitura operacional.

---

## 13. Escrita permanece fora da 6.6C

A homologação não altera ainda a autoridade dos fluxos mutáveis tradicionais.

Continuam fora da 6.6C:

```text
PUT  /api/aee/planos/{plano_id}
POST /api/aee/planos/{plano_id}/duplicate
```

Assim, a leitura já possui autoridade única efetiva, mas um Plano com head V2 ainda precisa de governança explícita para impedir que o editor legado volte a escrever silenciosamente na âncora histórica.

Esse é exatamente o problema reservado à 6.6D.

---

## 14. Critérios de homologação

| Critério | Resultado |
|---|---|
| PR #112 mergeado no commit esperado | ✅ |
| Backend healthy | ✅ |
| Installer 6.6C ativo | ✅ |
| 6.6A/6.6B não empilhados | ✅ |
| Rota FastAPI aponta para `plan_list_effective_cutover.py` | ✅ |
| Listagem sem filtro responde 200 | ✅ |
| Universo preservado em 23 Planos | ✅ |
| 3 Planos V2 managed | ✅ |
| 1 `sidecar_active` | ✅ |
| 2 `working_only` | ✅ |
| 20 `legacy_allowed` | ✅ |
| Zero erros de integridade | ✅ |
| Caso sentinela aparece Vigente na lista | ✅ |
| `status_filter=ativo` retorna total efetivo 1 | ✅ |
| `status_filter=rascunho` retorna total efetivo 22 | ✅ |
| Filtro efetivo ocorre antes da paginação | ✅ |
| Heads queries <= 1 | ✅ |
| Snapshot queries <= 1 | ✅ |
| Viewer executa GET individual | ✅ |
| Viewer usa `effective_dossier` | ✅ |
| Viewer mostra `sidecar_active`, v2.r2 e Vigente | ✅ |
| `legacy.status=rascunho` permanece preservado | ✅ |
| PDF mostra Vigente | ✅ |
| Nenhuma governança de escrita foi antecipada | ✅ |

---

## 15. Decisão

> **Fase 6.6C HOMOLOGADA EM PRODUÇÃO em 23/08/2026.**

A Fonte Efetiva agora governa de forma coerente a listagem, a situação visual, os filtros, o total, a paginação, a visualização individual e o PDF do Plano AEE.

A evidência é suficiente para avançar ao planejamento executivo da:

> **Fase 6.6D — Governança de Escrita do Plano AEE.**

A homologação da 6.6C **não autoriza automaticamente a implementação da 6.6D**. A próxima subfase exige plano executivo próprio, PR de implementação separado, gates, autorização explícita e nova homologação em produção.
