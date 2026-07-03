# ENTREGA 02 — Inventário Completo do Sistema (Módulos)

> Auditoria READ-ONLY · Jun/2026. Agrupamento funcional dos **89 routers** +
> **77 páginas** em **~29 módulos de domínio**. Classificação 🟢🟡🔴⚫.
> Para cada módulo: maturidade, complexidade, acoplamento, risco de alteração,
> potencial de expansão e nota de BI.

**Legenda de atributos:** Complexidade/Acoplamento/Risco = Baixo · Médio · Alto.

---

## 1. Autenticação, Sessão & Assinatura — 🟢
- **Objetivo:** login, refresh rotativo, JWT em cookie HttpOnly, revogação, assinatura digital do usuário.
- **Backend:** `auth.py`, `auth_middleware.py`, `auth_utils.py`, `user_signature.py`.
- **Frontend:** `Login.js`, `UserProfile.js`, `contexts/AuthContext.js`, `services/sessionToken.js`.
- **APIs:** `/api/auth/*` (login, refresh, me, logout, register), `/api/user-signature/*`.
- **Coleções:** `users`, `user_terms`, `email_change_requests`.
- **Maturidade:** alta · Complexidade: alta · Acoplamento: alto (base de tudo) · Risco: **alto** · Expansão: média.
- **Obs.:** múltiplos P0 já resolvidos (isolamento no refresh, sessão offline). **BI:** identidade/atividade de usuários online.

## 2. Multi-Tenancy & Branding — 🟢
- **Objetivo:** isolamento por mantenedora (RLS), troca de contexto, branding/domínios por tenant.
- **Backend:** `mantenedoras.py`, `mantenedora.py`, `tenant_admin.py`, `tenant_scope.py`, `tenant_audit.py`.
- **Frontend:** `Mantenedoras.jsx`, `Mantenedora.js`, `TenantAdmin.jsx`, `contexts/MantenedoraContext.js`, `BrandingContext.js`, `useTenantBranding.js`.
- **Coleções:** `mantenedoras`, `tenant_branding`, `tenant_domains`, `tenant_security_events`.
- **Maturidade:** alta · Complexidade: alta · Acoplamento: alto · Risco: **alto** (segurança) · Expansão: média.
- **Obs.:** existe coleção legada `mantenedora` (singular) — ver [17](17_CODIGO_OBSOLETO.md).

## 3. Escolas — 🟢
- **Backend:** `schools.py`. **Frontend:** `Schools.js`, `SchoolsComplete.js`, `useSchools.js`, `useSchoolForm.js`, `useSchoolStaff.js`.
- **Coleções:** `schools`, `school_assignments`.
- **Complexidade:** média · Acoplamento: alto · Risco: médio · Expansão: alta. **BI:** dimensão geográfica/rede.

## 4. Turmas & Grade Horária — 🟡
- **Objetivo:** turmas (multisseriadas), horário de aulas, alocação de professores.
- **Backend:** `classes.py`, `class_details.py`, `class_schedule.py`, `teacher_class_assignments.py`, `assignments.py`.
- **Services:** `legacy_schedule_bridge.py`, `class_teachers.py`, `grade_legacy_migration_service.py`.
- **Frontend:** `Classes.js`, `teacherAssignmentAPI`, `classScheduleAPI`.
- **Coleções:** `classes`, `class_schedules` (legado), `teacher_assignments`, `teacher_class_assignments`, `teacher_allocations`.
- **Maturidade:** média · Complexidade: **alta** · Acoplamento: alto · Risco: alto · Expansão: média.
- **Débito conhecido:** anti-pattern **WRITE≠READ** (grava em `class_schedules` legado, lê no modelo novo) — migração concluída em prod, mas dual-read/bridges permanecem. Ver [16](16_CODIGO_DUPLICADO.md)/[17](17_CODIGO_OBSOLETO.md).

