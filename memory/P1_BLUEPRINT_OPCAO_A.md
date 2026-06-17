# P1 — Conteúdo/Diário Offline — BLUEPRINT (Opção A) — SEM implementação

> Decisão dos arquitetos: **`content_entries` = fonte oficial**; `learning_objects` = **LEGADO**
> (congelado, permitido só durante a migração). Offline construído EXCLUSIVAMENTE sobre o
> motor moderno. Implementação só APÓS homologação da Fase A em produção.

## Estado real descoberto na auditoria (importante)
- `learning_objects`: **19 docs** (todos 2026), **sem chaves naturais duplicadas** → migração pequena e limpa.
- `content_entries`: **144 docs** (draft 72 / published 45 / corrected 27) — coleção já existe e é robusta,
  **mas nenhum frontend grava nela** (LearningObjects.js ainda grava em `learning_objects`).
- Já existe **`services/legacy_content_bridge.py`**, porém é **READ-ONLY** (sintetiza CE a partir de LO
  para leitura no Diário/snapshots quando CE está vazio). **Não** é o adapter de escrita da P1.2.
- `content_migrated` em LO vem do **fluxo de revisão de IA** (`content_review.py`), NÃO de migração LO→CE.

## ⚠️ Dois bloqueios de design a resolver ANTES de migrar
1. **Lacuna de schema (risco de perda de dados):** `content_entries` NÃO possui os campos pedagógicos
   ricos do `learning_objects`. É preciso ESTENDER o schema de `content_entries` antes da migração:
   | learning_objects | content_entries (hoje) | Ação |
   |---|---|---|
   | content / methodology / observations | ✅ existem | mapear direto |
   | course_id | ✅ course_id + component_id | course_id → ambos |
   | recorded_by | created_by/teacher_id | recorded_by → teacher_id/created_by |
   | date | ✅ | direto |
   | academic_year | ❌ ausente | **ADICIONAR** (necessário p/ lock de bimestre) |
   | number_of_classes | ❌ ausente | **ADICIONAR** |
   | resources | ❌ ausente | **ADICIONAR** |
   | skill_codigos (BNCC) | ❌ ausente | **ADICIONAR** |
   | adaptation_ids | ❌ ausente | **ADICIONAR** |
   | evidencia_aprendizagem | ❌ ausente | **ADICIONAR** |
   | pratica_pedagogica | ❌ ausente | **ADICIONAR** |
   | mantenedora_id | (usa school_id) | **ADICIONAR** mantenedora_id (consistência multi-tenant) |
2. **Locks de calendário ausentes no motor novo:** `learning_objects` valida `ano letivo aberto`
   (`verify_academic_year_open_or_raise`) e `prazo de edição do bimestre`
   (`verify_bimestre_edit_deadline_or_raise`). `content_entries` NÃO valida nada disso.
   Esses locks devem ser **portados para o motor canônico de `content_entries`** e aplicados
   **server-side no sync** (server-authoritative).

---

## Sequenciamento (alinhado aos arquitetos)

### P1.0 — Pré-requisitos (antes da migração)
- Estender `ContentEntryCreate`/doc de `content_entries` com os campos da tabela acima
  (`academic_year`, `number_of_classes`, `resources`, `skill_codigos`, `adaptation_ids`,
  `evidencia_aprendizagem`, `pratica_pedagogica`, `mantenedora_id`).
- Extrair **motor canônico** `save_content_canonical(db, user, request, payload, audit_service)`
  (espelho de `save_attendance_canonical`): upsert por chave natural, versionamento, audit,
  + **locks de calendário portados** (ano letivo + bimestre).
- Endpoint `POST /content-entries` passa a chamar `save_content_canonical`.

### P1.1 — Migração LO → CE (one-shot, idempotente, auditada)
- Script `scripts/migrate_learning_objects_to_content_entries.py`:
  - Para cada LO não migrado: monta payload → `save_content_canonical` (com `migration_source="learning_objects"`,
    `legacy_id=lo.id`, `status="published"`, `version=1`).
  - Chave natural CE: `class_id|component_id(=course_id)|teacher_id(=recorded_by)|date|aula_numero(=null)`.
  - Idempotente: re-rodar não duplica (upsert por chave natural + flag `migrated_to_content_entries=true` no LO).
  - Registrar auditoria da migração (coleção `audit_logs` + log de migração).
  - Validação pós-migração: contagem LO migrados == CE com `legacy_id` correspondente; sem perda de campos.

### P1.2 — Adapter de compatibilidade (write-through)
- Objetivo: o professor continua na MESMA tela (`LearningObjects.js`), mas a escrita vai p/ `content_entries`.
- Implementação recomendada: **adapter no backend** — manter os endpoints `/api/learning-objects`
  (POST/PUT/DELETE) porém redirecionando a escrita para `save_content_canonical` (traduzindo campos),
  e a leitura para `content_entries` (com o bridge read-only cobrindo legados ainda não migrados).
  → zero mudança de UI no curto prazo; troca de motor por baixo.
- Alternativa: trocar `learningObjectsAPI` no frontend para chamar `/content-entries`. Mais invasivo na UI.
- Decisão de implementação: **adapter backend** (menos risco operacional).

