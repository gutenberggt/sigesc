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
from .grades import router as grades_router, setup_grades_router
from .attendance import router as attendance_router, setup_attendance_router
from .calendar import router as calendar_router, setup_calendar_router
from .staff import router as staff_router, setup_staff_router
from .announcements import router as announcements_router, setup_announcements_router

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
    'announcements_router', 'setup_announcements_router'
]
