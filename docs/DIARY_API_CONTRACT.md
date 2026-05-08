# Contrato Arquitetural — Diário com Dependência

> **Status**: 🔒 Congelado em Fev/2026 — `contract_version: 1`.
> **Antes de qualquer mudança neste contrato**: bumpar versão, manter compatibilidade ou criar V2 paralelo.
> **Pré-requisito**: Fase 1 da Dependência de Estudos validada (ver `STUDENT_DEPENDENCY.md`).

---

## Objetivo

Definir um contrato estável entre backend e frontend para o Diário, suportando coexistência de:

- alunos regulares (via `enrollments`);
- alunos em dependência (via `student_dependencies`);
- frequência, notas, fechamento;
- observabilidade;
- escalabilidade futura.

> ⚠️ **Princípio fundamental**: o frontend **NÃO** infere regras pedagógicas. Toda regra vem pronta do backend.

---

## 1. Estratégia obrigatória de retorno

### ❌ NÃO retornar listas separadas

```json
{
  "regular": [...],
  "dependency": [...]
}
```

Isso força **bifurcação de renderização no React** e aumenta risco de hooks condicionais, ordenação inconsistente, bugs de fechamento e duplicidade visual.

### ✅ Retornar lista **unificada** com flag `is_dependency`

```json
{
  "contract_version": 1,
  "items": [
    {
      "student_id": "stu_1",
      "student_name": "Ana Silva",
      "is_dependency": false
    },
    {
      "student_id": "stu_2",
      "student_name": "Carlos Souza",
      "is_dependency": true,
      "dependency_id": "dep_9"
    }
  ]
}
```

Backend entrega a lista **já pronta** para renderização.

---

## 2. Ordem visual obrigatória (responsabilidade do backend)

O backend ordena:

1. **Alunos regulares** (sort alfabético por `student_name`).
2. **Alunos em dependência** (sort alfabético por `student_name`).

> Nunca deixar essa decisão para o frontend. O frontend pode reordenar **localmente apenas para UI** (ex.: clique no header da coluna), mas o **default** vem ordenado.

---

## 3. Shape mínimo obrigatório

Cada item do diário **deve** conter:

```json
{
  "student_id": "string",
  "student_name": "string",
  "student_code": "string|null",

  "is_dependency": true,
  "dependency_id": "string|null",
  "dependency_type": "with_dependency|dependency_only|null",

  "class_id": "string",
  "course_id": "string",

  "attendance_enabled": true,
  "grades_enabled": true,

  "status": "active|completed|failed|cancelled",

  "origin_academic_year": 2025,

  "display_label": "Dependência"
}
```

| Campo | Obrigatório? | Uso |
|---|---|---|
| `student_id` | ✅ | Chave primária no UI |
| `student_name` | ✅ | Nome exibido + ordenação |
| `student_code` | opcional | Matrícula/código se houver |
| `is_dependency` | ✅ | Flag para renderização condicional do badge |
| `dependency_id` | ✅ se `is_dependency=true` | FK para `student_dependencies` (lançar frequência/notas) |
| `dependency_type` | ✅ se `is_dependency=true` | Diferencia `with_dependency` vs `dependency_only` |
| `attendance_enabled` | ✅ | Se professor pode lançar frequência (false em dep concluída) |
| `grades_enabled` | ✅ | Se professor pode lançar notas |
| `status` | ✅ se `is_dependency=true` | Espelha `student_dependencies.status` |
| `origin_academic_year` | ✅ se `is_dependency=true` | Para histórico/auditoria |
| `display_label` | ✅ | Texto do badge — sempre `"Dependência"` (sem variantes) |

---

## 4. Regra crítica — fonte da verdade

### ❌ O diário NUNCA usa

```python
student.dependency_mode
```

para carregar alunos.

### ✅ O diário SEMPRE usa

```python
student_dependencies.find({
    "mantenedora_id": tenant,
    "class_id": class_id,
    "course_id": course_id,
    "status": "active",
})
```

> `dependency_mode` é **estado administrativo** (intenção do secretário). `student_dependencies` é o **vínculo pedagógico real**. Misturar gera inconsistência invisível.

---

## 5. Frequência e notas — separação lógica obrigatória

Mesmo aparecendo na mesma tela do diário, registros de dependência **precisam carregar** `dependency_id` em:

- frequência (`attendance` collection);
- notas (`grades` collection);
- recuperação;
- fechamento.

Isso permite, futuramente, separar boletim regular vs boletim de dependência **sem reescrever queries**.

