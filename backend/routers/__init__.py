"""
Routers do SIGESC
Organização modular dos endpoints da API.
"""

from .auth import router as auth_router, setup_router as setup_auth_router
from .users import router as users_router, setup_router as setup_users_router
from .schools import router as schools_router, setup_router as setup_schools_router
from .courses import router as courses_router, setup_router as setup_courses_router
from .classes import router as classes_router, setup_router as setup_classes_router

__all__ = [
    'auth_router', 'setup_auth_router',
    'users_router', 'setup_users_router',
    'schools_router', 'setup_schools_router',
    'courses_router', 'setup_courses_router',
    'classes_router', 'setup_classes_router'
]
