"""Regressões P1: matrícula de transferido pela escola de destino."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import APIRouter, HTTPException, Request

from auth_middleware import AuthMiddleware
from models import StudentUpdate
from routers.student_transfer_destination_access import (
    ROUTE_PATH,
    install_student_transfer_destination_access,
)


TENANT = "tenant-1"
SOURCE_SCHOOL = "school-source"
TARGET_SCHOOL = "school-target"
OTHER_SCHOOL = "school-other"


class _StudentsCollection:
    def __init__(self, doc):
        self.doc = doc

    async def find_one(self, query, projection=None):
        if not self.doc or query.get("id") != self.doc.get("id"):
            return None
        return dict(self.doc)


class _DB:
    def __init__(self, student_doc):
        self.students = _StudentsCollection(student_doc)


def _request():
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "query_string": b"",
    })


def _routes(router, method):
    return [
        route
        for route in router.routes
        if getattr(route, "path", None) == ROUTE_PATH
        and method in (getattr(route, "methods", set()) or set())
    ]


def _student(*, status="transferred", tenant=TENANT):
    return {
        "id": "student-1",
        "full_name": "Aluno Transferido",
        "status": status,
        "school_id": SOURCE_SCHOOL,
        "class_id": "class-source",
        "mantenedora_id": tenant,
    }


def _secretary(*, tenant=TENANT):
    return {
        "id": "secretary-1",
        "email": "secretary@example.test",
        "role": "secretario",
        "school_ids": [TARGET_SCHOOL],
        "mantenedora_id": tenant,
        "is_sandbox": False,
    }


def _install_router(db, seen):
    router = APIRouter(prefix="/students")

    @router.get("/{student_id}")
    async def get_student(student_id: str, request: Request):
        seen["legacy_get_calls"] = seen.get("legacy_get_calls", 0) + 1
        return {"legacy": True, "id": student_id}

    @router.put("/{student_id}")
    async def update_student(
        student_id: str,
        student_update: StudentUpdate,
        request: Request,
    ):
        seen["legacy_put_calls"] = seen.get("legacy_put_calls", 0) + 1
        seen["payload"] = student_update.model_dump(exclude_unset=True)
        return {"legacy": True, "id": student_id}

    install_student_transfer_destination_access(router, db)
    return router


@pytest.mark.asyncio
async def test_secretary_can_load_transferred_student_from_other_school_same_tenant(monkeypatch):
    seen = {}
    db = _DB(_student())
    router = _install_router(db, seen)

    async def fake_current_user(request):
        return _secretary()

    monkeypatch.setattr(AuthMiddleware, "get_current_user", staticmethod(fake_current_user))

    result = await _routes(router, "GET")[0].endpoint("student-1", _request())

    assert result["id"] == "student-1"
    assert result["status"] == "transferred"
    assert result["school_id"] == SOURCE_SCHOOL
    assert seen.get("legacy_get_calls", 0) == 0


@pytest.mark.asyncio
async def test_secretary_cannot_load_transferred_student_from_other_tenant(monkeypatch):
    seen = {}
    db = _DB(_student(tenant="tenant-other"))
    router = _install_router(db, seen)

    async def fake_current_user(request):
        return _secretary()

    monkeypatch.setattr(AuthMiddleware, "get_current_user", staticmethod(fake_current_user))

    with pytest.raises(HTTPException) as exc:
        await _routes(router, "GET")[0].endpoint("student-1", _request())

    assert exc.value.status_code == 403
    assert "mantenedora" in str(exc.value.detail).lower()
    assert seen.get("legacy_get_calls", 0) == 0


@pytest.mark.asyncio
async def test_secretary_cannot_load_transferred_student_without_explicit_tenant(monkeypatch):
    seen = {}
    doc = _student()
    doc.pop("mantenedora_id")
    db = _DB(doc)
    router = _install_router(db, seen)

    async def fake_current_user(request):
        return _secretary()

    monkeypatch.setattr(AuthMiddleware, "get_current_user", staticmethod(fake_current_user))

    with pytest.raises(HTTPException) as exc:
        await _routes(router, "GET")[0].endpoint("student-1", _request())

    assert exc.value.status_code == 403
    assert seen.get("legacy_get_calls", 0) == 0


@pytest.mark.asyncio
async def test_active_student_keeps_previous_school_authorization(monkeypatch):
    seen = {}
    db = _DB(_student(status="active"))
    router = _install_router(db, seen)

    async def fake_current_user(request):
        return _secretary()

    monkeypatch.setattr(AuthMiddleware, "get_current_user", staticmethod(fake_current_user))

    result = await _routes(router, "GET")[0].endpoint("student-1", _request())

    assert result == {"legacy": True, "id": "student-1"}
    assert seen["legacy_get_calls"] == 1


@pytest.mark.asyncio
async def test_transferred_legacy_student_is_normalized_before_response(monkeypatch):
    seen = {}
    doc = _student()
    doc.update({
        "address": "Rua Histórica",
        "address_number": "123",
        "neighborhood": "Centro",
        "city": "Floresta do Araguaia",
        "state": "PA",
        "civil_certificate_type": "",
        "comunidade_tradicional": "",
    })
    db = _DB(doc)
    router = _install_router(db, seen)

    async def fake_current_user(request):
        return _secretary()

    monkeypatch.setattr(AuthMiddleware, "get_current_user", staticmethod(fake_current_user))

    result = await _routes(router, "GET")[0].endpoint("student-1", _request())

    assert result["address"]["street"] == "Rua Histórica"
    assert result["address"]["number"] == "123"
    assert result["address"]["neighborhood"] == "Centro"
    assert result["civil_certificate_type"] is None
    assert result["comunidade_tradicional"] is None
    assert seen.get("legacy_get_calls", 0) == 0


@pytest.mark.asyncio
async def test_transfer_to_active_requires_access_to_destination_school(monkeypatch):
    seen = {}
    db = _DB(_student())
    router = _install_router(db, seen)

    async def fake_current_user(request):
        return _secretary()

    async def fake_verify_school_access(request, school_id):
        seen["verified_school_id"] = school_id
        if school_id != TARGET_SCHOOL:
            raise HTTPException(status_code=403, detail="Acesso negado a esta escola")
        return _secretary()

    monkeypatch.setattr(AuthMiddleware, "get_current_user", staticmethod(fake_current_user))
    monkeypatch.setattr(AuthMiddleware, "verify_school_access", staticmethod(fake_verify_school_access))

    result = await _routes(router, "PUT")[0].endpoint(
        "student-1",
        StudentUpdate(
            school_id=TARGET_SCHOOL,
            class_id="class-target",
            status="active",
        ),
        _request(),
    )

    assert result == {"legacy": True, "id": "student-1"}
    assert seen["verified_school_id"] == TARGET_SCHOOL
    assert seen["legacy_put_calls"] == 1


@pytest.mark.asyncio
async def test_transfer_to_unlinked_destination_is_blocked_before_previous_write(monkeypatch):
    seen = {}
    db = _DB(_student())
    router = _install_router(db, seen)

    async def fake_current_user(request):
        return _secretary()

    async def fake_verify_school_access(request, school_id):
        seen["verified_school_id"] = school_id
        raise HTTPException(status_code=403, detail="Acesso negado a esta escola")

    monkeypatch.setattr(AuthMiddleware, "get_current_user", staticmethod(fake_current_user))
    monkeypatch.setattr(AuthMiddleware, "verify_school_access", staticmethod(fake_verify_school_access))

    with pytest.raises(HTTPException) as exc:
        await _routes(router, "PUT")[0].endpoint(
            "student-1",
            StudentUpdate(
                school_id=OTHER_SCHOOL,
                class_id="class-other",
                status="active",
            ),
            _request(),
        )

    assert exc.value.status_code == 403
    assert seen["verified_school_id"] == OTHER_SCHOOL
    assert seen.get("legacy_put_calls", 0) == 0


@pytest.mark.asyncio
async def test_cadastral_edit_of_transferred_student_does_not_require_source_school_link(monkeypatch):
    seen = {}
    db = _DB(_student())
    router = _install_router(db, seen)

    async def fake_current_user(request):
        return _secretary()

    async def should_not_verify(request, school_id):
        raise AssertionError("edição cadastral não deve validar a escola histórica de origem")

    monkeypatch.setattr(AuthMiddleware, "get_current_user", staticmethod(fake_current_user))
    monkeypatch.setattr(AuthMiddleware, "verify_school_access", staticmethod(should_not_verify))

    result = await _routes(router, "PUT")[0].endpoint(
        "student-1",
        StudentUpdate(observations="Conferência cadastral antes da matrícula"),
        _request(),
    )

    assert result == {"legacy": True, "id": "student-1"}
    assert seen["legacy_put_calls"] == 1


def test_installation_is_idempotent_no_direct_writes_and_wired_after_legacy_compat():
    seen = {}
    db = _DB(_student())
    router = _install_router(db, seen)

    first_get = _routes(router, "GET")[0].endpoint
    first_put = _routes(router, "PUT")[0].endpoint

    install_student_transfer_destination_access(router, db)

    assert len(_routes(router, "GET")) == 1
    assert len(_routes(router, "PUT")) == 1
    assert _routes(router, "GET")[0].endpoint is first_get
    assert _routes(router, "PUT")[0].endpoint is first_put

    backend = Path(__file__).resolve().parents[1]
    source = (backend / "routers" / "student_transfer_destination_access.py").read_text(encoding="utf-8")
    init_source = (backend / "routers" / "__init__.py").read_text(encoding="utf-8")

    for primitive in (
        ".insert_one(",
        ".insert_many(",
        ".update_one(",
        ".update_many(",
        ".delete_one(",
        ".delete_many(",
        ".bulk_write(",
    ):
        assert primitive not in source

    legacy_call = "configured = install_student_legacy_compat(configured, db, sandbox_db)"
    destination_call = "return install_student_transfer_destination_access(configured, db, sandbox_db)"
    assert "install_student_transfer_destination_access" in init_source
    assert legacy_call in init_source
    assert destination_call in init_source
    assert init_source.index(legacy_call) < init_source.index(destination_call)