## 5. Alunos, Matrículas & Responsáveis — 🟢🟡
- **Backend:** `students.py`, `enrollments.py`, `guardians.py`, `student_history.py`, `pre_matricula.py`, `dedup_enrollments.py`, `student_series_backfill.py`.
- **Frontend:** `Students.js`, `StudentsComplete.js` (>3800 linhas — dívida), `Enrollments.js`, `Guardians.js`, `StudentHistory.js`, `PreMatricula.jsx`, `PreMatriculaManagement.jsx`, `EnrollmentAudit.jsx`.
- **Coleções:** `students`, `enrollments`, `enrollment_counters`, `guardians`, `student_history`, `pre_matriculas`, `class_students`.
- **Complexidade:** **alta** · Acoplamento: **alto** (núcleo) · Risco: **alto** · Expansão: alta.
- **Obs.:** canonicalização de série (`serie_canonical`), saneamento de duplicadas (padrão `with_critical_mutation`). **BI:** matrícula/rede, distorção idade-série, cor/raça (usar `color_race`).

## 6. Servidores/RH & Folha — 🟡
- **Backend:** `staff.py`, `hr.py`, `assignments.py`, `hr_pdf_generator.py`.
- **Frontend:** `Staff.js`, `HRPayroll.js`, `useStaff.js`, `useSchoolStaff.js`.
- **Coleções:** `staff`, `school_payrolls`, `payroll_items`, `payroll_occurrences`, `payroll_competencies`, `hr_audit_logs`.
- **Complexidade:** alta · Acoplamento: médio · Risco: alto (financeiro) · Expansão: **alta**. **BI:** custo de pessoal por escola/rede.

## 7. Componentes Curriculares, Currículo & BNCC — 🟡
- **Backend:** `courses.py`, `curriculum.py`, `curriculum_v2.py`, `curriculum_import.py`.
- **Services:** `curriculum_extractor.py`, `curriculum_v2_migration.py`.
- **Frontend:** `Courses.js`, `CoursesNew.js`, `CurriculumAdaptations.jsx`, `CurriculumCoverage.jsx`, `CurriculumImport.jsx`.
- **Coleções:** `courses`, `curriculum_components`, `curriculum_skills`, `curriculum_adaptations`, `curriculum_adaptation_methods`, `curriculum_methods`, `curriculum_coverage_stats`, `curriculum_import_batches`, `bncc_skills`.
- **Complexidade:** alta · Acoplamento: médio · Risco: médio · Expansão: **alta** (BNCC + IA — tarefa futura). **BI:** cobertura curricular.

## 8. Notas & Cálculo — 🟢
- **Backend:** `grades.py`, `grade_calculator.py`, `closure.py`. **Frontend:** `Grades.js`, `components/grades/*`, `GradesContext.js`, `useOfflineGrades.js`.
- **Coleções:** `grades`, `grade_integrity_issue_states`.
- **Complexidade:** alta · Acoplamento: alto · Risco: alto · Expansão: média.
- **Obs.:** congelamento granular (bimestral) pós-movimentação; conceitual vs numérico; offline autosave. **BI:** rendimento/aprovação.

## 9. Frequência — 🟢
- **Backend:** `attendance.py`, `attendance_ext.py`. **Services:** `attendance_utils.py`, `attendance_audit_diary.py`.
- **Frontend:** `Attendance.js`, `AttendanceContext.js`, `useOfflineAttendance.js`.
- **Coleções:** `attendance`, `attendance_settings`, `attendance_frequency_reasons`, `attendance_frequency_reason_groups`.
- **Complexidade:** alta · Acoplamento: alto · Risco: alto · Expansão: média.
- **Obs.:** sábado letivo (rotação), consolidação diária ≥50%, datas futuras configuráveis. **BI:** infrequência/busca ativa.

