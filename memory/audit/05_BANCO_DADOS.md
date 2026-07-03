# ENTREGA 05 — Banco de Dados

> Auditoria READ-ONLY · Jun/2026 · MongoDB 7 (Motor async). **102 coleções**
> referenciadas no código, **~190 índices** criados. Classificação 🟢🟡🔴⚫.

## 1. Visão geral
- **SGBD:** MongoDB 7 (documentos JSON), acesso 100% assíncrono via **Motor 3.3.1**.
- **Modelagem:** orientada a documentos, com **UUID string** em `id` (não usa `_id`/ObjectId
  no contrato de API — regra do projeto para evitar `ResponseValidationError`).
- **Isolamento multi-tenant:** quase toda coleção carrega `mantenedora_id`; o filtro é
  injetado por `tenant_scope.apply_tenant_filter` (**fail-closed**).
- **Índices:** centralizados em `backend/startup/indexes.py` (329 linhas) + criações
  pontuais em routers/scripts. Padrão: `id` único em todas; índices compostos por
  `(student_id, academic_year)`, `(class_id, course_id, academic_year)`, etc.

## 2. Entidades núcleo (core do domínio) — 🟢
| Coleção | Papel | Índices-chave | Refs no código |
|---|---|---|---|
| `students` | aluno (dados demográficos, status, série) | `id`✦, `cpf`(sparse), `school_id`, `class_id`, `(status,school_id)` | 173 |
| `classes` | turma (nível, multisseriada, grade_level, school_history) | `id`✦ | 158 |
| `schools` | escola | `id`✦ | 115 |
| `enrollments` | matrícula (vínculo aluno↔turma↔ano) | `id`✦, `(student_id,academic_year)`, `school_id`, `uq_enrollment_number`(partial) | 108 |
| `users` | contas/credenciais | `id`✦, `email`✦ | 92 |
| `attendance` | frequência | `id`✦, `(class_id,date)`, `(class_id,academic_year)`, únicos por aluno/data/componente | 82 |
| `staff` | servidores | `id`✦ | 73 |
| `courses` | componentes curriculares | `id`✦ | 73 |
| `grades` | notas por bimestre | `id`✦, `(student_id,academic_year)`, `(class_id,course_id,academic_year)` | 63 |
| `mantenedoras` | tenants (fonte definitiva) | `id`✦ | 47 |

✦ = índice único em `id`.

## 3. Grupos temáticos de coleções (102 no total)
- **Acadêmico/pedagógico:** `grades`, `attendance`, `attendance_settings`,
  `content_entries`, `learning_objects`, `diary_snapshots`, `snapshots`,
  `snapshot_retention_policies`, `calendario_letivo`, `calendar_events`,
  `academic_events`, `academic_event_audit`.
- **Currículo/BNCC:** `curriculum_components`, `curriculum_skills`,
  `curriculum_adaptations`, `curriculum_adaptation_methods`, `curriculum_methods`,
  `curriculum_coverage_stats`, `curriculum_import_batches`, `bncc_skills`.
- **Grade/alocação:** `class_schedules`(legado), `teacher_assignments`,
  `teacher_class_assignments`, `teacher_allocations`, `school_assignments`.
- **Matrícula/aluno:** `enrollments`, `enrollment_counters`, `student_history`,
  `student_dependencies`, `dependency_completions`, `pre_matriculas`,
  `class_students`, `guardians`.
- **Documentos/verificação:** `verifiable_documents`, `document_files`,
  `document_render_jobs`, `render_jobs`, `school_documents_log`,
  `bulletin_verifications`, `history_verifications`, `promotion_books`,
  `promotion_book_counters`, `medical_certificates`.
- **AEE ⛔:** `planos_aee`, `planos_aee_templates`, `atendimentos_aee`,
  `articulacoes_aee`, `evolucoes_aee`.
