# Contrato Normativo: Eventos Acadêmicos & Continuidade Pedagógica

> **Status: CONGELADO V1 (Fev/2026).**
> Documento normativo. Mudanças exigem PR explícito + bump de `contract_version`.
> Este contrato precede qualquer implementação de movimentação acadêmica.

```yaml
contract_version: 1
schema_version: 1
issued_at: 2026-02-08
status: FROZEN
```

## 1. Princípio fundador

> **Movimentações escolares NÃO removem o aluno da turma de origem.**

Toda movimentação acadêmica é evento **temporalmente delimitado** —
nunca uma "transferência física" de registros entre turmas. O sistema
preserva:

- rastreabilidade pedagógica;
- integridade histórica;
- autoria docente original;
- continuidade documental;
- coerência entre diário, frequência, notas, boletim e histórico.

> **Lançamentos anteriores ao evento permanecem para sempre vinculados à
> turma/professor de origem.**

---

## 2. Eventos cobertos (V1)

| Evento | Descrição | Approval Required |
|---|---|---|
| `transfer` | Transferência intra-rede entre escolas/turmas | Sim |
| `remanejamento` | Mudança de turma na mesma escola | Sim |
| `reclassificacao` | Aluno avança/regride por avaliação especial | Sim |
| `progressao_parcial` | Aluno avança com pendências (≠ dependência) | Sim |

Eventos NÃO cobertos nesta V1 (escopo futuro):
- abandono escolar
- evasão
- óbito
- transferência inter-rede

---

## 3. Modelo canônico de evento (`db.academic_events`)

```json
{
  "id": "<uuid>",
  "event_type": "transfer | remanejamento | reclassificacao | progressao_parcial",
  "effective_date": "YYYY-MM-DD",
  "student_id": "...",
  "origin_class_id": "...",
  "destination_class_id": "...",
  "origin_school_id": "...",
  "destination_school_id": "...",
  "mantenedora_id": "...",
  "academic_year": 2026,
  "rationale": "Texto livre — obrigatório",
  "approval_required": true,
  "approved_by_user_id": "...",
  "approved_at": "ISO timestamp",
  "approval_status": "pending | approved | rejected",
  "rejection_reason": null,
  "created_by_user_id": "...",
  "created_at": "ISO",
  "supersedes_event_id": null,
  "audit_trail": [
    {
      "action": "created | approved | rejected | superseded",
      "by_user_id": "...",
      "at": "ISO",
      "snapshot_before": {},
      "snapshot_after": {}
    }
  ]
}
```

Coleção é **append-mostly**: updates apenas via fluxo aprovado de §10.

---

## 4. Regra Temporal — antes da `effective_date`

Para todo lançamento (frequência, nota) com `date < effective_date`:

### 4.1 Turma de origem
- ✅ Editável pelo professor de origem (mantém autoria).
- ✅ Permanece visível no diário da origem.
- ✅ Continua compondo histórico do aluno.
- ✅ Compõe fechamento da turma de origem proporcionalmente até `effective_date`.

### 4.2 Turma de destino
- 📖 Registros aparecem como **read-only** (projeção do canônico).
- 🔒 Bloqueados para edição. HTTP 409 em qualquer tentativa.
- 🏷️ Badge visual obrigatório no UI: **"Registro herdado da turma de origem"**.
- 🔄 Sincronização é **unidirecional**: origem → destino. Mudanças do
  professor de origem refletem na destino em até 1 minuto.

### 4.3 Sincronização técnica
- **NÃO duplicar fisicamente** registros entre turmas.
- Origem é o **canonical store**.
- Destino consulta via **read-model temporal**:
  - `db.attendance.find({"student_id": sid, "date": {"$lt": effective_date}, "class_id": {"$in": [origin, destination]}})` retorna registros da origem mas com flag `_inherited=true`.
- Implementação: middleware/service `academic_event_lens.py` que reescreve
  queries quando o aluno tem evento ativo.

---

## 5. Regra Temporal — a partir da `effective_date`

Para todo lançamento (frequência, nota) com `date >= effective_date`:

### 5.1 Turma de origem
- 👤 Aluno permanece listado no diário (não some).
- 🔒 Frequência/notas ficam **bloqueadas** para o aluno.
- 🏷️ Marcador visual: **"Aluno movimentado em DD/MM/AAAA"**.
- ❌ Professor origem **não pode editar** registros do aluno após data.

