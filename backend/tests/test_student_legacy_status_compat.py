import pytest
from fastapi import APIRouter, HTTPException, Request
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


def _request_for_tenant(tenant_id="tenant-1"):
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/students/student-inactive-legacy",
            "query_string": b"",
            "headers": [(b"x-mantenedora-id", tenant_id.encode("utf-8"))],
            "scheme": "https",
            "server": ("testserver", 443),
            "client": ("127.0.0.1", 12345),
        }
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
def test_known_legacy_statuses_are_mapped_only_when_building_student(legacy, canonical):
    source = {
        "id": "student-legacy-status",
        "full_name": "Estudante Legado",
        "status": legacy,
    }

    generic_projection = normalize_legacy_student_doc(source)
    typed_student = build_compatible_student(source)

    assert source["status"] == legacy
    # Contrato de rematrícula/transferência continua vendo o valor histórico bruto.
    assert generic_projection["status"] == legacy
    # Só a resposta tipada do cadastro completo usa o Literal canônico.
    assert typed_student.status == canonical


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

    generic_projection = normalize_legacy_student_doc(source)

    assert generic_projection["status"] == "situacao_desconhecida"
    with pytest.raises(ValidationError):
        build_compatible_student(source)


class _FakeStudents:
    def __init__(self, doc):
        self.doc = doc
        self.find_calls = 0

    async def find_one(self, query, projection):
        self.find_calls += 1
        assert query == {"id": self.doc["id"]}
        assert projection == {"_id": 0}
        return dict(self.doc)


class _FakeSchools:
    def __init__(self, school=None):
        self.school = school
        self.find_calls = 0

    async def find_one(self, query, projection):
        self.find_calls += 1
        assert projection == {"_id": 0, "id": 1}
        return dict(self.school) if self.school else None


class _FakeDB:
    def __init__(self, doc, school=None):
        self.students = _FakeStudents(doc)
        self.schools = _FakeSchools(school)


def _install_router_that_fails_school_lookup(db):
    router = APIRouter(prefix="/students")

    @router.get("/{student_id}", response_model=Student)
    async def get_student(student_id: str, request: Request):
        raise HTTPException(status_code=404, detail="Escola não encontrada")

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

    install_student_legacy_compat(router, db=db)
    return router


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


@pytest.mark.asyncio
async def test_super_admin_can_open_inactive_without_current_school(monkeypatch):
    doc = {
        "id": "student-inactive-legacy",
        "full_name": "Estudante Inativo Legado",
        "status": "Inativo",
        "school_id": None,
        "mantenedora_id": "tenant-1",
        "address": {},
    }
    db = _FakeDB(doc)

    async def fake_current_user(request):
        return {
            "id": "super-admin-1",
            "role": "super_admin",
            "is_sandbox": False,
        }

    monkeypatch.setattr(AuthMiddleware, "get_current_user", fake_current_user)
    router = _install_router_that_fails_school_lookup(db)

    result = await _route(router, "/students/{student_id}", "GET").endpoint(
        doc["id"], _request_for_tenant("tenant-1")
    )

    assert isinstance(result, Student)
    assert result.status == "inactive"
    assert result.school_id is None
    assert db.students.find_calls == 1
    assert db.schools.find_calls == 0


@pytest.mark.asyncio
async def test_super_admin_inactive_without_school_stays_fail_closed_cross_tenant(monkeypatch):
    doc = {
        "id": "student-inactive-legacy",
        "full_name": "Estudante Inativo Legado",
        "status": "inactive",
        "school_id": None,
        "mantenedora_id": "tenant-2",
        "address": {},
    }
    db = _FakeDB(doc)

    async def fake_current_user(request):
        return {
            "id": "super-admin-1",
            "role": "super_admin",
            "is_sandbox": False,
        }

    monkeypatch.setattr(AuthMiddleware, "get_current_user", fake_current_user)
    router = _install_router_that_fails_school_lookup(db)

    with pytest.raises(HTTPException) as caught:
        await _route(router, "/students/{student_id}", "GET").endpoint(
            doc["id"], _request_for_tenant("tenant-1")
        )

    assert caught.value.status_code == 403
    assert caught.value.detail == "Registro pertence a outra mantenedora"


@pytest.mark.asyncio
async def test_active_student_without_school_does_not_receive_inactive_exception(monkeypatch):
    doc = {
        "id": "student-inactive-legacy",
        "full_name": "Estudante Ativo",
        "status": "active",
        "school_id": None,
        "mantenedora_id": "tenant-1",
        "address": {},
    }
    db = _FakeDB(doc)

    async def fake_current_user(request):
        return {
            "id": "super-admin-1",
            "role": "super_admin",
            "is_sandbox": False,
        }

    monkeypatch.setattr(AuthMiddleware, "get_current_user", fake_current_user)
    router = _install_router_that_fails_school_lookup(db)

    with pytest.raises(HTTPException) as caught:
        await _route(router, "/students/{student_id}", "GET").endpoint(
            doc["id"], _request_for_tenant("tenant-1")
        )

    assert caught.value.status_code == 404
    assert caught.value.detail == "Escola não encontrada"


@pytest.mark.asyncio
async def test_non_super_admin_inactive_without_school_keeps_original_denial(monkeypatch):
    doc = {
        "id": "student-inactive-legacy",
        "full_name": "Estudante Inativo",
        "status": "inactive",
        "school_id": None,
        "mantenedora_id": "tenant-1",
        "address": {},
    }
    db = _FakeDB(doc)

    async def fake_current_user(request):
        return {
            "id": "admin-1",
            "role": "admin",
            "mantenedora_id": "tenant-1",
            "is_sandbox": False,
        }

    monkeypatch.setattr(AuthMiddleware, "get_current_user", fake_current_user)
    router = _install_router_that_fails_school_lookup(db)

    with pytest.raises(HTTPException) as caught:
        await _route(router, "/students/{student_id}", "GET").endpoint(
            doc["id"], _request_for_tenant("tenant-1")
        )

    assert caught.value.status_code == 404
    assert caught.value.detail == "Escola não encontrada"
