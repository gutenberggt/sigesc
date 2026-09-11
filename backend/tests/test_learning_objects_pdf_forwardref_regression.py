import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Optional

from fastapi import APIRouter, FastAPI, Query, Request
from fastapi.testclient import TestClient


def _load_content_dvd_history_module():
    """Load the adapter directly, without executing routers/__init__.py.

    This regression needs the real FastAPI/Pydantic stack but not the complete
    SIGESC bootstrap. Minimal dependency stubs keep the test focused on route
    registration and query-parameter validation.
    """
    auth_stub = ModuleType("auth_middleware")

    class AuthMiddleware:
        @staticmethod
        async def get_current_user(request):
            return {"role": "professor"}

        @staticmethod
        def require_roles(_roles):
            async def dependency(_request):
                return {"role": "professor"}

            return dependency

    auth_stub.AuthMiddleware = AuthMiddleware

    services_stub = ModuleType("services")
    services_stub.__path__ = []

    assignment_scope_stub = ModuleType("services.content_assignment_scope")

    async def filter_visible_content_entries(*_args, **_kwargs):
        return []

    assignment_scope_stub.filter_visible_content_entries = filter_visible_content_entries

    history_bridge_stub = ModuleType("services.content_history_bridge")

    class ContentHistoryBridgeError(Exception):
        def __init__(self, code="TEST", message="test"):
            super().__init__(message)
            self.code = code
            self.message = message

    async def list_assignment_content_history(*_args, **_kwargs):
        return {"items": []}

    history_bridge_stub.ContentHistoryBridgeError = ContentHistoryBridgeError
    history_bridge_stub.list_assignment_content_history = list_assignment_content_history

    teacher_diaries_stub = ModuleType("services.teacher_diaries")

    async def list_teacher_diaries(*_args, **_kwargs):
        return {"items": []}

    teacher_diaries_stub.list_teacher_diaries = list_teacher_diaries

    tenant_scope_stub = ModuleType("tenant_scope")
    tenant_scope_stub.get_mantenedora_scope = lambda *_args, **_kwargs: None

    stubs = {
        "auth_middleware": auth_stub,
        "services": services_stub,
        "services.content_assignment_scope": assignment_scope_stub,
        "services.content_history_bridge": history_bridge_stub,
        "services.teacher_diaries": teacher_diaries_stub,
        "tenant_scope": tenant_scope_stub,
    }
    previous = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        path = Path(__file__).parents[1] / "routers" / "content_dvd_history.py"
        spec = importlib.util.spec_from_file_location(
            "_content_dvd_history_forwardref_regression", path
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        for name, value in previous.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


def _fake_learning_objects_module():
    module = SimpleNamespace()
    module.router = APIRouter()

    def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
        @module.router.get("/learning-objects/pdf/bimestre/{class_id}")
        async def legacy_pdf(
            class_id: str,
            request: Request,
            bimestre: int = Query(..., ge=1, le=4),
            academic_year: Optional[int] = None,
            course_id: Optional[str] = None,
            assignment_id: Optional[str] = None,
        ):
            return {
                "class_id": class_id,
                "bimestre": bimestre,
                "academic_year": academic_year,
                "course_id": course_id,
                "assignment_id": assignment_id,
            }

        return module.router

    module.setup_router = setup_router
    return module


def test_dvd_history_pdf_resolves_optional_query_annotations_at_runtime():
    """Pydantic 2.13 must not receive Optional[...] as unresolved ForwardRef."""
    adapter = _load_content_dvd_history_module()
    module = _fake_learning_objects_module()
    adapter.install_learning_objects_history_setup(module)
    router = module.setup_router(db=None)

    pdf_route = next(
        route
        for route in router.routes
        if route.path == "/learning-objects/pdf/bimestre/{class_id}"
        and "GET" in route.methods
    )
    assert pdf_route.endpoint.__annotations__["academic_year"] == Optional[int]
    assert pdf_route.endpoint.__annotations__["course_id"] == Optional[str]
    assert pdf_route.endpoint.__annotations__["assignment_id"] == Optional[str]

    app = FastAPI()
    app.include_router(router, prefix="/api")
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get(
        "/api/learning-objects/pdf/bimestre/class-1",
        params={"bimestre": 3, "academic_year": 2026},
    )

    assert response.status_code == 200, response.text
    assert response.json()["academic_year"] == 2026
    assert response.json()["bimestre"] == 3
