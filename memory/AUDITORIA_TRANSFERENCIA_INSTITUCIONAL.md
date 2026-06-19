# RELATÓRIO TÉCNICO — Transferência Institucional de Turmas (Dissolução de Escola)
> **Read-only. Nada implementado.** Entregável para aprovação antes de qualquer código.
> Base: auditoria real do backend SIGESC (FastAPI + MongoDB/motor), Jun/2026.

---

## 0. Achados estruturais que governam toda a decisão

1. **Fonte da verdade turma→escola = `classes.school_id`.** Toda a árvore pedagógica
   (frequência, notas, conteúdos, etc.) referencia a turma por **`class_id`** (UUID estável).
2. **Denormalização ampla de `school_id`.** Além de `classes`, MUITAS coleções gravam uma
   **cópia** de `school_id` no momento da escrita (lookup na turma): `students`, `enrollments`,
   `attendance`, `grades`, `content_entries`, `teacher_class_assignments`, `student_dependencies`,
   `planos_aee`, `atendimentos_aee`, `bolsa_familia_tracking`, etc. ⇒ Mudar só `classes.school_id`
   deixa essas cópias **defasadas**.
   - ⚠️ Nuance real (analytics.py:206): **`attendance.school_id` costuma estar AUSENTE em dados legados** —
     o analytics resolve frequência **por turma** (busca classes da escola → filtra attendance por `class_id`).
3. **Índices ÚNICOS NÃO contêm `school_id`.** As chaves naturais usam `class_id`/`student_id`/`course_id`:
   - `enrollments` unique = `[student_id, class_id, academic_year]` (partial status=active)
   - `attendance` unique = `[class_id, date, course_id, aula_numero]`
   - `content_entries` unique = `[class_id, component_id, teacher_id, date, aula_numero]` (partial deleted=false)
   ⇒ **Mudar `school_id` NÃO colide com nenhum índice único.** (Fator decisivo a favor da Opção A.)
4. **Mecanismo de movimentação JÁ existe:** coleção `academic_events`
   (`event_type ∈ {transfer, remanejamento, reclassificacao, progressao_parcial}`) com
   `origin_class_id/destination_class_id` e `origin_school_id/destination_school_id`. A nova
   funcionalidade deve REUTILIZAR esse padrão de auditoria (ou espelhá-lo).
5. **Isolamento multi-tenant** por `mantenedora_id` em quase tudo. ⇒ Transferência **deve ser
   intra-mantenedora** (origem e destino na mesma rede). Cross-tenant é projeto separado.
6. **Documentos emitidos são IMUTÁVEIS** (`verifiable_documents`, `document_render_jobs`,
   `history_pdf`, `bulletins`, `diary_snapshots`): são registros legais/verificáveis assinados,
   referenciando a escola **no momento da emissão**. **NÃO podem ser reescritos** pela transferência.

---

## FASE 1 — Matriz de Impacto

Legenda do vínculo: **D** = grava `school_id` direto (denormalizado) · **I** = indireto (via `class_id`/`student_id`) · **H** = histórico imutável.

