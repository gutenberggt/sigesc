"""
Routers do SIGESC
Organização modular dos endpoints da API.
"""

from .auth import router as auth_router, setup_router as setup_auth_router

__all__ = ['auth_router', 'setup_auth_router']
