"""Regressões do P0 que protege students.enrollment_number na edição genérica."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import APIRouter, Request

from models import StudentUpdate
from routers.student_enrollment_identity_guard import (
    ROUTE_METHOD,
    ROUTE_PATH,
    install_student_enrollment_identity_guard,
    sanitize_student_update,
)


def _dump_unset(model):
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_unset=True)
    return model.dict(exclude_unset=True)


def _put_routes(router):
    return [
        route
        for route in router.routes
        if getattr(route, "path", None) == ROUTE_PATH
        and ROUTE_METHOD in (getattr(route, "methods", set()) or set())
    ]


def test_sanitize_discards_client_enrollment_number_and_preserves_other_fields():
    incoming = StudentUpdate(
        enrollment_number="202699999",
        full_name="Aluno Teste",
        observations="edição cadastral",
    )

    safe = sanitize_student_update(incoming)
    payload = _dump_unset(safe)

    assert "enrollment_number" not in payload
    assert payload["full_name"] == "Aluno Teste"
    assert payload["observations"] == "edição cadastral"


def test_sanitize_explicit_null_does_not_turn_into_unset_or_clear_projection():
    incoming = StudentUpdate(enrollment_number=None, observations="somente observação")

    safe = sanitize_student_update(incoming)
    payload = _dump_unset(safe)

    assert "enrollment_number" not in payload
    assert payload == {"observations": "somente observação"}


@pytest.mark.asyncio
async def test_guard_delegates_to_legacy_endpoint_without_client_number():
    router = APIRouter(prefix="/students")
    seen = {}

    @router.put("/{student_id}")
    async def update_student(
        student_id: str,
        student_update: StudentUpdate,
        request: Request,
    ):
        seen["student_id"] = student_id
        seen["payload"] = _dump_unset(student_update)
        return {"ok": True}

    assert len(_put_routes(router)) == 1

    install_student_enrollment_identity_guard(router)

    routes = _put_routes(router)
    assert len(routes) == 1

    result = await routes[0].endpoint(
        "student-1",
        StudentUpdate(
            enrollment_number="CLIENTE-NAO-E-FONTE",
            full_name="Nome preservado",
        ),
        None,
    )

    assert result == {"ok": True}
    assert seen["student_id"] == "student-1"
    assert seen["payload"]["full_name"] == "Nome preservado"
    assert "enrollment_number" not in seen["payload"]


def test_guard_installation_is_idempotent():
    router = APIRouter(prefix="/students")

    @router.put("/{student_id}")
    async def update_student(
        student_id: str,
        student_update: StudentUpdate,
        request: Request,
    ):
        return {"id": student_id}

    install_student_enrollment_identity_guard(router)
    first_endpoint = _put_routes(router)[0].endpoint

    install_student_enrollment_identity_guard(router)

    routes = _put_routes(router)
    assert len(routes) == 1
    assert routes[0].endpoint is first_endpoint


def test_guard_has_no_database_write_primitives_and_is_wired_before_server_import():
    backend = Path(__file__).resolve().parents[1]
    guard_source = (
        backend / "routers" / "student_enrollment_identity_guard.py"
    ).read_text(encoding="utf-8")
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
        assert primitive not in guard_source

    assert "setup_students_router as _setup_students_router" in init_source
    assert "install_student_enrollment_identity_guard" in init_source
    assert "def setup_students_router(" in init_source
    assert "configured = _setup_students_router(" in init_source
    assert "return install_student_enrollment_identity_guard(configured)" in init_source