### 5.2 Turma de destino
- ✅ Registros são **exclusivos** da destino.
- ✅ Editáveis apenas pelo professor destino.
- ❌ Não sincronizam mais com origem.

---

## 6. Regras críticas — INVARIANTES

> Estas regras são **invariantes do domínio**. Violação → bug arquitetural
> grave que compromete histórico escolar.

### 6.1 Proibido mover registros históricos entre turmas
A coleção `attendance.records[]` e `grades` mantém `class_id` original
imutável. Qualquer reescrita de `class_id` em registros existentes é proibida.

### 6.2 Proibido alterar autoria original
`created_by_user_id` em registros de attendance/grade é imutável após
`created_at + 24h`.

### 6.3 Proibido reatribuir frequência/notas antigas
Mesmo após movimentação, registros mantêm `class_id` e `course_id` originais.

### 6.4 Proibido apagar vínculo do aluno com turma de origem
`enrollments` da origem **não vão para `status='cancelled'`** após
movimentação. Recebem `status='moved_out'` com `moved_out_event_id`
referenciando o evento.

### 6.5 Proibido recalcular fechamento retroativamente sem auditoria
Recálculos pós-fechamento exigem fluxo §10 (justificativa + aprovação +
snapshot before/after).

---

## 7. Fonte da verdade

```
db.academic_events  →  fonte única e autoritativa
```

Sistema **NUNCA** deve inferir bloqueios/permissões pela
`students.class_id` atual ou por `enrollments.status` isoladamente.

Permissões e bloqueios são derivados via:

```python
from utils.academic_event_lens import resolve_student_class_state

state = await resolve_student_class_state(
    db=db, student_id=sid, class_id=cid, target_date="2026-08-15",
)
# state = {
#   "is_member": True/False,
#   "is_inherited": True/False,         # registro vem da origem
#   "is_locked_for_edit": True/False,
#   "blocking_event": {...},            # evento que bloqueia (se houver)
#   "lock_reason": "AFTER_EFFECTIVE_DATE | BEFORE_EFFECTIVE_DATE_DESTINATION",
# }
```

---

## 8. Auditoria de tentativas de edição

Toda tentativa de escrita bloqueada por evento gera entrada em
`db.academic_event_audit`:

```json
{
  "id": "<uuid>",
  "event_id": "...",                      // evento que bloqueou
  "action": "grade_edit_blocked | attendance_edit_blocked | grade_create_blocked",
  "attempted_by_user_id": "...",
  "attempted_role": "professor",
  "target_student_id": "...",
  "target_class_id": "...",
  "target_date": "YYYY-MM-DD",
  "target_resource": "grade | attendance",
  "reason_code": "AFTER_EFFECTIVE_DATE | BEFORE_EFFECTIVE_DATE_DESTINATION | NO_AUTHORSHIP",
  "ip": "...",
  "user_agent": "...",
  "created_at": "ISO"
}
```

Resposta HTTP correspondente:
```http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "detail": {
    "code": "ACADEMIC_EVENT_LOCK",
    "reason_code": "AFTER_EFFECTIVE_DATE",
    "event_id": "...",
    "effective_date": "2026-08-15",
    "message": "Aluno foi movimentado em 15/08/2026. Edição bloqueada."
  }
}
```

Observabilidade: canal `academic_events` registra contagem de bloqueios
por `reason_code` para detectar má-formação operacional (professor que
insiste em editar registro alheio).

---

## 9. Read-model temporal (implementação obrigatória)

Para o aluno tem evento ativo, queries de listagem/diário consultam ambas
as turmas e marcam herança:

```python
async def list_diary_items_with_event_lens(
    db, *, class_id, course_id, academic_year, target_date
):
    # 1. Itens canônicos da turma alvo
    items = await load_diary_items(db, class_id=class_id, ...)

    # 2. Eventos ATIVOS do aluno onde target_date está no intervalo herdado
    events = await db.academic_events.find({
        "$or": [
            {"origin_class_id": class_id},
            {"destination_class_id": class_id},
        ],
        "approval_status": "approved",
    }).to_list(...)

    # 3. Aplica lente: marca _inherited, _locked, etc. por aluno
    for item in items:
        ev = next((e for e in events if e["student_id"] == item["student_id"]), None)
        if not ev: continue
        if class_id == ev["destination_class_id"] and target_date < ev["effective_date"]:
            item["_inherited"] = True
            item["_lock_reason"] = "BEFORE_EFFECTIVE_DATE_DESTINATION"
        elif class_id == ev["origin_class_id"] and target_date >= ev["effective_date"]:
            item["_inherited"] = False
            item["_locked"] = True
            item["_lock_reason"] = "AFTER_EFFECTIVE_DATE"
            item["_event_id"] = ev["id"]

    return items
```

