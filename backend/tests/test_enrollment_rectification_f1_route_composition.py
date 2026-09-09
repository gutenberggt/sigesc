"""Regressão da composição efetiva da rota administrativa de Retificação.

O server do SIGESC inclui ``setup_enrollments_router`` dentro de um APIRouter
com prefixo ``/api``. O teste protege a composição real e garante que F2.0
acrescente apenas a preparação segura, sem expor `/execute` ou `/rollback`.
"""

from fastapi import APIRouter
from mongomock_motor import AsyncMongoMockClient

from routers import setup_enrollments_router


class _AuditStub:
    async def log(self, *args, **kwargs):  # pragma: no cover - handlers não executados aqui
        return None


def test_effective_rectification_routes_are_admin_siblings_of_enrollments():
    db = AsyncMongoMockClient()["sigesc_rectification_route_test"]

    domain_router = setup_enrollments_router(db, _AuditStub())
    api_router = APIRouter(prefix="/api")
    api_router.include_router(domain_router)

    paths = {route.path for route in api_router.routes}
    rectification_paths = sorted(path for path in paths if "enrollment-rectification" in path)

    assert "/api/enrollments" in paths
    assert rectification_paths == [
        "/api/admin/enrollment-rectification/dry-run",
        "/api/admin/enrollment-rectification/prepare-execution",
    ]
    assert "/api/enrollments/admin/enrollment-rectification/dry-run" not in paths
    assert "/api/enrollments/admin/enrollment-rectification/prepare-execution" not in paths
    assert "/api/admin/enrollment-rectification/execute" not in paths
    assert "/api/admin/enrollment-rectification/rollback" not in paths