- **Risco/IA/alertas:** `alert_rules`, `alerts`, `student_alerts`,
  `intervention_alerts`, `intervention_notifications`, `student_risk_scores`,
  `ai_risk_analyses`, `ai_plans`, `ai_analysis_snapshots`, `student_diagnostics`,
  `student_snapshots`, `sie_config`, `pmpi_cron_log`, `action_plans`, `monthly_goals`.
- **Programas sociais/saúde:** `bolsa_familia_tracking`, `bf_network_stats_snapshots`,
  `vaccine_status`.
- **RH/folha:** `school_payrolls`, `payroll_items`, `payroll_occurrences`,
  `payroll_competencies`, `hr_audit_logs`.
- **Multi-tenant/branding:** `mantenedoras`, `tenant_branding`, `tenant_domains`,
  `tenant_security_events`, `user_profiles`, `permission_overrides`.
- **Comunicação:** `messages`, `message_logs`, `announcements`,
  `announcement_reads`, `connections`.
- **Auditoria/migração:** `audit_logs`, `school_transfer_audit`,
  `history_reconstruction_audit`, `mec_integration`, `sync_telemetry`,
  `grade_integrity_issue_states`, `*_runs`/`*_locks`/`*_idempotency` (mutações críticas).
- **Analytics:** `monthly_reports`, `pme_external_indicators`, `curriculum_coverage_stats`.

## 4. Relacionamentos (chaves lógicas, sem FK física)
```
mantenedoras (1) ──< schools ──< classes ──< enrollments >── students
classes ──< teacher_class_assignments >── staff (professor)
classes ──< grades / attendance / content_entries / diary_snapshots
courses (componentes) ──< grades / teacher_assignments / curriculum_*
students ──< student_history / student_dependencies / planos_aee / bolsa_familia_tracking
users ──(1:1 lógico)── staff | students (portal) via user_id/email
```
Junções feitas em application-layer (aggregate/`$lookup` pontual). Não há transações
distribuídas de longo alcance exceto nos motores canônicos (transfer/reconstruction),
que usam snapshot + idempotência + rollback próprios.

## 5. Redundâncias e riscos observados (🔴/⚫ — detalhe na Onda 2)
- ⚫ **`mantenedora` (singular)** — legado da coleção plural `mantenedoras`. Confirmar remoção.
- 🔴 **Grade horária duplicada:** `class_schedules` (legado) × `teacher_class_assignments`
  (novo) + `teacher_allocations` — três representações de "quem leciona o quê". Migração
  concluída em prod, mas as três coleções coexistem (dual-read/bridge).
- 🟡 **`class_students`** × `enrollments` × `students.class_id` — três formas de expressar
  o vínculo aluno↔turma; fonte de bugs históricos (fallback multisseriada, livro de promoção).
- 🟡 **`snapshots`** × `diary_snapshots` × `student_snapshots` × `ai_analysis_snapshots` —
  múltiplos padrões de snapshot; validar convergência de estratégia.
- 🟡 **`render_jobs`** × `document_render_jobs` — dois registros de jobs de renderização.
- 🟡 **Status legado:** `enrollments.status='inactive'` fora do `Literal` do modelo já
  causou 500 (corrigido com `field_validator` de coerção em Jun/2026). Recomenda-se
  **migração de dados** para saneamento dos valores legados.

## 6. Recomendações
1. Consolidar a representação de "vínculo aluno↔turma" numa fonte única (enrollments) com view derivada.
2. Concluir a **remoção controlada** do legado de grade horária (`class_schedules`) pós-observação.
3. Padronizar snapshots numa estratégia única com política de retenção.
4. Auditar/normalizar valores de `status` legados (matrículas/alunos) via `with_critical_mutation`.
5. Documentar em cada modelo Pydantic os `field_validator` de tolerância a legado (evitar 500 silenciosos).

> Este documento é macro (Onda 1). O detalhamento por-coleção com contagem de
> documentos em produção depende de acesso ao banco de produção e será
> aprofundado se solicitado.
