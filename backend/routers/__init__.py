"""
Routers do SIGESC
Organização modular dos endpoints da API.

PATCH 4.x: Refatoração gradual do server.py para routers modulares.
"""

from .auth import router as auth_router, setup_router as _setup_auth_router
from .auth_impersonation import install_auth_impersonation
from .auth_impersonation_search import install_auth_impersonation_search
from services.impersonation_audit_policy import install_impersonation_request_audit_policy
from .users import router as users_router, setup_router as setup_users_router
from .schools import router as schools_router, setup_router as setup_schools_router
from .courses import router as courses_router, setup_router as setup_courses_router
from .classes import router as classes_router, setup_router as setup_classes_router
from .guardians import router as guardians_router, setup_router as setup_guardians_router
from .enrollments import router as enrollments_router, setup_router as setup_enrollments_router
from .students import router as students_router, setup_students_router as _setup_students_router
from .student_enrollment_identity_guard import install_student_enrollment_identity_guard
from .student_enrollment_identity_continuity import install_student_enrollment_identity_continuity
from .student_enrollment_audit_semantics import install_student_enrollment_audit_semantics
from .student_legacy_compat import install_student_legacy_compat
from .grades import router as grades_router, setup_grades_router as _setup_grades_router
from .grades_dvd import install_grades_dvd_adapter
from .grades_dvd_hardening import install_grades_dvd_hardening
from . import grades_dvd_parity as _grades_dvd_parity_mod
from .grades_dvd_parity import install_grades_dvd_parity
from .grades_dvd_student_scope import install_grades_dvd_student_scope
from .attendance import router as attendance_router, setup_attendance_router as _setup_attendance_router
from . import attendance_dvd as _attendance_dvd_mod
from .attendance_dvd import install_attendance_dvd_adapter
from . import attendance_tabs_dvd as _attendance_tabs_dvd_mod
from .attendance_tabs_dvd import install_attendance_tabs_dvd_adapter
from .attendance_pdf_dvd_parity import install_attendance_pdf_dvd_parity
from .attendance_ext_dvd import install_attendance_ext_dvd_setup
from .dvd_historical_bridge_generalization import install_dvd_historical_bridge_generalization
from .calendar import router as calendar_router, setup_router as setup_calendar_router
from .staff import router as staff_router, setup_staff_router
from .announcements import router as announcements_router, setup_announcements_router
from .analytics import router as analytics_router, setup_analytics_router

# FastAPI resolve anotações postergadas usando o namespace global do módulo que
# declara a função. O adaptador de abas registra o mesmo payload Pydantic da
# Fase 4 dinamicamente; expor este alias evita ForwardRef dependente de closure.
_attendance_tabs_dvd_mod.dvd_mod = _attendance_dvd_mod

# P0 DVD histórico — Frequência e Notas usam a mesma validação fail-closed da
# proveniência de cutovers ativados. A instalação só troca o helper de leitura;
# não altera valid_from, não migra documentos e não adiciona autoria retroativa.
install_dvd_historical_bridge_generalization(
    _attendance_tabs_dvd_mod,
    _grades_dvd_parity_mod,
)

# P0 DVD Conteúdos — instala os adaptadores antes de server.py importar
# setup_content_entries_router/learning_objects. Os routers originais permanecem
# intactos; leitura histórica e cópia segura são adicionadas sobre o motor canônico.
from . import content_entries as _content_entries_mod
from . import learning_objects as _learning_objects_mod
from . import assignments as _assignments_mod
from .content_dvd_history import install_content_history_setups
from .content_copy_dvd import install_content_copy_setup
from services.course_missing_containment import install_course_missing_containment_setup

# Sprint 007 — a gestão da política avaliativa é exposta dentro do cadastro da
# mantenedora, mas sua SSoT permanece em assessment_policies. Envolver o setup
# evita tocar no server.py e não instala qualquer runtime de Notas/cutover.
from . import mantenedora as _mantenedora_mod
from .assessment_policy_admin import install_assessment_policy_admin_setup