## 10. Diário de Classe, Conteúdos & Snapshots — 🟢🟡
- **Backend:** `diary.py`, `diary_snapshots.py`, `calendar_diary_state.py`, `diary_dashboard.py`, `content_entries.py`, `learning_objects.py`, `admin_diary_diagnose.py`.
- **Services:** `diary_snapshot_service.py`, `diary_pdf_handler.py`, `diary_matching_mode.py`, `legacy_content_bridge.py`, `snapshot_service.py`, `snapshot_pdf.py`.
- **Frontend:** `DiaryCalendar.jsx`, `DiaryDashboard.js`, `LearningObjects.js`, `VerifyDiarySnapshot.jsx`.
- **Coleções:** `diary_snapshots`, `content_entries`, `snapshots`, `snapshot_retention_policies`.
- **Complexidade:** **alta** · Acoplamento: alto · Risco: alto · Expansão: média. **BI:** cumprimento de diário/conteúdo.

## 11. Calendário Letivo & Eventos — 🟢
- **Backend:** `calendar.py`, `calendar_ext.py`, `academic_events.py`. **Service:** `school_calendar_helper.py`.
- **Frontend:** `Calendar.js`, `Events.js`, `useCalendarioLetivo.js`.
- **Coleções:** `calendario_letivo`, `calendar_events`, `academic_events`, `academic_event_audit`.
- **Complexidade:** média · Acoplamento: alto (dias letivos alimentam frequência/diário) · Risco: médio.

## 12. Documentos Oficiais, PDFs & Verificação Pública — 🟢
- **Backend:** `documents.py`, `bulletins.py`, `bulletin_pdf.py`, `history_pdf.py`, `school_documents.py`, `render_jobs.py`, `verifiable_docs.py`, `public_verify.py`, `medical_certificates.py`, dir `pdf/`.
- **Services:** `bulletin_renderer.py`, `history_renderer.py`, `school_docs_service.py`, `school_doc_templates.py`, `document_files.py`, `verifiable_docs_service.py`, `render_worker.py`.
- **Frontend:** `SchoolDocuments.jsx`, `BulletinViewer.jsx`, `DocumentValidator.jsx`, `VerifyBulletin.jsx`, `VerifyPublic.jsx`, `VerifyHistory.jsx`, `Promotion.jsx`.
- **Coleções:** `verifiable_documents`, `document_files`, `document_render_jobs`, `render_jobs`, `school_documents_log`, `bulletin_verifications`, `history_verifications`, `promotion_books`, `promotion_book_counters`, `medical_certificates`.
- **Complexidade:** alta · Acoplamento: médio · Risco: médio · Expansão: alta. **BI:** volume de emissões.

## 13. AEE (Atendimento Educacional Especializado) — 🟢 ⛔ PROTEGIDO
- **Backend:** `aee.py` + models `PlanoAEE*`. **Frontend:** `DiarioAEE.js`, `PlanoAEEModal.js`, tutorial.
- **Coleções:** `planos_aee`, `planos_aee_templates`, `atendimentos_aee`, `articulacoes_aee`, `evolucoes_aee`.
- ⛔ **MÓDULO BLOQUEADO** (PRD): qualquer alteração exige autorização explícita do usuário.
- **Complexidade:** alta · Risco: **alto** (bloqueado). **BI:** alunos PcD/atendimentos.

## 14. Transferência Institucional & Reconstrução de Histórico — 🟢
- **Backend:** `school_transfer.py`, `history_reconstruction.py`. **Service:** `history_consolidator.py`, `pedagogical_consolidation.py`.
- **Frontend:** `SchoolTransferWizard.jsx`, `SchoolTransfers.jsx`, `HistoryReconstruction.jsx`.
- **Coleções:** `school_transfer_audit`, `history_reconstruction_audit`.
- **Complexidade:** **alta** · Acoplamento: alto · Risco: **alto** (destrutivo) · Expansão: média.
- **Obs.:** motor canônico com dry-run + idempotência + **rollback** (janela 7d) + recibo PDF/QR. Coberto por 27 testes de gate. Exemplar de engenharia madura.