| Coleção | Vínculo escola | Campo(s) | Índice único relevante | Ação na transferência | Impacto |
|---|---|---|---|---|---|
| **schools** | entidade | `id`, `mantenedora_id`, `status` | `id` unique | origem → marcar `status` (encerrada); destino intacto | Crítico |
| **classes** | **D (fonte)** | `school_id`, `academic_year`, `course_ids` | `id` unique; `[school_id, year]` (não único) | **UPDATE `school_id`** (mantém `id`) | **Crítico** |
| **students** | D | `school_id`, `class_id` | `id` unique; `[status, school_id]` | UPDATE `school_id` dos alunos das turmas movidas | **Crítico** |
| **enrollments** | D | `school_id`, `class_id`, `student_id`, `academic_year` | unique `[student_id, class_id, year]` (active) | UPDATE `school_id` (class_id estável → sem colisão) | **Crítico** |
| **attendance** | D (legado ausente) + I | `class_id`, `school_id?`, `course_id`, `date`, `aula_numero` | unique `[class_id,date,course_id,aula]` | UPDATE `school_id` onde existir; class_id estável | **Crítico** |
| **grades** | D + I | `class_id`, `student_id`, `school_id`, `course_id`, `academic_year` | unique `id`; `[class_id,course_id,year]` | UPDATE `school_id` | **Crítico** |
| **content_entries** | D + I | `class_id`, `component_id`, `teacher_id`, `school_id`, `date` | unique `[class_id,component_id,teacher_id,date,aula]` | UPDATE `school_id` | **Crítico** |
| **learning_objects** (legado) | I | `class_id`, `course_id`, `academic_year` | `[class_id,year,date]` | nada (segue via class_id) | Médio |
| **teacher_class_assignments** | D | `school_id`, `class_id`, `component_id`, `valid_*` | `id`; `[school_id,valid_*,deleted]` | UPDATE `school_id`; revalidar lotação no destino | Alto |
| **teacher_assignments** | I | `class_id`, `course_id`, `staff_id` | `[class_id,course_id]` | nada (via class_id); conferir vínculo do prof. | Médio |
| **school_assignments** (lotação servidor) | D | `school_id`, `staff_id`, `academic_year` | `[school_id,year]` | **NÃO mover automaticamente** (servidor é lotado na escola, não na turma) — decisão de RH | Alto |
| **student_dependencies** | D | `school_id`, `class_id`, `course_id`, `student_id` | unique `[student_id,course_id,origin_year]` (active) | UPDATE `school_id` | Alto |
| **planos_aee / atendimentos_aee / evolucoes_aee / articulacoes_aee** | D | `school_id`, `student_id` | `id` | UPDATE `school_id` dos alunos movidos | Alto |
| **bolsa_familia_tracking** | D | `school_id`, `student_id`, `academic_year`, `month` | `[school_id,year,month,student_id]` | UPDATE `school_id` | Alto |
| **calendario_letivo** | D | `school_id`, `ano_letivo` | `[ano_letivo, school_id]` | **NÃO mover** — é da ESCOLA. Destino precisa ter ano/bimestre abertos compatíveis (trava de escrita do diário) | **Crítico (bloqueante)** |
| **calendar_events / academic_events** | D | `school_id` / `origin_*`, `destination_*` | vários | academic_events: **manter histórico**; gerar evento institucional | Alto |
| **action_plans / alerts / alert_rules / monthly_goals / monthly_reports** | D | `school_id` | `[school_id,...]`, `monthly_goals` unique `[mid,month,school_id]` | UPDATE `school_id` (ou recalcular) | Médio |
| **school_payrolls / payroll_items / payroll_occurrences** | D | `school_id` | unique `[competency_id, school_id]` | **NÃO mover** (folha é da escola/competência) — decisão de RH | Alto |
| **verifiable_documents / document_render_jobs / history_pdf / bulletins / diary_snapshots** | **H** | `school_id` no snapshot | idempotency_key | **NÃO ALTERAR** (registro legal imutável) | **Crítico (compliance)** |
| **student_history** | D/H | entradas com escola | — | acrescentar evento "transferência institucional"; não reescrever passado | Alto |
| **class_schedules** | I | `class_id` | — | nada (via class_id) | Baixo |
| **pre_matriculas** | D | `school_id` | — | decisão: mover pendentes? (provável NÃO) | Baixo |
| **announcements / messages** | D/escopo | `school_id` | — | decisão de produto | Baixo |
| **ai_analysis_snapshots / intervention_alerts / student_risk_scores / sie** | D/I | `school_id`/`student_id`/`class_id` | — | recalcular/UPDATE school_id (derivados) | Médio |
| **vaccine_status / medical_certificates** | I (student) | `student_id` | — | seguem o aluno | Baixo |
| **users** (diretores/coord./prof.) | D (acesso) | `school_ids` / `school_links` | `id`, `email` unique | **NÃO mover automaticamente** — revisar acessos da escola encerrada | Alto |
| **audit_logs** | H | `extra_data.class_id`, `extra_data.school_id` | vários | **NÃO reescrever** (trilha histórica) | Crítico (compliance) |
| **tenant_domains / mantenedoras** | — | — | — | sem impacto | Nenhum |