### P1.3 — Offline de Conteúdo (núcleo, padrão Frequência)
- IndexedDB: **reusar `syncQueue`** (fila genérica) com `collection='content_entries'` + `naturalKey`.
  Nova store de leitura `content_local` (espelho p/ exibir offline), keyed por naturalKey.
- `addToSyncQueue('content_entries', UPSERT, 'nk:<chave>', payload, naturalKey)` → idempotência (Cenário D: 5 edições = 1 item).
- Backend: `routers/sync.py::_sync_content_canonical` chama `save_content_canonical` (NUNCA insert cru).
- **P0 dentro da P1 — Lock de bimestre no sync:** se o bimestre/ano fechou enquanto offline, o sync NÃO
  perde nem sobrescreve. O motor canônico levanta o lock → o item recebe `status="rejected"` com
  `reason="Bimestre encerrado em dd/mm/aaaa. Lançamento não pode ser sincronizado."` e fica visível no Painel.
  (Implica estender `SyncPushResult`/fila para carregar `rejected` + motivo, distinto de `failed` por erro técnico.)

### P1.4 — Pré-cache automático
- Ao abrir a turma ONLINE, pré-carregar (≤30 dias): alunos, horários, calendário (datas/bimestres p/ avaliar
  locks offline de forma informativa), frequências e **conteúdos recentes**. Sem ação manual.

### P1.5 — Painel de sincronização (elevado a P1 pelos arquitetos)
- Estados por item: **Salvo no aparelho → Aguardando envio → Sincronizado**; e **Rejeitado** (com motivo).
- Ações: "Enviar agora", "Ver detalhes". Contador "X lançamentos aguardando envio".
- Fonte: `syncQueue` (pending/failed/rejected) — genérico p/ frequência E conteúdo.

### P1.6 — Desativação definitiva do `learning_objects`
- Após 100% migrado + adapter estável + janela de homologação: remover escrita em LO, manter leitura via bridge
  por período de segurança, depois descomissionar endpoints LO.

---

## Critérios de aceite (P1.4 dos arquitetos) — validação por pytest + E2E offline
- A) Online → registra → persistido em `content_entries`.
- B) Offline → registra → salvo localmente (`syncQueue` + `content_local`).
- C) Offline → fecha/reabre → conteúdo permanece.
- D) Offline → edita 5x → **1 item** na fila (estado final).
- E) Reconecta → sync idempotente (sem duplicação/perda). **Lock de bimestre → item `rejected` com motivo no Painel.**

## Reuso integral do padrão aprovado na Frequência
`motor canônico único` + `fila genérica syncQueue` + `chave natural` + `idempotência` + `versionamento` +
`auditoria` + `validação de locks server-side no sync`.

---
**Status:** BLUEPRINT pronto. Implementação aguardando confirmação de **homologação da Fase A em produção**.

---

## ✅ P1.0 (A–D) IMPLEMENTADO E VALIDADO (Jun/2026) — migração (E) e offline AINDA pendentes de homologação da Fase A

Decisões dos arquitetos aplicadas (BNCC redesenhado/não migrado; `resources` descartado;
`teacher_id` via derivação + fallback `teacher_unknown`; só 13 reais na migração; `created_at` Date nativo).

- **P1.0-A — Schema estendido** (`routers/content_entries.py::ContentEntryCreate` + doc):
  adicionados `academic_year`, `number_of_classes`, `teacher_unknown`, `mantenedora_id`;
  timestamps `created_at`/`updated_at` agora **Date nativo** (ISO só na serialização da API).
  **SEM** `resources`/`skill_codigos`/`adaptation_ids`/`evidencia_aprendizagem` (descartados).
- **P1.0-B — Motor canônico único** `save_content_canonical()` (espelho de `save_attendance_canonical`):
  **UPSERT por chave natural** `(class_id, component_id, teacher_id, date, aula_numero)` → idempotente
  (reenviar não duplica; N edições convergem). `POST /content-entries` agora roteia por ele.
- **P1.0-C — Locks de calendário portados** (única autoridade no motor): `ano letivo aberto`
  (`verify_academic_year_open_or_raise`) + `prazo de edição do bimestre`
  (`verify_bimestre_edit_deadline_or_raise`) via `utils/academic_year.create_academic_year_validators`.
- **P1.0-D — Testes** `tests/test_content_canonical.py` (5/5): conteúdo válido, ano fechado (403),
  bimestre encerrado (403), optimistic locking (409 + force overwrite + idempotência), multi-tenant
  (mantenedora derivada da turma, não do header). Suíte de conteúdo+freq+sync: **34/34 verdes**.
  (Teste legado `test_unique_constraint_blocks_duplicate...` atualizado para o novo contrato de upsert idempotente.)

**Pendente (após homologação da Fase A em produção):** P1.0-E migração dos 13 reais (script idempotente
com derivação de `teacher_id` + `teacher_unknown`), P1.2 adapter write-through `/api/learning-objects`,
P1.3 offline de conteúdo (sync canônico + `rejected` por lock), P1.4 pré-cache, P1.5 painel, P1.6 desativação.
