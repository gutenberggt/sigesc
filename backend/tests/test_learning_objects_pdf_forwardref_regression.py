from types import SimpleNamespace
from typing import Optional

from fastapi import APIRouter, FastAPI, Query, Request
from fastapi.testclient import TestClient

from routers.content_dvd_history import install_learning_objects_history_setup


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
    """Regression: Pydantic 2.13 must not receive Optional[...] as ForwardRef.

    In production the postponed annotations from content_dvd_history caused
    academic_year to reach FastAPI as ForwardRef('Optional[int]'), producing an
    unhandled HTTP 500 before the PDF handler could run.
    """
    module = _fake_learning_objects_module()
    install_learning_objects_history_setup(module)
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