```json
// Exemplo de POST /api/attendance/lançar
{
  "student_id": "stu_2",
  "dependency_id": "dep_9",  // null se aluno regular
  "class_id": "cl_1",
  "course_id": "co_1",
  "date": "2026-03-15",
  "present": true
}
```

---

## 6. Anti-duplicidade — garantida pelo backend

Um aluno:

- ❌ **NÃO** pode aparecer duas vezes no mesmo componente da mesma turma;
- ❌ **NÃO** pode aparecer como regular **E** dependência simultaneamente no mesmo componente;
- ❌ **NÃO** pode ter dois vínculos ativos para mesmo componente/ano de origem (já garantido pelo índice único parcial em `student_dependencies`).

> O backend deve fazer essa deduplicação **antes** de devolver `items`.

---

## 7. Badge visual padronizada

```jsx
<Badge variant="amber-soft">Dependência</Badge>
```

**Constante única**: `DEPENDENCY_DISPLAY_LABEL = "Dependência"` em `/app/backend/utils/diary_constants.py`.

**Proibido** (validado em `validate_dependency_label`):
- ❌ `"DP"`, `"Dep."`, `"Depend."`, `"Dependente"`, `"Aluno dependência"`, `"(Dep.)"`, `"Em DP"`.
- ❌ Vermelho agressivo
- ❌ Ícone de alerta/erro

> Dependência é **condição pedagógica**, não erro. Inconsistência de nomenclatura entre diário/boletim/PDF/ficha quebra confiança. **Toda referência usa a constante**, nunca string literal.

---

## 8. Performance — SLA obrigatório

| Métrica | SLA |
|---|---|
| `p95_latency_ms` | < 200ms |
| `p99_latency_ms` | < 500ms |
| Payload típico | < 50kB |
| Sem agregações pesadas | obrigatório |

### Índice obrigatório utilizado

```python
db.student_dependencies.create_index(
    [("mantenedora_id", 1), ("class_id", 1), ("course_id", 1), ("status", 1)],
    name="ix_dep_tenant_class_course_status",
    background=True,
)
```

> Validar com `db.student_dependencies.find({...}).explain("executionStats")` que `winningPlan` usa este índice (`stage: IXSCAN` com `indexName: "ix_dep_tenant_class_course_status"`). Documentar o `explain()` esperado em PR.

---

## 9. Observabilidade — instrumentação obrigatória

Toda carga do diário **deve** registrar via canal `diary_metrics`:

```python
from utils.observability import record_diary_load

record_diary_load(
    duration_ms=duration_ms,
    tenant_id=current_user["mantenedora_id"],
    regular_count=len(regulars),
    dependency_count=len(deps),
    cache_hit=False,
    is_error=False,
    class_id=class_id,
    course_id=course_id,
)
```

Snapshot disponível em `GET /api/admin/observability/diary` (super_admin only).

### Métricas-alvo

- `requests_total` — volume de carregamentos.
- `avg_latency_ms`, `p95_latency_ms`, `p99_latency_ms` — performance.
- `counters.regular_total` / `counters.dependency_total` — proporção pedagógica.
- `cache_hit_pct` — eficiência de cache (quando implementado).
- `top_tenants` — quem mais usa o diário.

---

## 10. Compatibilidade futura

O contrato V1 deve **preservar** o shape para atender futuras necessidades, sem quebrar:

- boletim regular + boletim de dependência (Fase 3);
- ficha individual (Fase 3);
- histórico escolar (Fase 4);
- recuperação;
- conselho de classe;
- dependência concluída/cancelada;
- equivalência curricular.

Campos novos podem ser **adicionados** ao item (extensão segura). Campos existentes **não podem** mudar nome ou tipo sem bumpar `contract_version`.

---

## 11. Versionamento do contrato

```json
{
  "contract_version": 1
}
```

- Mudança **não-breaking** (novo campo opcional): mantém v1.
- Mudança **breaking** (renomear/remover campo, mudar tipo): cria v2 paralelo (header `Accept: application/vnd.sigesc.diary.v2+json` ou query `?v=2`).

> Frontend lê `contract_version` no payload e dispara erro audível ao receber versão não suportada.

---

## 12. Divisão de responsabilidades

### Frontend
- ✅ Renderiza items.
- ✅ Filtra visualmente (busca local na lista carregada).
- ✅ Ordena localmente quando usuário clica na coluna.
- ❌ **NÃO** calcula dependência.
- ❌ **NÃO** decide elegibilidade pedagógica.
- ❌ **NÃO** monta vínculo.
- ❌ **NÃO** infere status.

