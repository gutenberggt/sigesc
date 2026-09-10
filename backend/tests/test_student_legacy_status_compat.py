import pytest
from fastapi import APIRouter, Request
from pydantic import ValidationError

from auth_middleware import AuthMiddleware
from models import Student, StudentUpdate
from routers.student_legacy_compat import (
    build_compatible_student,
    install_student_legacy_compat,
    is_legacy_compat_validation_error,
    normalize_legacy_student_doc,
)


def _route(router, path, method):
    return next(
        route
        for route in router.routes
        if getattr(route, "path", None) == path
        and method in (getattr(route, "methods", set()) or set())
    )


@pytest.mark.parametrize(
    ("legacy", "canonical"),
    [
        ("Ativo", "active"),
        ("INATIVO", "inactive"),
        ("Desistente", "dropout"),
        ("Transferido", "transferred"),
        ("Falecido", "deceased"),
        ("Cancelado", "cancelled"),
        ("Reclassificado", "reclassified"),
        ("Progredido", "progressed"),
    ],
)
def test_known_legacy_statuses_are_projected_without_mutating_source(legacy, canonical):
    source = {
        "id": "student-legacy-status",
        "full_name": "Estudante Legado",
        "status": legacy,
    }

    normalized = normalize_legacy_student_doc(source)

    assert source["status"] == legacy
    assert normalized["status"] == canonical
    assert Student.model_validate(normalized).status == canonical


def test_status_only_validation_error_is_eligible_for_legacy_fallback():
    with pytest.raises(ValidationError) as caught:
        Student.model_validate(
            {
                "id": "student-inactive",
                "full_name": "Estudante Inativo",
                "status": "Inativo",
            }
        )

    roots = {str(error["loc"][0]) for error in caught.value.errors()}
    assert roots == {"status"}
    assert is_legacy_compat_validation_error(caught.value) is True


def test_unknown_status_is_never_silently_reinterpreted():
    source = {
        "id": "student-unknown-status",
        "full_name": "Estudante Legado",
        "status": "situacao_desconhecida",
    }

    normalized = normalize_legacy_student_doc(source)

    assert normalized["status"] == "situacao_desconhecida"
    with pytest.raises(ValidationError):
        build_compatible_student(source)


@pytest.mark.asyncio
async def test_super_admin_get_fallback_opens_inactive_legacy_profile(monkeypatch):
    legacy_doc = {
        "id": "student-inactive-legacy",
        "full_name": "Estudante Inativo Legado",
        "status": "Inativo",
        "address": {},
    }

    class FakeStudents:
        def __init__(self):
            self.find_calls = 0

        async def find_one(self, query, projection):
            self.find_calls += 1
            assert query == {"id": "student-inactive-legacy"}
            assert projection == {"_id": 0}
            return dict(legacy_doc)

    class FakeDB:
        def __init__(self):
            self.students = FakeStudents()

    async def fake_current_user(request):
        return {
            "id": "super-admin-1",
            "role": "super_admin",
            "is_sandbox": False,
        }

    monkeypatch.setattr(AuthMiddleware, "get_current_user", fake_current_user)

    router = APIRouter(prefix="/students")

    @router.get("/{student_id}", response_model=Student)
    async def get_student(student_id: str, request: Request):
        assert student_id == "student-inactive-legacy"
        return Student.model_validate(legacy_doc)

    @router.put("/{student_id}", response_model=Student)
    async def update_student(
        student_id: str,
        student_update: StudentUpdate,
        request: Request,
    ):  # pragma: no cover
        raise NotImplementedError

    @router.post("/{student_id}/cancel-transfer")
    async def cancel_transfer(student_id: str, request: Request):  # pragma: no cover
        raise NotImplementedError

    db = FakeDB()
    install_student_legacy_compat(router, db=db)

    result = await _route(
        router, "/students/{student_id}", "GET"
    ).endpoint("student-inactive-legacy", None)

    assert isinstance(result, Student)
    assert result.status == "inactive"
    assert db.students.find_calls == 1