## 15. Bolsa Família — 🟢
- **Backend:** `bolsa_familia.py`. **Services:** `bf_network_stats.py`, `bf_reason_suggestion.py`, `bf_legacy_migration.py`.
- **Frontend:** `BolsaFamilia.js`, `BuscaAtivaDashboard.jsx`.
- **Coleções:** `bolsa_familia_tracking`, `bf_network_stats_snapshots`.
- **Complexidade:** média · Risco: médio (condicionalidade PBF). **BI:** frequência PBF/limiares MEC.

## 16. Assistência Social — 🟡
- **Backend:** `social.py`. **Frontend:** `AssocialDashboard.js`.
- **Complexidade:** média · Acoplamento: baixo · Risco: baixo · Expansão: alta.

## 17. Vacinas / Saúde escolar — 🟡
- **Backend:** `vaccines.py`. **Frontend:** `VaccineDashboard.js`. **Coleção:** `vaccine_status`.
- **Complexidade:** baixa · Risco: baixo · Expansão: alta. **BI:** cobertura vacinal.

## 18. Analytics, Painel PME & Relatórios Mensais — 🟡
- **Backend:** `analytics.py`, `pme_anos_finais.py`, `monthly_reports.py`.
- **Services:** `monthly_report_service.py`, `monthly_report_scheduler.py`, `monthly_report_email.py`, `bf_network_stats.py`.
- **Frontend:** `AnalyticsDashboard.jsx`, `PmeAnosFinais.jsx`, `PmeExternalIndicators.jsx`, `MonthlyReports.jsx`, `SemedPanel.jsx`, `RankingGestores.jsx`.
- **Coleções:** `pme_external_indicators`, `monthly_reports`, `monthly_goals`.
- **Complexidade:** alta · Acoplamento: alto (lê muitas fontes) · Risco: médio · Expansão: **alta**.
- **Obs.:** núcleo da futura camada de **BI**. Ver [21](21_BUSINESS_INTELLIGENCE.md) (Onda 2).

## 19. PMPI Engine, Motores de Risco & Alertas — 🟡🔴
- **Backend:** `pmpi.py`, `pmpi_engine.py`, `pmpi_ai.py`, `interventions.py`.
- **Services:** `pmpi_compute.py`, `alert_engine.py`, `academic_risk_engine.py`, `attendance_risk_engine.py`, `overall_risk_engine.py`, `diagnostic_engine.py`, `intervention_detector.py`, `plano_acao_ai.py`, `recommendation_validator.py`.
- **Frontend:** `PmpiEngine.jsx`, `Interventions.jsx`, `PlanoAcao.jsx`, `ActionPlans.jsx`.
- **Coleções:** `alert_rules`, `alerts`, `student_alerts`, `intervention_alerts`, `intervention_notifications`, `student_risk_scores`, `ai_risk_analyses`, `ai_plans`, `ai_analysis_snapshots`, `pmpi_cron_log`, `action_plans`.
- **Complexidade:** **alta** · Acoplamento: **alto** · Risco: alto · Expansão: **alta**.
- **Obs.:** vários motores de risco potencialmente sobrepostos — candidato a **unificação** ([16](16_CODIGO_DUPLICADO.md), Onda 2).

## 20. Student Intelligence Engine (SIE) — 🔴 (parcial)
- **Backend:** `student_intelligence.py`. **Service:** `sie_service.py`. **Coleções:** `sie_config`, `student_diagnostics`, `student_snapshots`.
- **Maturidade:** **parcial** (tarefa futura no PRD) · Complexidade: alta · Risco: médio · Expansão: **alta**.

## 21. Notificações, Mensagens & Avisos — 🟡
- **Backend:** `notifications.py`, `admin_messages.py`, `announcements.py`. WebSocket (`useWebSocket.js`, `MessagingContext.js`).
- **Frontend:** `Announcements.js`, `MessageLogs.js`.
- **Coleções:** `notifications`? , `messages`, `message_logs`, `announcements`, `announcement_reads`, `connections`.
- **Complexidade:** média · Acoplamento: médio · Risco: médio · Expansão: alta.