**Resumo das dependências:**
- **Diretas (precisam UPDATE de `school_id`):** classes, students, enrollments, attendance, grades, content_entries, teacher_class_assignments, student_dependencies, planos/atendimentos/evolucoes/articulacoes_aee, bolsa_familia_tracking, (action_plans/alerts/monthly_* — derivados).
- **Indiretas (seguem sozinhas via `class_id`/`student_id`):** learning_objects, teacher_assignments, class_schedules, medical_certificates, vaccine_status.
- **NÃO mover (são da ESCOLA, não da turma):** calendario_letivo, school_assignments (lotação), school_payrolls/folha, users.school_ids.
- **Imutáveis (compliance):** verifiable_documents, document_render_jobs, history/bulletin PDFs, diary_snapshots, audit_logs.
- **Índices únicos afetados:** NENHUM contém `school_id` ⇒ **transferência por re-homing não gera colisão de unicidade.**

---

## FASE 2 — Parecer: Opção A vs Opção B

### Opção A — Re-homing (UPDATE `school_id`, mantém `class_id`)
- ✅ Mantém `class_id` ⇒ **todas** as referências indiretas continuam válidas automaticamente.
- ✅ **Zero colisão** de índices únicos (nenhum usa `school_id`).
- ✅ Sem duplicação; idempotente; reversível por flip de campo + snapshot.
- ✅ Preserva `academic_events`, `audit_logs.extra_data.class_id`, snapshots de PDF (apontam para `class_id`).
- ⚠️ Precisa atualizar TODAS as cópias denormalizadas de `school_id` (senão analytics/isolamento ficam inconsistentes).
- ⚠️ "Histórico institucional muda": a turma passa a 'pertencer' ao destino também no passado — **mitigado** registrando `origin_school_id`/data no `school_transfer_audit` + `school_id_history[]` na turma.

### Opção B — Encerrar turma + recriar no destino (novos `class_id`)
- ✅ Histórico institucional "puro" (turma origem permanece encerrada).
- ❌ **Reescrita massiva**: re-apontar `class_id` em attendance, grades, content_entries, enrollments, teacher_*, snapshots → altíssimo volume e risco.
- ❌ **Risco de colisão/duplicidade** nos índices únicos compostos por `class_id` ao recriar.
- ❌ Quebra referências de `academic_events` (origin/destination_class_id) e `audit_logs`.
- ❌ Snapshots/documentos emitidos apontam para `class_id` antigo → inconsistência de verificação.
- ❌ Complexidade e superfície de erro ~5–10×.

### Adequação por contexto
| Critério | Opção A (Re-homing) | Opção B (Recriar) |
|---|---|---|
| Rede municipal (operacional) | ✅ Simples, sem perda | ❌ Complexo |
| Censo Escolar | ✅ desde que se registre `origin_school_id` + data (reconstruível) | ✅ histórico físico, mas frágil tecnicamente |
| Prestação de contas | ✅ com audit imutável | ⚠️ depende de re-link íntegro |
| Auditoria | ✅ trilha clara (audit + history[]) | ❌ múltiplas entidades novas |
| Risco de perda de dados | **Baixo** | **Alto** |

---

## FASE — Estratégia RECOMENDADA

> **Opção A (Re-homing institucional)** — mudar `school_id` mantendo `class_id`, atualizando
> TODAS as cópias denormalizadas, **preservando documentos/auditorias imutáveis**, e registrando
> proveniência (`origin_school_id` + data) para reconstrução histórica/censo.

Princípios (alinhados ao "motor canônico único" do projeto):
1. **Intra-mantenedora apenas** (validar `origin.mantenedora_id == destination.mantenedora_id`).
2. **Motor único + idempotência por chave natural** (reaplicar a transferência não duplica nada).
3. **Não tocar** em coleções imutáveis nem em `calendario_letivo`/folha/lotação/usuários.
4. **Pré-requisito bloqueante:** ano letivo/bimestre do destino compatível (senão diário trava).
5. **Proveniência:** `classes.school_id_history[] = [{from, to, at, by, protocol}]` + `school_transfer_audit`.

---

## PLANO DE MIGRAÇÃO (sequência por transação/lote idempotente)

1. **Pré-checagem (Dry Run obrigatório):** contagem de registros afetados por coleção; conflitos;
   professores sem vínculo no destino; ano letivo do destino aberto?; turmas incompatíveis (série/curso).
2. **Lock + janela:** marcar turmas em `transfer_in_progress` (bloqueio de escrita do diário durante a operação).
3. **Snapshot/backup** (pré-transferência) — export JSON de `{coleção, id, school_id_antigo}` de todos os docs afetados → guardado no `school_transfer_audit`.
4. **UPDATE em lote (ordem):** classes → students → enrollments → attendance → grades → content_entries →
   student_dependencies → teacher_class_assignments → planos/atendimentos_aee → bolsa_familia_tracking →
   derivados (alerts/action_plans/monthly_*).
