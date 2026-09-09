"""Regressão da composição efetiva da rota administrativa de Retificação.

O server do SIGESC inclui ``setup_enrollments_router`` dentro de um APIRouter
com prefixo ``/api``. O teste protege a composição real: F1.0 permanece
estritamente read-only (``/dry-run``) e o router irmão F2.2 expõe
``/prepare-execution``, ``/execute`` e ``/rollback`` (a F2.2 substitui a
exposição HTTP isolada da preparação F2.0, que permanece no repositório e é
testada diretamente em ``test_enrollment_rectification_f2_safety_kernel.py``).
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
        "/api/admin/enrollment-rectification/execute",
        "/api/admin/enrollment-rectification/prepare-execution",
        "/api/admin/enrollment-rectification/rollback",
    ]
    assert "/api/enrollments/admin/enrollment-rectification/dry-run" not in paths
    assert "/api/enrollments/admin/enrollment-rectification/prepare-execution" not in paths
    assert "/api/enrollments/admin/enrollment-rectification/execute" not in paths
    assert "/api/enrollments/admin/enrollment-rectification/rollback" not in paths
