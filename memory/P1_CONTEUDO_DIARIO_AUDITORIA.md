# P1 — Conteúdo/Diário Offline — AUDITORIA (P1.1) + Desenho (sem implementação)

> Entregue ANTES de codar, conforme diretriz dos arquitetos do SIGESC IA.
> Objetivo: mapear coleção, endpoint, motor canônico, versionamento e locks.

---

## 🚨 ACHADO CRÍTICO — Existem DOIS sistemas de "conteúdo"

A diretriz Princípio 1 ("um único motor de negócio") **já está em risco no estado atual**:
há duas coleções/motores distintos para conteúdo. Antes de construir offline, é
**obrigatório decidir qual é o canônico**.

| Aspecto | **`learning_objects`** (EM USO) | **`content_entries`** (NOVO, não ligado ao front) |
|---|---|---|
| Router | `routers/learning_objects.py` | `routers/content_entries.py` |
| Coleção | `learning_objects` | `content_entries` |
| UI que usa | **`LearningObjects.js` (`learningObjectsAPI`)** — é o que o professor usa hoje | **Nenhuma** (backend Rodada 2/3 pronto, frontend pendente) |
| Chave natural | `(class_id, course_id, date)` | `(class_id, component_id, teacher_id, date, aula_numero)` — UNIQUE parcial `ux_content_entry_logical` |
| Multi-autoria | ❌ Não (1 registro por turma+componente+dia) | ✅ Sim (`teacher_id` na chave) |
| Multi-aula no mesmo dia | ❌ Não | ✅ Sim (`aula_numero`) |
| Versionamento | ❌ Não tem `version` | ✅ `version`, `expected_version` |
| Optimistic locking | ❌ Não | ✅ Sim (force_overwrite + change_note) |
| Delete | Hard delete | Soft delete (`deleted=true`) |
| Workflow | Sem status (registro direto) | `draft → published → corrected` (publish/correct) |
| Auditoria | Não registra audit no create/update | ✅ `audit_logs` em toda escrita |
| Locks | `academic_year aberto` + `bimestre edit deadline` (calendário) | Sem locks de calendário; protege via versão+status |
| Campos pedagógicos | Ricos: BNCC skills, adaptações, recursos, evidência, prática | content/methodology/observations |
| Multi-tenant | ✅ `mantenedora_id` derivado da turma | ✅ `school_id` derivado; (verificar mantenedora_id) |

### Por que isso importa para o offline
Replicar o offline em cima de `learning_objects` significaria construir sobre um motor
**sem versão, sem locking, com hard delete e sem auditoria** — o oposto do que fizemos
(e aprovamos) na Frequência. Já `content_entries` é praticamente um espelho do padrão
canônico da Frequência (version + locking + audit + chave natural via índice único),
mas **ainda não tem frontend**.

---

## P1.1 — Respostas à auditoria solicitada

**Onde o conteúdo é salvo hoje?**
- Motor ATIVO: `routers/learning_objects.py` → coleção `learning_objects`.
- Endpoints: `POST/GET/PUT/DELETE /api/learning-objects`, `/copy-to-class`, `/check-date`, `/pdf/bimestre`.
- Frontend: `pages/LearningObjects.js` via `learningObjectsAPI`.

**Existe versionamento?**
- `learning_objects`: **NÃO** (só `updated_at`/`recorded_by`; sem `version`, sem `expected_version`).
- `content_entries`: **SIM** (`version`, `updated_at`, `updated_by`, optimistic locking completo).

**Existe lock pedagógico?**
- **NÃO existe Academic Event Lock** em conteúdo (diferente da Frequência) — conteúdo é por
  turma/componente/dia, não por aluno.
- `learning_objects` tem locks de **calendário**: `verify_academic_year_open_or_raise` e
  `verify_bimestre_edit_deadline_or_raise` (prazo de edição por bimestre). Estes são
  **server-authoritative** e dependem de calendário/configuração — atenção offline.
- `content_entries` não tem locks de calendário, mas tem **lock de versão** + workflow de status.

---

## Desenho proposto (a confirmar APÓS a decisão do motor canônico)

### Decisão necessária (arquitetos)
**Opção A — Unificar no `content_entries` (recomendada a médio prazo):** ligar o frontend
(`LearningObjects.js`) ao `content_entries`, migrar dados de `learning_objects`, e então
construir offline sobre o motor canônico moderno. Mais trabalho, mas elimina o motor duplo
e entrega offline sobre base versionada/auditada (coerente com a Frequência).

**Opção B — Offline sobre `learning_objects` (caminho curto):** primeiro endurecer o
`learning_objects` (extrair motor canônico `save_learning_object_canonical`, adicionar
`version`+locking, trocar hard→soft delete) e então plugar offline. Evita migração de dados
agora, mas mantém dois modelos de conteúdo convivendo.

> Em ambos os casos, o offline reusa o MESMO motor canônico (Princípio 1) e a MESMA fila
> genérica de sync (não criar segunda fila — Princípio 2/3).

### Estruturas offline (comuns às duas opções)
- **IndexedDB:** NÃO criar store separada de fila. Reusar `syncQueue` com `collection`
  = `'content'` (ou `'content_entries'`/`'learning_objects'` conforme decisão) e `naturalKey`.
  Cache de leitura offline: nova store `content_local` keyed por naturalKey (espelho do diário).
- **Chave natural (alinhar ao motor escolhido):**
  - se `content_entries`: `class_id|component_id|teacher_id|date|aula_numero`
  - se `learning_objects`: `class_id|course_id|date` (avaliar incluir `teacher_id` para multi-autoria)
- **Idempotência (A3):** `addToSyncQueue(..., naturalKey)` já deduplica → N edições = 1 item.
  O backend deve fazer **UPSERT por chave natural** (hoje o create rejeita duplicata com
  400/409 → precisa virar upsert no caminho de sync, como fizemos na Frequência).

### Motor canônico de sync (A2)
- Extrair `save_content_canonical(db, user, request, payload, audit_service)` (espelho de
  `save_attendance_canonical`) e chamá-lo tanto no endpoint HTTP quanto em
  `routers/sync.py::_sync_content_canonical`. **Sem `insert_one` cru no sync.**
- **Locks de calendário offline:** validar SEMPRE no servidor no momento do sync
  (server-authoritative). Se o bimestre fechou enquanto o professor estava offline, o sync
  deve retornar falha explícita (item fica `failed` com motivo claro), nunca perder
  silenciosamente. Definir UX: alertar o professor sobre lançamentos rejeitados por prazo.

### Pré-cache (P1.3 — entra junto da P1 ou logo após)
Ao abrir a turma ONLINE, pré-carregar (limite ~30 dias): alunos, horários, calendário,
frequências recentes e **conteúdos recentes** → permite registrar conteúdo offline já com
contexto (componentes/aulas) sem ação manual.

### Critérios de aceite (P1.4) — a validar (pytest + E2E offline)
- A) Online → registra conteúdo → persistido.
- B) Offline → registra → salvo localmente.
- C) Offline → fecha/reabre → conteúdo permanece.
- D) Offline → edita 5x → **1 item** na fila (estado final).
- E) Reconecta → sync automático, **sem duplicação, sem perda**; rejeições por prazo/lock
  são reportadas explicitamente.

---

## Recomendação ao board
1. **Decidir Opção A vs B** (motor canônico de conteúdo) — é o gargalo do Princípio 1.
2. Só então desenho de implementação detalhado + tarefas.
3. Implementação **após** homologação da Fase A em produção (conforme sequenciamento).
