# Dependência de Estudos — SIGESC

> **Status**: Fase 1 implementada (Fev/2026). Fases 2-4 no roadmap.
> Dependência **NÃO** é matrícula simplificada — é entidade acadêmica própria.

---

## 1. Conceito

Dependência de Estudos representa o **vínculo acadêmico parcial** de um aluno a um componente curricular específico em regime especial. O aluno pode:

- Estar **com dependência** (`with_dependency`): aprovado parcialmente, mas com componentes pendentes.
- Estar **em dependência** (`dependency_only`): matrícula exclusiva para cursar dependências, sem turma regular.

São modos **mutuamente exclusivos** por construção (enum `dependency_mode`, não 2 booleanos).

---

## 2. Modelo de dados

### `Student.dependency_mode`

```python
dependency_mode: Literal['none', 'with_dependency', 'dependency_only'] = 'none'
```

> Modelado como enum (não 2 booleanos) para eliminar estados inválidos. Simplifica queries, frontend e relatórios.

### Coleção `student_dependencies`

```python
class StudentDependency:
    id: str
    mantenedora_id: str        # tenant scope
    student_id: str
    school_id: str
    class_id: str              # turma onde cursará (frequência/notas vão pra cá)
    course_id: str             # componente curricular
    teacher_id: Optional[str]
    
    academic_year: int         # ano em que está cursando
    origin_academic_year: int  # ano de origem (quando reprovou) — CRÍTICO p/ histórico
    origin_class_id: Optional[str]
    origin_series: Optional[str]
    
    status: Literal['active', 'completed', 'failed', 'cancelled']
    final_grade: Optional[float]
    completed_at: Optional[str]
    
    observations: Optional[str]
    created_at, created_by, updated_at, updated_by
```

### Índices

```python
db.student_dependencies.create_index("id", unique=True)
db.student_dependencies.create_index([("student_id", 1), ("status", 1)])
db.student_dependencies.create_index([("class_id", 1), ("course_id", 1), ("status", 1)])  # diário
db.student_dependencies.create_index([("mantenedora_id", 1), ("school_id", 1), ("academic_year", 1)])
# Duplicidade: 1 dep ativa por aluno×componente×ano de origem
db.student_dependencies.create_index(
    [("student_id", 1), ("course_id", 1), ("origin_academic_year", 1)],
    unique=True,
    partialFilterExpression={"status": "active"},
)
```

---

## 3. Endpoints

| Método | Path | Permissão | Descrição |
|---|---|---|---|
| POST | `/api/student-dependencies` | manage | Cria dependência (valida mode, limite, duplicidade) |
| GET | `/api/student-dependencies/student/{student_id}` | view | Lista dependências do aluno (enriquecido com class/course names) |
| GET | `/api/student-dependencies/student/{student_id}/summary` | view | Resumo (active/completed/failed/cancelled + limite + mode) |
| GET | `/api/student-dependencies/class/{class_id}/course/{course_id}` | view | **Fase 2 (diário)** — alunos em dep ativa nesta turma+componente |
| PUT | `/api/student-dependencies/{id}` | manage | Atualiza status/grade/observações |
| DELETE | `/api/student-dependencies/{id}` | manage | Remove dependência (audit log obrigatório) |

### Roles

```python
DEPENDENCY_MANAGE_ROLES = {"super_admin", "admin", "admin_teste", "gerente", "secretario", "diretor"}
DEPENDENCY_VIEW_ROLES   = MANAGE | {"coordenador", "apoio_pedagogico", "professor", "semed*"}
```

---

## 4. Validações obrigatórias