### Backend
- ✅ Toda lógica pedagógica.
- ✅ Tenant scope.
- ✅ Anti-duplicidade.
- ✅ Ordenação default.
- ✅ Telemetria.
- ✅ Auditoria.

---

## 13. Cenários obrigatórios de teste E2E

O contrato só é considerado **estável** após validar todos:

| # | Cenário | Esperado |
|---|---|---|
| 1 | Aluno regular puro | aparece com `is_dependency=false` |
| 2 | Aluno apenas dependência (`dependency_only`) | só aparece nos componentes vinculados |
| 3 | Aluno `with_dependency` | aparece em regulares + dependência |
| 4 | Turma sem dependências | `items` só com regulares |
| 5 | Múltiplas dependências do mesmo aluno | cada uma em seu componente |
| 6 | Dep cancelada | NÃO aparece no diário |
| 7 | Dep concluída | NÃO aparece OU aparece com `attendance_enabled=false` (decidir Fase 4) |
| 8 | Exclusão de turma com dep ativa | bloqueada (HTTP 409 — já implementado Fase 1) |
| 9 | Exclusão de componente com dep ativa | bloqueada (HTTP 409 — já implementado Fase 1) |
| 10 | Fechamento da turma regular | NÃO afeta deps ativas |
| 11 | Boletim — Fase 3 | seção "Dependência" separada |
| 12 | PDF — Fase 3 | página exclusiva |
| 13 | Ficha individual — Fase 3 | seção dedicada |
| 14 | Auditoria | toda mudança registra `before/after`, IP, user, timestamp |

---

## 14. Risco arquitetural principal

> O maior risco da Fase 2 **NÃO é visual**.
> É **mistura estrutural** entre:
>
> ```text
> enrollment   vs   student_dependency
> ```

Se fundir cedo demais:
- O diário vira entidade híbrida.
- O histórico escolar quebra.
- O fechamento anual fica inconsistente.
- Surgem duplicidades impossíveis de auditar.

> **Regra de ouro**: separação lógica permanece **rígida internamente**, mesmo que a UI mostre tudo como uma única lista.

---

## 15. Endpoint canônico (Fase 2)

```http
GET /api/diary/class/{class_id}/course/{course_id}?academic_year=2026
Authorization: Bearer <token>
```

### Response 200

```json
{
  "contract_version": 1,
  "class_id": "cl_1",
  "course_id": "co_1",
  "academic_year": 2026,
  "items": [
    {
      "student_id": "stu_1",
      "student_name": "Ana Silva",
      "student_code": "2026001",
      "is_dependency": false,
      "dependency_id": null,
      "dependency_type": null,
      "class_id": "cl_1",
      "course_id": "co_1",
      "attendance_enabled": true,
      "grades_enabled": true,
      "status": "active",
      "origin_academic_year": null,
      "display_label": ""
    },
    {
      "student_id": "stu_2",
      "student_name": "Carlos Souza",
      "student_code": "2025013",
      "is_dependency": true,
      "dependency_id": "dep_9",
      "dependency_type": "with_dependency",
      "class_id": "cl_1",
      "course_id": "co_1",
      "attendance_enabled": true,
      "grades_enabled": true,
      "status": "active",
      "origin_academic_year": 2025,
      "display_label": "Dependência"
    }
  ],
  "summary": {
    "regular_count": 1,
    "dependency_count": 1,
    "total": 2
  }
}
```

### Códigos de erro

| Code | Quando |
|---|---|
| 401 | Sem token |
| 403 | Role não pode acessar diário desta turma/componente |
| 404 | Turma ou componente não encontrado |
| 409 | (Reservado para futuras validações de integridade) |
| 500 | Erro interno (logado no canal `diary` com `is_error=True`) |

---

## 16. Helper de instrumentação (já implementado)

```python
# /app/backend/utils/observability.py
def record_diary_load(*, duration_ms, tenant_id, regular_count, dependency_count,
                     cache_hit=False, is_error=False, is_rate_limited=False,
                     class_id=None, course_id=None):
    ...
```

Use sempre este helper. Não chame `diary_metrics.record` diretamente — o helper garante a estrutura padronizada.

---

**Mantido por**: Equipe SIGESC
**Última atualização**: Fev/2026
**Próximo bump**: somente quando houver breaking change (`contract_version: 2`).

---

