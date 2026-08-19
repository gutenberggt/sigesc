"""
Routers do SIGESC
Organização modular dos endpoints da API.

PATCH 4.x: Refatoração gradual do server.py para routers modulares.
"""

from .auth import router as auth_router, setup_router as setup_auth_router
from .users import router as users_router, setup_router as setup_users_router
from .schools import router as schools_router, setup_router as setup_schools_router
from .courses import router as courses_router, setup_router as setup_courses_router
from .classes import router as classes_router, setup_router as setup_classes_router
from .guardians import router as guardians_router, setup_router as setup_guardians_router
from .enrollments import router as enrollments_router, setup_router as setup_enrollments_router
from .students import router as students_router, setup_students_router
from .grades import router as grades_router, setup_grades_router as _setup_grades_router
from .grades_dvd import install_grades_dvd_adapter
from .grades_dvd_hardening import install_grades_dvd_hardening
from .attendance import router as attendance_router, setup_attendance_router as _setup_attendance_router
from .attendance_dvd import install_attendance_dvd_adapter
from .attendance_ext_dvd import install_attendance_ext_dvd_setup
from .calendar import router as calendar_router, setup_calendar_router
from .staff import router as staff_router, setup_staff_router
from .announcements import router as announcements_router, setup_announcements_router
from .analytics import router as analytics_router, setup_analytics_router

# `server.py` importa attendance_ext somente depois deste pacote. Envolver o
# setup aqui garante que o endpoint legado de PDF seja protegido antes de ser
# registrado na aplicação, sem alterar o gerador/layout do PDF.
install_attendance_ext_dvd_setup()

# Urgências / Ficha Individual: `server.py` já registra `routers.documents.router`
# em /api. Para evitar tocar no server.py e manter o diff mínimo, envolvemos o
# setup do módulo documents e anexamos o router de contingência ao MESMO router
# sem prefixo. Resultado final:
#   /api/documents/ficha-individual-manual/preview
#   /api/documents/ficha-individual-manual
# A instalação é feita uma única vez por processo.
from . import documents as _documents_module
from .manual_ficha_individual import setup_router as _setup_manual_ficha_router

_original_documents_setup_router = _documents_module.setup_router
_urgencias_manual_installed = False


def _setup_documents_with_urgencias(db, audit_service=None, sandbox_db=None, **kwargs):
    global _urgencias_manual_installed
    configured = _original_documents_setup_router(
        db, audit_service, sandbox_db, **kwargs
    )
    if not _urgencias_manual_installed:
        manual_router = _setup_manual_ficha_router(
            db, audit_service, sandbox_db, **kwargs
        )
        _documents_module.router.include_router(manual_router)
        _urgencias_manual_installed = True
    return configured


_documents_module.setup_router = _setup_documents_with_urgencias


def setup_grades_router(
    db,
    audit_service,
    verify_academic_year_open_or_raise=None,
    verify_bimestre_edit_deadline_or_raise=None,
    sandbox_db=None,
):
    """Configura Notas históricas + adaptador DVD Fase 5 no mesmo router."""
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
    return install_grades_dvd_hardening(
        configured,
        db,
        sandbox_db=sandbox_db,
    )


def setup_attendance_router(db, audit_service, sandbox_db=None):
    """Configura Frequência histórica + adaptador DVD Fase 4 no mesmo router."""
    configured = _setup_attendance_router(db, audit_service, sandbox_db)
    return install_attendance_dvd_adapter(configured, db, audit_service, sandbox_db)


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