---

## 10. Fluxo obrigatório para alteração/exclusão de evento

Eventos acadêmicos **NÃO** podem ser alterados/removidos livremente.
Toda mudança exige TODOS os passos abaixo:

1. **Justificativa textual** (`rationale`, ≥ 30 chars).
2. **Usuário com papel autorizado** — apenas `super_admin`, `admin`,
   `gerente`, `secretario` (validado server-side).
3. **Confirmação humana explícita** — header `X-Academic-Event-Confirm: true`
   exigido na requisição (UI mostra modal de dupla confirmação).
4. **Auditoria completa** — entrada em `academic_event_audit` com
   `snapshot_before` + `snapshot_after`.
5. **Supersession (não exclusão)**:
   - Eventos NÃO são deletados.
   - Mudança = criar novo evento com `supersedes_event_id` apontando para
     o anterior.
   - Anterior recebe `approval_status='superseded'` mas continua na coleção.

```python
@router.put("/academic-events/{event_id}")
async def update_event(event_id, payload, request):
    if not payload.rationale or len(payload.rationale) < 30:
        raise HTTPException(422, detail={"code": "RATIONALE_TOO_SHORT"})
    if request.headers.get("X-Academic-Event-Confirm") != "true":
        raise HTTPException(428, detail={"code": "CONFIRMATION_REQUIRED"})
    if current_user.role not in {"super_admin", "admin", "gerente", "secretario"}:
        raise HTTPException(403, detail={"code": "INSUFFICIENT_PRIVILEGE"})
    # ... cria novo evento com supersedes_event_id
```

---

## 11. Impacto em outros domínios

Este contrato **impactará** os seguintes módulos quando implementados:

| Módulo | Impacto |
|---|---|
| Diário | Lente temporal em `/api/diary/...` filtra registros por evento |
| Frequência | Bloqueio HTTP 409 + auditoria em escritas após `effective_date` |
| Notas | Mesmo |
| Boletim | Snapshot por turma onde o aluno cumpriu cada período |
| Histórico Escolar | Campo `class_label_at_issue` é a turma de origem ou destino conforme o período |
| Ficha Individual | Mesma lógica do boletim |
| Censo | Aluno aparece na turma de destino a partir de `effective_date` |
| Relatórios | Queries pré-`effective_date` retornam dados da origem mesmo se filtrarem por destino |
| Fechamento anual | Cada turma fecha **seus** períodos; aluno movimentado tem fechamento composto |
| Dependência | Movimentação durante dependência ativa ⇒ aluno mantém vínculo da dep com escola/turma onde foi reprovado originalmente |
| Reclassificação | Caso especial deste contrato — `effective_date = data_da_avaliacao` |
| Progressão parcial | Idem |
| Transferência intra-rede | Idem |

---

## 12. Não tocar nesta V1

- ❌ Inter-rede (transferência entre mantenedoras) — exige tratado entre
  prefeituras ou mecanismo de federação.
- ❌ Histórico inter-rede — Fase futura.
- ❌ Recálculo automático pós-evento — fechamento sempre proporcional.
- ❌ Mover registros físicos — fica eternamente proibido.

---

## 13. Cenários de teste obrigatórios (quando implementar)

1. Movimentação aprovada antes de qualquer lançamento — destino limpo.
2. Movimentação com lançamentos anteriores — destino mostra herdados.
3. Tentativa de editar registro herdado pelo professor destino → 409.
4. Tentativa de editar registro pré-data pelo professor origem → 200 OK.
5. Tentativa de editar registro pós-data pelo professor origem → 409.
6. Sync unidirecional: professor origem edita registro pré-data → reflete em destino em ≤1min.
7. Aluno com 2 movimentações no ano — 3 turmas, 3 períodos.
8. Movimentação durante dependência ativa — dep não migra.
9. Supersedência: substituir evento aprovado por novo → antigo vira `superseded`.
10. Auditoria: tentativa bloqueada gera registro com `reason_code` correto.
11. Read-model temporal: query no diário do destino antes de `effective_date` retorna 0 alunos para aquele aluno.
12. Read-model temporal: query no diário do destino após `effective_date` retorna registros exclusivos.