1. **Aluno deve ter `dependency_mode != 'none'`** antes de vincular componente. Caso contrário 400.
2. **Mantenedora deve permitir o modo** (`aprovacao_com_dependencia` ou `cursar_apenas_dependencia`).
3. **Limite de componentes** lendo da config da mantenedora (`max_componentes_dependencia` / `qtd_componentes_apenas_dependencia`).
4. **Duplicidade**: não pode haver 2 dependências `active` para o mesmo `(student_id, course_id, origin_academic_year)`. Imposto via índice único parcial.
5. **Tenant scope**: todas as queries usam `apply_tenant_filter`.
6. **[Fev/2026] Mudança de `dependency_mode` → `none` com vínculos ativos**: exige confirmação explícita via header `X-Confirm-Cancel-Dependencies: yes`. Sem o header, retorna 409. Com o header, todas as deps `active` são automaticamente marcadas como `cancelled` com `status_reason="[auto] dependency_mode alterado para 'none' por <usuário>"`.
7. **[Fev/2026] Exclusão de turma com dep ativa**: bloqueada com HTTP 409 — `DELETE /api/classes/{id}` retorna mensagem clara orientando a cancelar/concluir as deps antes.
8. **[Fev/2026] Exclusão de componente com dep ativa**: bloqueada com HTTP 409 — `DELETE /api/courses/{id}` idem.
9. **[Fev/2026] `status_reason` (free-text controlado)**: registra motivo da mudança de status. Crítico para casos de cancelamento, transferência, equivalência, dispensa, decisão judicial, conselho de classe. Recomendação: prefixar com tag (`[transferencia]`, `[conselho]`, `[judicial]`, `[auto]`).

---

## 5. Frontend

### Hook canônico (a criar quando precisar reuso): `useStudentDependencies(studentId)`

### Componente `<StudentDependencySection />` — `/app/frontend/src/components/StudentDependencySection.jsx`

- Renderiza radio (none / with / only) — opções dinâmicas conforme flags da mantenedora.
- Mostra card resumido (active/completed/failed/limite).
- Lista dependências ativas com botão "Remover".
- Modal "Vincular componente" (turma + curso + ano de origem).
- `readOnly`: oculta ações em modo visualização.

### Plugagem
- `StudentsComplete.js`, aba **Info. Complementares** — seção aparece só se mantenedora tiver pelo menos uma flag.

---

## 6. Roadmap

### Fase 2 — Diário (P1)
- Aluno com dep aparece **apenas** no diário do componente vinculado.
- Sufixo `(Dependência)` no nome.
- Listagem visualmente separada (preferencialmente no final).
- Anti-duplicidade: nunca aparecer em outros componentes da turma.

#### 🚨 Diretrizes arquiteturais OBRIGATÓRIAS para a Fase 2

##### 1. Diário NÃO pode inferir dependência implicitamente

> **Erro mais perigoso possível**:
> ```python
> if student.dependency_mode != "none":  # ❌ NÃO FAZER
>     ...
> ```

O diário deve depender **EXCLUSIVAMENTE** de:
```python
student_dependencies.find({
    "class_id": class_id,
    "course_id": course_id,
    "status": "active",
})
```

Razão:
- `dependency_mode` é **estado administrativo** (intenção do secretário).
- `student_dependencies` é o **vínculo pedagógico real** (concreto).
- Misturar os dois cria inconsistência invisível: aluno com `mode=with_dependency` mas sem componente vinculado → apareceria em diário errado.

##### 2. Padrão `regular + dependency = view_model` (não fundir)

```text
regular_students        ← query 1: enrollments.find({class_id, status:'active'})
+
dependency_students     ← query 2: student_dependencies.find({class_id, course_id, status:'active'})
↓
diary_view_model        ← junção controlada com flag is_dependency
```

NÃO mexer no enrollment para forçar dependência (cria duplicidade estrutural).

##### 3. Ordem visual obrigatória no diário

```text
1. alunos regulares (sort alfabético do nome)
2. dependências (no final, sort alfabético separado)
3. badge discreta "(Dependência)"
```

Exemplo:
```
Ana Souza
Carlos Lima
Maria Santos
─────────────────
João Ferreira (Dependência)
Pedro Alves   (Dependência)
```

NÃO misturar aleatoriamente no sort alfabético — confunde o professor.

##### 4. Hooks React — anti-padrões proibidos no Diário

