"""Regressão F1.0 da composição efetiva da rota administrativa.

O server do SIGESC inclui ``setup_enrollments_router`` dentro de um APIRouter
com prefixo ``/api``. Este teste protege a composição real para impedir que o
prefixo legado ``/enrollments`` seja acidentalmente herdado pela Retificação.
"""

from fastapi import APIRouter
from mongomock_motor import AsyncMongoMockClient

from routers import setup_enrollments_router


class _AuditStub:
    async def log(self, *args, **kwargs):  # pragma: no cover - handlers não executados aqui
        return None


def test_effective_rectification_route_is_admin_sibling_of_enrollments():
    db = AsyncMongoMockClient()["sigesc_rectification_f1_route_test"]

    domain_router = setup_enrollments_router(db, _AuditStub())
    api_router = APIRouter(prefix="/api")
    api_router.include_router(domain_router)

    paths = {route.path for route in api_router.routes}
    rectification_paths = sorted(path for path in paths if "enrollment-rectification" in path)

    assert "/api/enrollments" in paths
    assert rectification_paths == ["/api/admin/enrollment-rectification/dry-run"]
    assert "/api/enrollments/admin/enrollment-rectification/dry-run" not in paths
    assert not any("execute" in path or "rollback" in path for path in rectification_paths)
