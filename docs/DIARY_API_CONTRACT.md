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

**Proibido**:
- ❌ Vermelho agressivo
- ❌ Ícone de alerta/erro
- ❌ Texto variante (`"Dep."`, `"Dependente"`, etc.)

> Dependência é **condição pedagógica**, não erro.

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