# AEE v2 — evolução incremental autorizada pelo proprietário em 21/08/2026.
# O router legado bloqueado permanece intacto. P0 protege integridade/autoria;
# Fase 1 projeta o Dossiê canônico; Fase 2 adiciona persistência sidecar versionada;
# Fase 6.0A impede apagar a âncora legada depois que o sidecar V2 existir;
# Fase 6.2A anexa metadados da fonte efetiva ao Diário em Shadow Mode;
# Fase 6.2B troca somente a grade semanal pela agenda efetiva, preservando
# grade_horarios_legacy e bloqueando cutover parcial quando o shadow falhar;
# Fase 6.3A observa o PDF legado em paralelo e registra paridade/divergência;
# Fase 6.3B usa a agenda efetiva no PDF apenas sob paridade total, de modo
# atômico e fail-closed, preservando o gerador ReportLab e o router legado;
# Fase 6.4A observa a consulta individual do Plano, sem alterar seu JSON legado;
# Fase 6.4B expõe Fonte Efetiva/Dossiê V2 de forma aditiva no mesmo GET;
# Fase 6.5A homologada em produção em 23/08/2026 após Shadow Mode real;
# Fase 6.5B ativa a Fonte Efetiva no PDF individual, preservando fallback legado
# fail-closed em erro de integridade ou projeção não representável;
# Fase 6.6A observou a listagem legado em lote e foi homologada em produção;
# Fase 6.6B expôs o contrato aditivo da Fonte Efetiva e foi homologada;
# Fase 6.6C substitui operacionalmente a 6.6B e torna status_filter, total,
# paginação e leitura da listagem coerentes com a Fonte Efetiva, sem writes;
# Fase 6.6D governa PUT/duplicate/DELETE legado: sem head mantém compatibilidade;
# com head exige Dossiê V2 e protege a âncora histórica de forma fail-closed;
# P0 temporal rejeita novos horários AEE fora de 06:00–22:00 ou com fim <= início.
from . import aee as _aee_mod
from .aee_v2_p0 import install_aee_v2_p0_setup
from .aee_v2_dossier import install_aee_v2_dossier_setup
from .aee_v2_persistence import install_aee_v2_persistence_setup
from .aee_v2_delete_guard import install_aee_v2_delete_guard_setup
from aee_v2.diario_shadow import install_aee_v2_diario_shadow_setup
from aee_v2.diario_schedule_cutover import install_aee_v2_diario_schedule_cutover_setup
from aee_v2.pdf_shadow import install_aee_v2_pdf_shadow_setup
from aee_v2.pdf_schedule_cutover import install_aee_v2_pdf_schedule_cutover_setup
from aee_v2.time_integrity import install_aee_time_integrity_setup
from aee_v2.plano_shadow import install_aee_v2_plano_shadow_setup
from aee_v2.plano_effective_read import install_aee_v2_plano_effective_read_setup
from aee_v2.plano_pdf_effective import install_aee_v2_plano_pdf_effective_setup
from aee_v2.plan_list_effective_cutover import install_aee_v2_plan_list_effective_cutover_setup
from aee_v2.plan_write_governance import install_aee_v2_plan_write_governance_setup


# `server.py` importa attendance_ext somente depois deste pacote. Envolver o
# setup aqui garante que o endpoint legado de PDF/alertas seja protegido antes
# de ser registrado na aplicação, sem alterar o gerador/layout legado.
install_attendance_ext_dvd_setup()
install_content_history_setups(_content_entries_mod, _learning_objects_mod)
install_content_copy_setup(_content_entries_mod)
install_course_missing_containment_setup(_learning_objects_mod, _assignments_mod)
install_assessment_policy_admin_setup(_mantenedora_mod)
install_aee_v2_p0_setup(_aee_mod)
install_aee_v2_dossier_setup(_aee_mod)
install_aee_v2_persistence_setup(_aee_mod)
install_aee_v2_delete_guard_setup(_aee_mod)
install_aee_v2_diario_shadow_setup(_aee_mod)
install_aee_v2_diario_schedule_cutover_setup(_aee_mod)
install_aee_v2_pdf_shadow_setup(_aee_mod)
install_aee_v2_pdf_schedule_cutover_setup(_aee_mod)
install_aee_time_integrity_setup(_aee_mod)
install_aee_v2_plano_shadow_setup(_aee_mod)
install_aee_v2_plano_effective_read_setup(_aee_mod)
install_aee_v2_plano_pdf_effective_setup(_aee_mod)
install_aee_v2_plan_list_effective_cutover_setup(_aee_mod)
install_aee_v2_plan_write_governance_setup(_aee_mod)