## 17. Ordenação rígida — divisor decidido pelo FRONTEND a partir de `meta`

**Atualização Fev/2026 (exigência operacional do owner):** o divisor visual NÃO faz parte
do array `items`. Misturar item fake `is_divider` com alunos reais gera bugs de
`map`/`filter`/exportação/render condicional/cálculos de presença. O backend devolve
metadados em `meta` e o frontend decide onde renderizar o separador.

Backend retorna `items` na ordem **exata**:

1. **Regulares** (sort `localeCompare('pt-BR')` por `student_name`).
2. **Dependências** (sort `localeCompare('pt-BR')` por `student_name`).

E em `meta`:

```json
{
  "regular_count": 28,
  "dependency_count": 3,
  "has_dependencies": true,
  "dependency_ratio_pct": 9.68,
  "total": 31,
  "load_duration_ms": 12.4
}
```

Frontend renderiza o separador imediatamente antes do primeiro item com
`is_dependency: true` quando `meta.has_dependencies === true`:

```jsx
{items.map((item, idx) => {
  const prev = items[idx - 1];
  const showDivider = item.is_dependency && (!prev || !prev.is_dependency);
  return (
    <Fragment key={item.student_id}>
      {showDivider && <DependencyDivider label="Dependência de Estudos" />}
      <StudentRow {...item} />
    </Fragment>
  );
})}
```

> Server-side a ordenação usa `db.students.find().collation({locale: 'pt', strength: 1})`.
> Em Python (fallback in-memory) usamos uma chave equivalente com remoção de diacríticos
> básica — comportamento alinhado com `localeCompare('pt-BR')` para nomes brasileiros.

---

## 18. Limite defensivo — `MAX_DEPENDENCY_STUDENTS_PER_DIARY = 30`

Se um diário receber mais de 30 alunos em dependência ativa:

- Não quebra renderização (todos ainda são retornados).
- Backend adiciona ao response:
  ```json
  {
    "warnings": [{
      "code": "EXCESS_DEPENDENCY_LOAD",
      "count": 47,
      "threshold": 30,
      "message": "Volume anômalo de alunos em dependência neste componente."
    }]
  }
  ```
- Telemetria: `record_diary_load(..., is_error=False)` continua, mas `labels.excess_dep=true`.
- Log crítico no servidor: `logger.error("[diary] excess dep load class=X course=Y count=N")`.
- Frontend mostra badge administrativa "Volume anômalo — verifique a secretaria".

> Caso típico: erro operacional (import CSV duplicado, seed errado). Sistema **não esconde** o problema, mas **não quebra**.

---

## 19. Validação automática de plano de execução

Toda query crítica deve passar por `assert_uses_index()` em testes:

```python
from utils.query_validation import assert_uses_index

plan = await db.student_dependencies.find({
    "mantenedora_id": tenant, "class_id": cid, "course_id": coid, "status": "active",
}).explain()
assert_uses_index(plan, expected_index_name="ix_dep_tenant_class_course_status",
                  description="diary_load")
```

### Fail explícito em DEV

Setando env `QUERY_INDEX_GUARD=1`, o backend valida queries críticas no startup e **falha** se cair em `COLLSCAN`. Implementação em `/app/backend/utils/query_validation.py` (`validate_critical_queries`).

> Em produção: opt-in. Em CI/dev: obrigatório.

---

## 20. Fixture E2E congelada — `fixture_dependency_diary_v1`

Dataset fixo para testes de regressão de TODA Fase 2+:

```text
1 mantenedora
1 escola
1 turma "5º ano A" (cl_fix_1)
2 componentes: Matemática (co_fix_mat), Português (co_fix_pt)

Alunos:
- 5 regulares (Ana, Bruno, Carlos, Diana, Eva) — enrollment ativo.
- 2 com dependência (Felipe e Gabriela) — enrollment ativo + 1 dep ativa em Matemática (origem 2025).
- 1 apenas dependência (Heitor) — sem enrollment regular + 2 deps ativas.
- 1 dep cancelada (Ivo, dep cancelada).
- 1 dep concluída (Júlia, dep completed com final_grade=7.5).
```

Seeder: `/app/backend/scripts/seed_dependency_diary_fixture.py`

Comando:
```bash
python -m scripts.seed_dependency_diary_fixture
```

Idempotente — pode rodar múltiplas vezes. Toda Fase 2+ valida-se contra **este** dataset.

---

## 21. Snapshot de baseline do payload

Antes de qualquer mudança no diário (Fase 2 e além), salvar baseline:

```bash
# Com a fixture v1 carregada:
TOKEN=$(...)
curl -s "$API/api/diary/class/cl_fix_1/course/co_fix_mat?academic_year=2026" \
  -H "Authorization: Bearer $TOKEN" \
  | tee /app/baselines/diary_response.json \
  | gzip -c | wc -c   # tamanho gzip
wc -c /app/baselines/diary_response.json   # tamanho bruto
```

Registrar em `/app/baselines/diary_baseline.md`:
- Tamanho bruto / gzip
- Tempo médio (10 chamadas)
- Quantidade de alunos (regulares + deps)
- Quantidade de componentes consultados
- p95 / p99 medidos

Servir como referência para detectar **regressão silenciosa** quando a UI começar a renderizar mais elementos.


---

## 22. Comparação automática de baseline (anti-regressão silenciosa)

**Atualização Fev/2026 — exigência §4 do owner.** Salvar arquivo NÃO basta;
sem comparação, performance degrada sprint após sprint.

Script: `/app/backend/scripts/compare_diary_baseline.py`

Modos:

```bash
# Gravar baseline inicial após carregar a fixture
python -m scripts.compare_diary_baseline --record

# Comparar estado atual contra baseline (CI / pré-merge)
python -m scripts.compare_diary_baseline --compare           # default 1.5x
python -m scripts.compare_diary_baseline --compare --threshold 1.2
```

Compara:
- `payload_size_bytes` (regressão se > 1.5× baseline)
- `p95_latency_ms` (regressão se > 1.5× baseline)
- `queries_count` (regressão se > 1.5× baseline)
- `p99_latency_ms`, `avg_latency_ms` (informativo)

Exit code `1` em regressão crítica → bloqueia merge em CI.

---

## 23. Anti-spoof na escrita (frequência e notas)

**Exigência §2 do owner (Fev/2026).** O backend NUNCA confia no payload do
navegador para resolver dependência. Toda gravação de attendance ou grade que
carrega `dependency_id != null` passa por `utils.dependency_validator.validate_dependency_link`,
que valida:

1. `dependency_id` existe na coleção `student_dependencies`.
2. `status='active'` (deps concluídas/canceladas/falhadas → 422).
3. `student_id` do payload bate com o da dependência.
4. `class_id` e `course_id` do payload batem com a dependência.
5. `tenant_id` do operador bate com o da dependência (RLS reforçada).

Qualquer violação → `HTTP 422` com `detail.code` em
`DEPENDENCY_COHERENCE_{NOT_FOUND,INACTIVE,STUDENT_MISMATCH,CLASS_MISMATCH,COURSE_MISMATCH,TENANT_MISMATCH}`.

---

## 24. Filtro automático de dependências inativas

**Exigência §3 do owner (Fev/2026).** O frontend não filtra; o backend só
entrega `status='active'`. Dependência marcada como `completed`, `cancelled`
ou `failed` desaparece automaticamente do diário na próxima carga — sem
necessidade de F5/cache invalidation no cliente.

Registros de attendance/grade já gravados com aquele `dependency_id`
continuam intactos para auditoria — mas a célula vai a read-only no UI.

---

## 25. Dependency ratio + alertas operacionais

**Exigências §8 e §9 do owner (Fev/2026).** Além de `regular_total` e
`dependency_total`, registramos no canal `diary`:

- `counters.dependency_ratio_sum_x100` + `counters.dependency_ratio_samples`
  → derivado em `avg_dependency_ratio_pct` no snapshot.
- `counters.excess_dep_loads` (cargas com `dependency_count > MAX = 30`).
- Label `excess_dep=true|false` em cada bucket.

Warnings emitidos no payload (não bloqueia diário):

| code | gatilho | log level |
|---|---|---|
| `EXCESS_DEPENDENCY_LOAD` | `dependency_count > 30` | `error` |
| `DEP_GREATER_THAN_REGULAR` | `dependency_count > regular_count` | `warning` |

Frontend renderiza badge administrativa quando `warnings` está presente.

---

## 26. Não tocar em (Fase 2)

**Exigência §10 do owner.** Esta fase entrega apenas leitura + frequência + notas.

❌ Fechamento anual.
❌ Recuperação por semestre/final.
❌ Conselho de classe.
❌ Histórico escolar.
❌ Boletim final / PDF.

Esses módulos serão tratados nas Fases 3 e 4 — incluí-los agora aumenta
o blast radius de bugs estruturais.
