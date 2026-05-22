"""Criação idempotente de índices MongoDB.

Extraído de `server.py:create_indexes` (Fev/2026). Comportamento e ordem foram
preservados exatamente — apenas modularizados.
"""
import logging

logger = logging.getLogger(__name__)


async def create_all_indexes(db):
    """Cria/verifica índices em todas as coleções relevantes."""
    # Índices para students
    await db.students.create_index("id", unique=True)
    await db.students.create_index("cpf", sparse=True)
    await db.students.create_index("school_id")
    await db.students.create_index("class_id")
    await db.students.create_index(
        [("full_name", 1)],
        collation={"locale": "pt", "strength": 1},
        name="full_name_pt_collation",
    )
    await db.students.create_index([("status", 1), ("school_id", 1)])

    # Student Dependencies (Dependência de Estudos) — Fev/2026
    # Índices para listagens por aluno, turma+componente (diário) e duplicidade.
    # `background=True` evita lock em produção durante criação dos índices.
    await db.student_dependencies.create_index("id", unique=True, background=True)
    await db.student_dependencies.create_index(
        [("student_id", 1), ("status", 1)],
        name="ix_dep_student_status", background=True,
    )
    # Diário (Fase 2): consulta primária por turma+componente+status (com tenant scope).
    await db.student_dependencies.create_index(
        [("mantenedora_id", 1), ("class_id", 1), ("course_id", 1), ("status", 1)],
        name="ix_dep_tenant_class_course_status", background=True,
    )
    # Mantida a versão legada (sem tenant) como fallback p/ buscas administrativas.
    await db.student_dependencies.create_index(
        [("class_id", 1), ("course_id", 1), ("status", 1)],
        name="ix_dep_class_course", background=True,
    )
    await db.student_dependencies.create_index(
        [("mantenedora_id", 1), ("school_id", 1), ("academic_year", 1)],
        name="ix_dep_tenant_school_year", background=True,
    )
    # Relatórios anuais agregados.
    await db.student_dependencies.create_index(
        [("academic_year", 1), ("status", 1)],
        name="ix_dep_year_status", background=True,
    )
    # Duplicidade lógica: evita 2 dependências ativas do mesmo componente×ano de origem.
    await db.student_dependencies.create_index(
        [("student_id", 1), ("course_id", 1), ("origin_academic_year", 1)],
        name="uniq_dep_student_course_origin_active",
        unique=True,
        partialFilterExpression={"status": "active"},
        background=True,
    )

    # Grades (notas) — muito consultada
    await db.grades.create_index("id", unique=True)
    await db.grades.create_index([("student_id", 1), ("academic_year", 1)])
    await db.grades.create_index([("class_id", 1), ("course_id", 1), ("academic_year", 1)])
    await db.grades.create_index("student_id")

    # Attendance (frequência)
    await db.attendance.create_index("id", unique=True)
    await db.attendance.create_index([("class_id", 1), ("date", 1)])
    await db.attendance.create_index([("class_id", 1), ("academic_year", 1)])
    # Fase 1 (Mai/2026) — UNIQUE composto que reflete a granularidade real
    # do diário: por turma+data, e em anos finais também por componente+aula.
    # Previne duplicidade silenciosa (mesma chave criada por professores
    # diferentes em race condition).
    await db.attendance.create_index(
        [("class_id", 1), ("date", 1), ("course_id", 1), ("aula_numero", 1)],
        unique=True,
        name="ux_attendance_class_date_course_aula",
        background=True,
    )
    # Índice de suporte para queries por professor (autor) — usado por
    # relatórios "minhas frequências lançadas" e timeline de auditoria.
    await db.attendance.create_index(
        [("updated_by", 1), ("updated_at", -1)],
        name="ix_attendance_updated_by_at",
        background=True, sparse=True,
    )

    # =========================================================
    # Content Entries (Diário Pedagógico) — Rodada 2 / Mai/2026
    # =========================================================
    await db.content_entries.create_index("id", unique=True)
    # UNIQUE composto: 1 entry por (turma, componente, professor, data, aula)
    # Apenas para docs vivos (deleted=false). Permite soft-delete + recreate.
    await db.content_entries.create_index(
        [("class_id", 1), ("component_id", 1), ("teacher_id", 1),
         ("date", 1), ("aula_numero", 1)],
        unique=True,
        partialFilterExpression={"deleted": False},
        name="ux_content_entry_logical",
        background=True,
    )
    # Calendário/listagem por turma+data
    await db.content_entries.create_index(
        [("class_id", 1), ("date", 1), ("deleted", 1)],
        name="ix_content_class_date", background=True,
    )
    # "Meus lançamentos" do professor
    await db.content_entries.create_index(
        [("teacher_id", 1), ("date", -1)],
        name="ix_content_teacher_date", background=True,
    )
    # Workflow / publicação
    await db.content_entries.create_index(
        [("status", 1), ("updated_at", -1)],
        name="ix_content_status_updated", background=True,
    )

    # Enrollments (matrículas)
    await db.enrollments.create_index("id", unique=True)
    await db.enrollments.create_index([("student_id", 1), ("academic_year", 1)])
    await db.enrollments.create_index("school_id")
    # Índice parcial único para prevenir duplicatas de matrícula ativa
    await db.enrollments.create_index(
        [("student_id", 1), ("class_id", 1), ("academic_year", 1)],
        unique=True,
        partialFilterExpression={"status": "active"},
        name="unique_active_enrollment_per_class",
    )

    # Classes (turmas)
    await db.classes.create_index("id", unique=True)
    await db.classes.create_index("school_id")
    await db.classes.create_index([("school_id", 1), ("academic_year", 1)])

    # Staff (servidores)
    await db.staff.create_index("id", unique=True)
    await db.staff.create_index("email", sparse=True)
    await db.staff.create_index("cpf", sparse=True)
    await db.staff.create_index(
        [("nome", 1)],
        collation={"locale": "pt", "strength": 1},
        name="nome_pt_collation",
    )

    # School assignments (lotações)
    await db.school_assignments.create_index("id", unique=True)
    await db.school_assignments.create_index([("staff_id", 1), ("academic_year", 1)])
    await db.school_assignments.create_index([("school_id", 1), ("academic_year", 1)])

    # Teacher assignments (alocações)
    await db.teacher_assignments.create_index("id", unique=True)
    await db.teacher_assignments.create_index([("staff_id", 1), ("academic_year", 1)])
    await db.teacher_assignments.create_index([("class_id", 1), ("course_id", 1)])
    await db.teacher_assignments.create_index([("class_id", 1), ("status", 1)])

    # Attendance compound (componente)
    await db.attendance.create_index([("class_id", 1), ("course_id", 1), ("academic_year", 1)])

    # Mensageiro
    await db.connections.create_index("id", unique=True)
    await db.connections.create_index([("requester_id", 1), ("receiver_id", 1)])
    await db.messages.create_index([("connection_id", 1), ("created_at", -1)])
    await db.messages.create_index([("sender_id", 1), ("receiver_id", 1)])

    # Courses (componentes)
    await db.courses.create_index("id", unique=True)
    await db.courses.create_index("nivel_ensino")

    # Performance de PDFs
    await db.learning_objects.create_index(
        [("class_id", 1), ("academic_year", 1), ("date", 1)], name="lo_class_year_date"
    )
    await db.learning_objects.create_index(
        [("class_id", 1), ("course_id", 1), ("academic_year", 1)], name="lo_class_course_year"
    )
    await db.enrollments.create_index(
        [("class_id", 1), ("status", 1), ("academic_year", 1)], name="enr_class_status_year"
    )
    await db.calendar_events.create_index("academic_year", name="calevents_year")
    await db.calendario_letivo.create_index(
        [("ano_letivo", 1), ("school_id", 1)], name="cal_year_school"
    )

    # Multi-tenant (mantenedora_id)
    await db.mantenedoras.create_index("id", unique=True)
    for coll in (
        "schools", "staff", "students", "classes", "courses",
        "enrollments", "grades", "learning_objects", "calendar_events",
        "calendario_letivo", "school_assignments", "teacher_assignments",
        "payroll_items", "announcements", "action_plans",
    ):
        try:
            await db[coll].create_index("mantenedora_id", name=f"{coll[:15]}_mid")
        except Exception:
            pass

    # Action plans
    try:
        await db.action_plans.create_index("id", unique=True)
        await db.action_plans.create_index([("school_id", 1), ("status", 1)])
    except Exception:
        pass

    # PMPI Engine
    try:
        await db.alert_rules.create_index("id", unique=True)
        await db.alert_rules.create_index([("mantenedora_id", 1), ("active", 1)])
        await db.alerts.create_index("id", unique=True)
        await db.alerts.create_index([("mantenedora_id", 1), ("status", 1), ("detected_at", -1)])
        await db.alerts.create_index([("rule_id", 1), ("school_id", 1), ("status", 1)])
        await db.monthly_goals.create_index("id", unique=True)
        await db.monthly_goals.create_index(
            [("mantenedora_id", 1), ("month", 1), ("school_id", 1)], unique=True
        )
    except Exception:
        pass

    # Schools, users, audit, medical, payroll
    await db.schools.create_index("id", unique=True)
    await db.users.create_index("id", unique=True)
    await db.users.create_index("email", unique=True)
    await db.audit_logs.create_index([("timestamp", -1)])
    await db.audit_logs.create_index("user_id")
    await db.audit_logs.create_index("collection")
    await db.audit_logs.create_index([("collection", 1), ("document_id", 1)])
    # Fase 1 Diário (Mai/2026) — queries pedagógicas:
    # "todas as alterações da turma X" / "todas as alterações em DD/MM"
    await db.audit_logs.create_index(
        [("collection", 1), ("extra_data.class_id", 1), ("extra_data.date", 1)],
        name="ix_audit_diary_class_date", background=True, sparse=True,
    )
    # "todas as alterações no aluno X" (busca multi-tabela via extra_data)
    await db.audit_logs.create_index(
        [("extra_data.student_ids_changed", 1), ("timestamp", -1)],
        name="ix_audit_diary_student_changed", background=True, sparse=True,
    )
    # "todas as sobrescritas pós-conflito" — auditoria institucional
    await db.audit_logs.create_index(
        [("extra_data.change_kind", 1), ("timestamp", -1)],
        name="ix_audit_change_kind", background=True, sparse=True,
    )

    await db.medical_certificates.create_index("id", unique=True)
    await db.medical_certificates.create_index("student_id")
    await db.medical_certificates.create_index(
        [("student_id", 1), ("start_date", 1), ("end_date", 1)]
    )

    await db.payroll_competencies.create_index("id", unique=True)
    await db.payroll_competencies.create_index([("year", -1), ("month", -1)], unique=True)
    await db.school_payrolls.create_index("id", unique=True)
    await db.school_payrolls.create_index(
        [("competency_id", 1), ("school_id", 1)], unique=True
    )
    await db.school_payrolls.create_index("school_id")
    await db.payroll_items.create_index("id", unique=True)
    await db.payroll_items.create_index("school_payroll_id")
    await db.payroll_items.create_index([("competency_id", 1), ("employee_id", 1)])
    await db.payroll_occurrences.create_index("id", unique=True)
    await db.payroll_occurrences.create_index("payroll_item_id")

    # Bolsa Família - Motivos MEC (Fev/2026)
    await db.attendance_frequency_reason_groups.create_index("id", unique=True, background=True)
    await db.attendance_frequency_reason_groups.create_index(
        [("mec_code", 1), ("mec_version", 1)], unique=True, background=True,
        name="uq_group_mec_code_version",
    )
    await db.attendance_frequency_reason_groups.create_index(
        [("active", 1), ("sort_order", 1)], background=True,
        name="ix_group_active_sort",
    )
    await db.attendance_frequency_reasons.create_index("id", unique=True, background=True)
    await db.attendance_frequency_reasons.create_index(
        [("mec_subcode", 1), ("mec_version", 1)], unique=True, background=True,
        name="uq_reason_subcode_version",
    )
    await db.attendance_frequency_reasons.create_index(
        [("group_id", 1), ("active", 1)], background=True,
        name="ix_reason_group_active",
    )
    await db.attendance_frequency_reasons.create_index(
        [("mec_group_code", 1), ("mec_subcode", 1)], background=True,
        name="ix_reason_group_sub",
    )
    # Tracking BF — índice composto (lookup principal)
    await db.bolsa_familia_tracking.create_index(
        [("school_id", 1), ("academic_year", 1), ("month", 1), ("student_id", 1)],
        background=True,
        name="ix_bf_tracking_lookup",
    )
    await db.bolsa_familia_tracking.create_index(
        [("reason_id", 1)], sparse=True, background=True, name="ix_bf_tracking_reason"
    )

    # BF Network Stats Snapshots (Fase 3B — Fev/2026)
    await db.bf_network_stats_snapshots.create_index(
        [("snapshot_date", -1), ("scope.academic_year", 1), ("scope.mec_version", 1)],
        unique=True, background=True, name="uq_bf_snapshot",
    )

    logger.info("Índices MongoDB criados/verificados com sucesso")