---

## 14. Versionamento

Quando bumpar `contract_version`?
- Adição de novo `event_type`.
- Mudança de invariante.
- Remoção/renomeação de campo canônico.

Quando bumpar `schema_version`?
- Adição de campo opcional não-quebrável.
- Mudança em formato de auditoria sem perda semântica.

Templates antigos NUNCA são deletados — apenas marcados como
`deprecated_for_new_events` em `event_type_versions`.

---

## 15. Precedência entre eventos concorrentes (Fev/2026)

Eventos múltiplos para o mesmo aluno em janelas sobrepostas devem resolver
para um **único** evento governante via precedência fixa:

```
reclassificacao > progressao_parcial > remanejamento > transfer
```

Implementação: `utils/academic_event_lens.pick_governing_event(events)`.

Tiebreaker (mesma precedência):
1. `effective_date` mais recente vence.
2. Se empate: `created_at` mais recente vence.

Eventos `pending` ou `superseded` são ignorados pela lens.

> **Observação:** a precedência V1 NÃO é configurável por mantenedora.
> Mudanças exigem PR + bump de `contract_version` e `decision_version` na lens.

---

## 16. Princípio de Persistência Pedagógica

> Movimentações acadêmicas **NÃO removem** rastreabilidade pedagógica histórica.

1. Transferência, remanejamento, reclassificação e progressão parcial NÃO
   removem o aluno das listagens históricas da turma/componente de origem.
2. Registros anteriores à `effective_date` permanecem visíveis e editáveis
   exclusivamente pelo contexto proprietário definido pela lens temporal.
3. Registros posteriores à `effective_date` ficam bloqueados no contexto
   anterior com justificativa explícita (`AFTER_EFFECTIVE_DATE`).
4. O contexto de destino pode exibir dados herdados anteriores ao evento
   apenas em modo leitura (`BEFORE_EFFECTIVE_DATE_DESTINATION`).
5. Alterações em dados pré-evento realizadas no contexto proprietário devem
   refletir automaticamente nos contextos herdados (sync_mode = "origin_authoritative").
6. Nenhum evento acadêmico pode causar perda documental, sobrescrita
   histórica ou exclusão silenciosa de frequência/notas.

### 16.1 Implicações técnicas

- Campo `visible` no retorno da lens é **sempre** `true` para o contexto
  proprietário OU herdado. NUNCA usar `visible: false` para "esconder" um aluno.
- Frontend NÃO infere lock localmente. Toda decisão vem do backend via lens.
- Coleção `enrollments` da origem NÃO recebe `status: 'cancelled'` em
  movimentação — recebe `status: 'moved_out'` com `moved_out_event_id`.

---

## 17. Supersession obrigatória + Timezone institucional

### 17.1 Supersession

Eventos NUNCA são editados in-place. Qualquer alteração material exige:

- `POST /api/academic-events/{id}/supersede` com `new_payload` + `rationale ≥ 30`.
- Header `X-Academic-Event-Confirm: true`.
- Cria novo evento aprovado com `supersedes_event_id = old_id`.
- Antigo recebe `approval_status = 'superseded'` + `superseded_by_event_id`.
- Audit trail preserva snapshot before/after no novo evento.

### 17.2 Timezone institucional

`effective_date` é resolvido no timezone da mantenedora (campo
`mantenedoras.timezone`). Default: `America/Sao_Paulo`.

> NUNCA comparar datas naïve UTC em bloqueios pedagógicos. Aulas começam às
> 7h da manhã horário local, não 7h UTC. Usar timezone errado bloqueia
> escritas legítimas no início do turno e libera escritas indevidas no fim.

A lens `_to_date(value, tz)` resolve qualquer entrada (str ISO, datetime UTC,
datetime naïve, date) para `date` no tz institucional antes de comparar.

---

## 18. ACADEMIC_EVENT_LOCK — formato de auditoria

Toda tentativa bloqueada pela lens gera entrada em `db.academic_event_audit`:

```json
{
  "id": "<uuid>",
  "event_id": "...",
  "action": "grade_create_blocked | grade_edit_blocked | attendance_create_blocked | attendance_edit_blocked",
  "attempted_by_user_id": "...",
  "attempted_role": "professor",
  "target_student_id": "...",
  "target_class_id": "...",
  "target_date": "YYYY-MM-DD",
  "target_resource": "grade | attendance",
  "reason_code": "AFTER_EFFECTIVE_DATE | BEFORE_EFFECTIVE_DATE_DESTINATION",
  "payload_hash": "sha256_hex",     // hash do payload tentado (sem PII)
  "ip": "...",
  "user_agent": "...",
  "created_at": "ISO"
}
```

Resposta HTTP correspondente:
```http
HTTP/1.1 409 Conflict
{
  "detail": {
    "code": "ACADEMIC_EVENT_LOCK",
    "reason_code": "AFTER_EFFECTIVE_DATE",
    "event_id": "...",
    "governing_event_type": "transfer",
    "effective_date": "2026-08-15",
    "message": "Edição bloqueada por evento acadêmico."
  }
}
```

---

## 19. Restrição arquitetural — Frontend não infere lock

> **Toda decisão de lock/visibilidade vem do backend via lens.**

Listagens de diário enriquecem cada item com:
- `_locked: bool`
- `_inherited: bool`
- `_lock_reason: str | null`
- `_governing_event_id: str | null`
- `_governing_event_type: str | null`
- `_historical_cutoff_date: str | null`

Frontend renderiza badges/desabilita inputs apenas com base nesses campos.
Nunca calcula `effective_date < today` no cliente. Nunca compara datas no JS.

---

## 20. Continuidade Avaliativa Temporal (Fev/2026)

> Regra pátria do domínio acadêmico — ao lado de §16 (Persistência Pedagógica).

1. O aluno movimentado permanece **visível em ambas as estruturas pedagógicas**
   conforme a lente temporal: nunca some da origem nem aparece como "novo" no destino.

2. A **origem é autora canônica** dos registros anteriores à `effective_date`.
   Toda autoria docente registrada nesses lançamentos é preservada para sempre
   (`created_by_user_id` em grades/attendance é imutável após `created_at + 24h`).

3. O **destino é autor canônico** dos registros posteriores à `effective_date`.
   Mesmo se houver retificação retroativa em registros pré-`effective_date`,
   a autoria do destino sobre seus próprios registros não é afetada.

4. **Alterações retroativas autorizadas** (em registros pré-`effective_date` realizadas
   pelo professor de origem) devem propagar para representações herdadas no destino
   sem alterar autoria histórica. A propagação é **sempre por projeção**, nunca por
   replicação física (cf. §4.3).

5. O sistema deve preservar para sempre:
   - **autoria original** (`created_by_user_id`)
   - **timestamp original** (`created_at`)
   - **contexto institucional original** (`class_id`, `course_id`, `school_id`,
     `mantenedora_id` no momento da criação do registro)
   - **autoria de cada modificação** (audit_trail interno do registro)

6. Recálculo de fechamento, médias ou frequência **NUNCA** pode reescrever esses
   campos em registros existentes. Recálculo gera novos campos derivados
   (`computed_*`) ou novas coleções (`bulletin_snapshots`), preservando a
   integridade dos registros canônicos.

### 20.1 SLA institucional para eventos `pending`

Eventos com `approval_status = "pending"` carregam SLA derivado em endpoints
de observabilidade e fila operacional:

| sla_days | sla_status | Cor visual recomendada |
|---|---|---|
| 0–3  | `healthy` | verde |
| 4–7  | `warning` | âmbar |
| > 7  | `critical` | vermelho |

Implementação: `utils/academic_event_sla.py`, `sla_version = "1"`.
Mudanças nas faixas exigem PR + bump de `sla_version`.

### 20.2 Endpoint operacional `GET /api/academic-events/pending`

Fila visível para diretores/secretaria/SEMED com:
- Paginação (`page`, `page_size`, máximo 100).
- Filtros: `mantenedora_id`, `school_id`, `event_type`, `approval_status`
  (default `pending`), `created_before`, `older_than_days`.
- Ordenação default: `created_at ASC` (mais antigos primeiro).
- Resposta inclui `sla_summary: {healthy, warning, critical}` agregado para
  todos os pendentes do filtro (não da página).

### 20.3 Snapshot `GET /api/admin/observability/academic_events`

Dimensões separadas, sem misturar:

```json
{
  "channel": "academic_events",
  "sla_version": "1",
  "technical": {
    "lock_attempts_total": int,
    "lock_attempts_by_reason_code": {<reason_code>: int}
  },
  "operational": {
    "pending_total": int,
    "pending_healthy": int,
    "pending_warning": int,
    "pending_critical": int,
    "pending_age_p95_days": int,
    "supersessions_total": int,
    "approvals_last_24h": int
  },
  "pedagogical": {
    "events_by_type": {<event_type>: int}
  },
  "legal": {
    "blocked_post_effective_date_attempts": int,
    "blocked_pre_effective_date_attempts": int,
    "events_without_rationale": int,
    "superseded_chain_depth_p95": int
  }
}
```

Frontend (futuro mini-dashboard SEMED): renderiza um painel por dimensão.
Misturar dimensões num mesmo card é **proibido** — cada dimensão tem público,
escala temporal e ação operacional diferentes.

### 20.4 Endurecimento jurídico de supersession

Toda supersession DEVE preservar (em `db.academic_events`):

```json
{
  "superseded_by_event_id": "<id do novo>",
  "superseded_at": "ISO timestamp",
  "superseded_reason": "<rationale ≥ 30 chars do supersede>"
}
```

Esses três campos formam a tripla auditável que responde "quem alterou,
quando e por quê" em qualquer ponto futuro do tempo. Cobertura via
`test_supersession_chain_preserved`.


---

## 21. Fechamento Temporal Composto (Fev/2026 — Passo 3)

> Implementação canônica em `utils/temporal_closure.py`. Endpoints expostos
> em `routers/closure.py` (somente leitura nesta V1).

### 21.1 Princípio
Todo aluno movimentado tem fechamento **composto** — uma sequência de
janelas (`periods`) onde cada turma é dona apenas do intervalo em que
o aluno lhe pertenceu segundo a lente temporal (§7).

```
period = {
  period_index, class_id, course_id, school_id,
  period_start, period_end,                 # YYYY-MM-DD inclusive
  source: "origin" | "destination" | "sole",
  governing_event_id, governing_event_type,
  governing_effective_date,
}
```

### 21.2 Algoritmo
1. Coleta TODOS os eventos aprovados, não-superseded do aluno no `academic_year`.
2. Constrói breakpoints = `{year_start, *each effective_date, year_end+1}`.
3. Para cada segmento `[seg_start, seg_end]`, escolhe governante via
   `pick_governing_event(active_events_at_seg_start)`.
4. Pré-evento → `class_id = origin_class_id` do PRÓXIMO evento futuro;
   pós-evento → `class_id = destination_class_id` do governante.
5. Funde segmentos consecutivos com mesma turma + mesmo governante (idempotência visual).

### 21.3 Atribuição de bimestres
Bimestre B com `[b.start, b.end]` pertence ao período P se P contém `b.end`
(data de fechamento do bimestre). Bimestres cuja data final cai fora de
qualquer período do aluno ficam órfãos (`period_index = None` — caso
patológico, indica aluno saiu antes do fechamento).

### 21.4 Endpoints
| Endpoint | Retorno |
|---|---|
| `GET /api/closure/student/{sid}/composite?academic_year=Y` | `{periods, bimesters, is_composite}` |
| `GET /api/closure/student/{sid}/window?academic_year=Y&class_id=C` | `{class_id, envelope_start, envelope_end, segments}` ou 404 `NO_WINDOW_FOR_CLASS` |
| `GET /api/closure/class/{cid}/students?academic_year=Y` | lista de `{student_id, envelope_*, segments}` para alunos com janela na turma |
| `GET /api/closure/student/{sid}/periods?academic_year=Y` | lista enxuta apenas de períodos |

### 21.5 Invariantes
- Períodos cobrem `[year_start, year_end]` SEM gaps (a menos que aluno não tenha matrícula nem evento).
- Eventos `pending` ou `superseded` NUNCA aparecem como governantes.
- Precedência §15 aplicada idêntica à `resolve_student_ownership`.
- Closure é **read-model derivado** — nunca persiste janelas. Snapshot
  documental é responsabilidade do Boletim/Histórico (Fase futura),
  consumindo este contrato como fonte única.

### 21.6 Cobertura de testes obrigatória
- `tests/test_temporal_closure.py` (11 unit) cobre: sole, transfer simples,
  pendente ignorado, supersession ignorada, múltiplos movimentos,
  precedência, atribuição de bimestres, envelope, órfão, shape canônico.
- `tests/test_closure_e2e_http.py` (8 E2E) cobre todos os endpoints
  + autenticação + 404s.