5. **Proveniência:** gravar `school_id_history[]` nas turmas; criar `academic_events` (event_type
   `transferencia_institucional`) por turma; criar registro em `school_transfer_audit`.
6. **Pós-validação:** revalidar contagens (origem zera; destino soma); verificar órfãos; liberar lock.
7. **Escola origem:** `status = "encerrada"` (sem deletar — preserva histórico e documentos).

---

## ESTRATÉGIA DE ROLLBACK

- **É possível?** Sim, **dentro de uma janela**, porque Option A só inverte `school_id` (class_id estável).
- **Como:** o `school_transfer_audit` guarda o snapshot `{coleção, id, school_id_antigo}` → rollback
  reaplica os valores antigos + remove o último item de `school_id_history[]` + reabre a escola origem.
- **Reversível:** classes, students, enrollments, attendance, grades, content_entries, dependencies,
  AEE, BF, derivados.
- **NÃO reversível / cuidado:**
  - Documentos emitidos **após** a transferência sob a escola destino (verifiable_documents/PDF) — não reescrever.
  - `audit_logs` e `academic_events` — são append-only (rollback gera NOVO evento de reversão, não apaga).
  - Lançamentos de diário feitos **no destino após** a transferência (decidir: manter no destino).
- **Janela recomendada:** rollback "1 clique" até X dias / até a primeira emissão de documento no destino;
  depois disso, só rollback parcial assistido.
- **Garantia mínima:** **export JSON pré-transferência** sempre gerado e baixável (mesmo que o rollback in-app expire).

---

## FASE — Segurança da operação
- Exclusiva `super_admin` (validar role no backend, não só na UI).
- **Re-autenticação** (senha) imediatamente antes de executar.
- **Justificativa obrigatória** (ex.: "Extinção da unidade escolar").
- **Protocolo** único + **log de auditoria** (`school_transfer_audit` + `audit_logs`).
- Idempotência: `idempotency_key` por operação (evita reexecução dupla).

### `school_transfer_audit` (proposto)
```json
{
  "id": "uuid",
  "protocol": "TRANSF-2026-000123",
  "mantenedora_id": "...",
  "origin_school_id": "...",
  "destination_school_id": "...",
  "class_ids": ["..."],
  "counts": {"students": 58, "attendance": 7821, "grades": 2104, "content_entries": 194, "aee": 22},
  "snapshot_ref": "gridfs/export-id ou inline",
  "reason": "Extinção da unidade escolar",
  "executed_by": "user_id",
  "executed_at": "ISO8601",
  "status": "executed|rolled_back",
  "dry_run_report": { ... }
}
```

---

## RISCOS IDENTIFICADOS (priorizados)
1. 🔴 **Defasagem de `school_id` denormalizado** se não atualizarmos TODAS as coleções D → analytics/isolamento inconsistentes. (Mitigar: lista canônica de coleções + validação pós.)
2. 🔴 **`calendario_letivo` é da escola** — diário do destino pode TRAVAR se ano/bimestre não abertos. (Pré-checagem bloqueante.)
3. 🔴 **Compliance**: não alterar documentos emitidos/auditorias/snapshots.
4. 🟠 **Lotação de servidores / acessos de usuários** (school_assignments, users.school_ids) NÃO seguem a turma — exigem decisão de RH/acesso separada.
5. 🟠 **Escrita concorrente** durante a operação (professor lançando diário) → lock + janela.
6. 🟠 **Falha parcial** no meio do lote → operação idempotente + snapshot + status `transfer_in_progress`.
7. 🟡 **Censo/série incompatível** (turma 5º ano indo para escola que não oferta a etapa) → validação no Dry Run.
8. 🟡 **Cross-tenant** acidental → bloquear (mesma mantenedora obrigatória).

---

## Próximo passo
Aguardando aprovação da estratégia (Opção A) e das decisões em aberto:
- Mover ou não: lotação de servidores, folha, acessos de usuários, pré-matrículas.
- Janela de rollback "1 clique" (em dias) e gatilho de expiração (1ª emissão de documento no destino?).
- Tratar `calendario_letivo` do destino: exigir ano/bimestre abertos como pré-requisito.