- ❌ Hooks condicionais (`if (...) const x = useState(...)`)
- ❌ Listas montadas em árvores diferentes (regular vs dep) — usar lista única derivada via `useMemo`.
- ❌ Alterar ordem de hooks entre renders.

Padrão correto:
```jsx
const diaryStudents = useMemo(() => {
  return [...regularSorted, ...dependencySorted];
}, [regularSorted, dependencySorted]);
// renderiza lista única
```

##### 5. Telemetria desde o dia 1

Use o canal pré-registrado em `/app/backend/utils/observability.py`:

```python
from utils.observability import diary_metrics

t0 = time.monotonic()
... # query
diary_metrics.record(
    duration_ms=(time.monotonic() - t0) * 1000,
    tenant_id=current_user["mantenedora_id"],
    labels={"class_id": class_id, "course_id": course_id, "cache_hit": False},
    bucket_counters={"students_regular": len(reg), "students_dep": len(deps)},
)
```

Monitorar via `GET /api/admin/observability/diary` (super_admin only).

Métricas-alvo:
- `p95_latency_ms` < 250ms
- `p99_latency_ms` < 1000ms
- `students_dep / requests_total` (média de deps por carregamento)

##### 6. Frequência / notas / fechamento — separação lógica

Mesmo que a Fase 2 reutilize o motor de notas/frequência atual, manter **separação lógica**:
- Frequência da dep tem `dependency_id` no documento (não só `student_id`).
- Notas da dep idem.
- Fechamento da dep é evento independente do fechamento da turma regular.

Justificativa: conselho, recuperação, histórico e transferência exigirão separação. Custo de retrocompatibilizar é altíssimo se misturar agora.

#### Checklist pré-Fase 2 (a executar)

- [x] Índices `(tenant_id, class_id, course_id, status)` + `(student_id, status)` + `(academic_year, status)` com `background=True`.
- [x] Telemetria genérica reutilizável (`utils/observability.py`).
- [x] Endpoint `/api/admin/observability/diary` registrado.
- [ ] Validar E2E da Fase 1 na UI.
- [ ] Rodar `explain()` no Mongo nas queries planejadas (validar uso dos índices).
- [ ] Medir payload do diário atual (baseline antes da Fase 2).
- [ ] Congelar contrato da API do Diário antes da implementação.

#### Implementação incremental sugerida (Fase 2)

1. Leitura (GET endpoint do diário com regulares + deps separados).
2. Renderização (lista única derivada, ordem visual, badge).
3. Frequência (lançamento por aluno × dia, com `dependency_id` quando aplicável).
4. Notas (idem).
5. Fechamento (Fase 4 — evento separado).

### Fase 3 — Boletim Online + PDF + Ficha (P2)
- Seção "Dependência de Estudos" separada no boletim online.
- Página exclusiva no PDF: "Boletim de Dependência".
- Seção na ficha individual com componente, ano, turma, CH, resultado final.

### Fase 4 — Fechamento anual + Histórico (P2)
- Lógica de fechamento isolada (aprovação/reprovação por componente).
- Histórico escolar marca claramente: "Dependência cursada em regime especial".
- **Não** aparecer como disciplina regular da série atual.

---

## 7. Auditoria

Todas as ações `create`, `update`, `delete` chamam `audit_service.log` com `collection='student_dependencies'`. Críticos para auditoria escolar.

---

## 8. Anti-padrões — proibidos

- ❌ Tratar dependência como matrícula/`enrollment` simplificada.
- ❌ Booleanos `in_dependency` + `with_dependency` (aceita estado inválido `True/True`).
- ❌ Misturar dep com componentes regulares no boletim/diário.
- ❌ Permitir vincular sem `class_id` (quebra diário, frequência, notas, professor responsável, CH).
- ❌ Não validar limite da mantenedora (vira "vale tudo").

---

**Mantido por**: Equipe SIGESC
**Última atualização**: Fev/2026 (Fase 1 entregue)
