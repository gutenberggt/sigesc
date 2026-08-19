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
from . import attendance_dvd as _attendance_dvd_mod
from .attendance_dvd import install_attendance_dvd_adapter
from . import attendance_tabs_dvd as _attendance_tabs_dvd_mod
from .attendance_tabs_dvd import install_attendance_tabs_dvd_adapter
from .attendance_ext_dvd import install_attendance_ext_dvd_setup
from .calendar import router as calendar_router, setup_calendar_router
from .staff import router as staff_router, setup_staff_router
from .announcements import router as announcements_router, setup_announcements_router
from .analytics import router as analytics_router, setup_analytics_router

# FastAPI resolve anotações postergadas usando o namespace global do módulo que
# declara a função. O adaptador de abas registra o mesmo payload Pydantic da
# Fase 4 dinamicamente; expor este alias evita ForwardRef dependente de closure.
_attendance_tabs_dvd_mod.dvd_mod = _attendance_dvd_mod

# P0 DVD Conteúdos — instala os adaptadores antes de server.py importar
# setup_content_entries_router/learning_objects. Os routers originais permanecem
# intactos; somente as superfícies de leitura recebem compatibilidade histórica.
from . import content_entries as _content_entries_mod
from . import learning_objects as _learning_objects_mod
from .content_dvd_history import install_content_history_setups


# `server.py` importa attendance_ext somente depois deste pacote. Envolver o
# setup aqui garante que o endpoint legado de PDF/alertas seja protegido antes
# de ser registrado na aplicação, sem alterar o gerador/layout legado.
install_attendance_ext_dvd_setup()
install_content_history_setups(_content_entries_mod, _learning_objects_mod)


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
    """Configura Frequência histórica + DVD Fase 4 + paridade das abas."""
    configured = _setup_attendance_router(db, audit_service, sandbox_db)
    configured = install_attendance_dvd_adapter(configured, db, audit_service, sandbox_db)
    return install_attendance_tabs_dvd_adapter(
        configured,
        db,
        audit_service,
        sandbox_db,
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