def setup_auth_router(db, audit_service):
    """Configura Auth + Modo de Teste seguro do Super Administrador."""
    configured = _setup_auth_router(db, audit_service)
    configured = install_auth_impersonation(configured, db, audit_service)
    configured = install_auth_impersonation_search(configured, db)
    install_impersonation_request_audit_policy(audit_service)
    return configured


def setup_students_router(db, audit_service, sandbox_db=None):
    """Configura Estudantes + identidade numérica + semântica/legado seguros."""
    configured = _setup_students_router(db, audit_service, sandbox_db)
    configured = install_student_enrollment_identity_guard(configured)
    configured = install_student_enrollment_identity_continuity(configured, db, audit_service)
    configured = install_student_enrollment_audit_semantics(configured, db, sandbox_db)
    return install_student_legacy_compat(configured, db, sandbox_db)


def setup_grades_router(
    db,
    audit_service,
    verify_academic_year_open_or_raise=None,
    verify_bimestre_edit_deadline_or_raise=None,
    sandbox_db=None,
):
    """Configura Notas + DVD + histórico + escopo Por Estudante do professor."""
    configured = _setup_grades_router(
        db,
        audit_service,
        verify_academic_year_open_or_raise,
        verify_bimestre_edit_deadline_or_raise,
        sandbox_db,
    )
    configured = install_grades_dvd_adapter(
        configured,
        db,
        audit_service,
        verify_academic_year_open_or_raise=verify_academic_year_open_or_raise,
        verify_bimestre_edit_deadline_or_raise=verify_bimestre_edit_deadline_or_raise,
        sandbox_db=sandbox_db,
    )
    configured = install_grades_dvd_hardening(
        configured,
        db,
        sandbox_db=sandbox_db,
    )
    configured = install_grades_dvd_parity(
        configured,
        db,
        sandbox_db=sandbox_db,
    )
    return install_grades_dvd_student_scope(
        configured,
        db,
        sandbox_db=sandbox_db,
    )


def setup_attendance_router(db, audit_service, sandbox_db=None):
    """Configura Frequência histórica + DVD Fase 4 + paridade das abas/PDF."""
    configured = _setup_attendance_router(db, audit_service, sandbox_db)
    configured = install_attendance_dvd_adapter(configured, db, audit_service, sandbox_db)
    configured = install_attendance_tabs_dvd_adapter(
        configured,
        db,
        audit_service,
        sandbox_db,
    )
    return install_attendance_pdf_dvd_parity(
        configured,
        db,
        sandbox_db=sandbox_db,
    )


__all__ = [
    'auth_router', 'setup_auth_router',
    'users_router', 'setup_users_router',
    'schools_router', 'setup_schools_router',
    'courses_router', 'setup_courses_router',
    'classes_router', 'setup_classes_router',
    'guardians_router', 'setup_guardians_router',
    'enrollments_router', 'setup_enrollments_router',
    'students_router', 'setup_students_router',
    'grades_router', 'setup_grades_router',
    'attendance_router', 'setup_attendance_router',
    'calendar_router', 'setup_calendar_router',
    'staff_router', 'setup_staff_router',
    'announcements_router', 'setup_announcements_router',
    'analytics_router', 'setup_analytics_router'
]