## 22. Auditoria, Observabilidade & Integridade — 🟢
- **Backend:** `audit_logs.py`, `admin_observability.py`, `integrity_audit.py`, `audit_service.py`, `tenant_audit.py`.
- **Frontend:** `AuditLogs.jsx`, `OnlineUsers.js`, `GradeIntegrity.jsx`.
- **Coleções:** `audit_logs`, `hr_audit_logs`, `tenant_security_events`.
- **Complexidade:** média · Risco: baixo · Expansão: média. **BI:** trilhas/uso.

## 23. Manutenção, Migrações & Mutações Críticas — 🟢
- **Backend:** `maintenance.py`, `grade_legacy_migration.py`, `dedup_enrollments.py`, `student_series_backfill.py`, `lib/critical_mutation.py`.
- **Coleções:** `*_runs`, `*_locks`, `*_idempotency` (on-demand).
- **Complexidade:** alta · Risco: alto (destrutivo, mas com dry-run/rollback) · Expansão: média.
- **Obs.:** padrão `with_critical_mutation` (idempotência + lock + auditoria) — ativo de reutilização de alta qualidade.

## 24. Portal do Aluno / Responsável — 🟡
- **Backend:** `student_portal.py`, `admin_student_users.py`, `professor.py` (turmas do professor).
- **Frontend:** `AlunoDashboard.jsx`, `BoletimAluno.jsx`, `ProfessorDashboard.js`.
- **Service:** `student_account_service.py`.
- **Complexidade:** média · Risco: médio · Expansão: alta.

## 25. Currículo — Revisão de Conteúdo & Higienização Textual — 🟡
- **Backend:** `content_review.py`, `text_improvement.py`, `spellcheck.py`. **Services:** `content_audit.py`, `text_utils.py`.
- **Frontend:** `ContentReview.jsx`, `TextImprovement.jsx`.
- **Complexidade:** média · Risco: baixo · Expansão: média.

## 26. MEC / Integrações Governamentais — 🔴 (parcial)
- **Backend:** `mec_integration.py`. **Frontend:** `MECIntegration.js`. **Coleção:** `mec_integration`.
- **Maturidade:** parcial/stub · Risco: médio · Expansão: alta (Educacenso/Sistema Presença).

## 27. Sincronização Offline (PWA) — 🟡
- **Frontend:** `contexts/OfflineContext.jsx`, `useOfflineSync.js`, `useOfflineGrades.js`, `useOfflineAttendance.js`, `db/database.js` (Dexie), `public/sw.js`. **Backend:** `sync.py`. **Coleção:** `sync_telemetry`.
- **Complexidade:** **alta** · Risco: alto · Expansão: **alta** (Fase B futura: Conteúdo/Diário offline).

## 28. Dependências de Estudo (recuperação/progressão parcial) — 🟡
- **Backend:** `student_dependencies.py`, `dependency_completions.py`. **Frontend:** `features/dependency`, `components/StudentDependencySection.jsx`.
- **Coleções:** `student_dependencies`, `dependency_completions`.

## 29. Debug / Sandbox / Ferramentas Admin — 🟡
- **Backend:** `debug.py`, `sandbox.py`, `sandbox_service.py`, `admin.py`, `profiles.py`, `permission_overrides.py`.
- **Frontend:** `AdminTools.js`, `PermissionMatrix.js`, `TutorialsPage.jsx`.
- **Coleções:** `permission_overrides`, `user_profiles`.

---

## Resumo quantitativo por maturidade
| Classe | Módulos (aprox.) |
|---|---|
| 🟢 Consolidado | 13 |
| 🟡 Precisa Evoluir | 12 |
| 🔴 Recomendado Refatorar / Parcial | 3 (SIE, MEC, motores de risco sobrepostos) |
| ⛔ Protegido (AEE) | 1 |

> Observação: a granularidade é funcional. Um mesmo router pode aparecer em mais
> de um módulo quando serve a fronteiras compartilhadas (ex.: `professor.py`).
