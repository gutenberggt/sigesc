"""Regressões da Fase 1 de continuidade da identidade institucional."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import APIRouter, Request

from models import Student, StudentUpdate
from routers.student_enrollment_identity_continuity import (
    EnrollmentIdentityContinuityConflict,
    TRANSFER_ROUTE_PATH,
    UPDATE_ROUTE_PATH,
    choose_identity_number,
    install_student_enrollment_identity_continuity,
)
from utils.enrollment import (
    enrollment_number_override_once,
    generate_enrollment_number,
)


@pytest.mark.asyncio
async def test_context_override_preserves_original_number_even_in_later_academic_year():
    calls = []

    async def resolver(db, academic_year):
        calls.append((db, academic_year))
        return "202602386"

    fake_db = object()
    with enrollment_number_override_once(resolver) as state:
        number = await generate_enrollment_number(fake_db, 2027)

    assert number == "202602386"
    assert calls == [(fake_db, 2027)]
    assert state.consumed is True
    assert state.resolved_number == "202602386"


@pytest.mark.asyncio
async def test_context_override_none_falls_back_to_atomic_generator():
    class FakeCounters:
        async def find_one(self, query):
            return {"_id": query["_id"], "sequence": 10}

        async def find_one_and_update(self, query, update, return_document=None):
            return {"_id": query["_id"], "sequence": 11}

    class FakeDb:
        enrollment_counters = FakeCounters()

    async def resolver(db, academic_year):
        return None

    with enrollment_number_override_once(resolver) as state:
        number = await generate_enrollment_number(FakeDb(), 2027)

    assert number == "202700011"
    assert state.consumed is True
    assert state.resolved_number is None


def test_choose_identity_prefers_unique_canonical_enrollment_without_log():
    number, basis = choose_identity_number(
        student_number="202606707",
        enrollment_numbers={"202602386"},
        logged_number="",
    )
    assert number == "202602386"
    assert basis == "ENROLLMENT_CANONICO_SEM_LOG"


def test_choose_identity_accepts_log_that_confirms_canonical_enrollment():
    number, basis = choose_identity_number(
        student_number="202606707",
        enrollment_numbers={"202602386"},
        logged_number="202602386",
    )
    assert number == "202602386"
    assert basis == "LOG_ORIGINAL_CONFIRMA_ENROLLMENT"


def test_choose_identity_blocks_when_log_confirms_divergent_student_projection():
    with pytest.raises(EnrollmentIdentityContinuityConflict):
        choose_identity_number(
            student_number="202607309",
            enrollment_numbers={"202607328"},
            logged_number="202607309",
        )


def test_choose_identity_blocks_third_historical_number():
    with pytest.raises(EnrollmentIdentityContinuityConflict):
        choose_identity_number(
            student_number="202604876",
            enrollment_numbers={"202603749"},
            logged_number="202603461",
        )


def test_choose_identity_blocks_multiple_enrollment_identities():
    with pytest.raises(EnrollmentIdentityContinuityConflict):
        choose_identity_number(
            student_number="202600001",
            enrollment_numbers={"202600001", "202600002"},
            logged_number="202600001",
        )


def test_choose_identity_uses_student_only_when_no_enrollment_identity_exists():
    number, basis = choose_identity_number(
        student_number="202500777",
        enrollment_numbers=set(),
        logged_number="",
    )
    assert number == "202500777"
    assert basis == "STUDENT_ONLY"


def test_choose_identity_without_history_allows_fresh_atomic_generation():
    number, basis = choose_identity_number(
        student_number="",
        enrollment_numbers=set(),
        logged_number="",
    )
    assert number is None
    assert basis == "SEM_IDENTIDADE_ANTERIOR"


def _routes(router, path, method):
    return [
        route
        for route in router.routes
        if getattr(route, "path", None) == path
        and method in (getattr(route, "methods", set()) or set())
    ]


def test_continuity_installer_wraps_only_expected_student_routes_and_is_idempotent():
    router = APIRouter(prefix="/students")

    @router.put("/{student_id}", response_model=Student)
    async def update_student(
        student_id: str,
        student_update: StudentUpdate,
        request: Request,
    ):
        return {"id": student_id}

    @router.post("/{student_id}/transfer")
    async def transfer_student(student_id: str, request: Request):
        return {"id": student_id}

    install_student_enrollment_identity_continuity(router, object(), object())
    first_update = _routes(router, UPDATE_ROUTE_PATH, "PUT")[0].endpoint
    first_transfer = _routes(router, TRANSFER_ROUTE_PATH, "POST")[0].endpoint

    install_student_enrollment_identity_continuity(router, object(), object())

    assert len(_routes(router, UPDATE_ROUTE_PATH, "PUT")) == 1
    assert len(_routes(router, TRANSFER_ROUTE_PATH, "POST")) == 1
    assert _routes(router, UPDATE_ROUTE_PATH, "PUT")[0].endpoint is first_update
    assert _routes(router, TRANSFER_ROUTE_PATH, "POST")[0].endpoint is first_transfer


def test_wiring_keeps_p0_before_p1_and_students_router_legacy_untouched():
    backend = Path(__file__).resolve().parents[1]
    init_source = (backend / "routers" / "__init__.py").read_text(encoding="utf-8")
    continuity_source = (
        backend / "routers" / "student_enrollment_identity_continuity.py"
    ).read_text(encoding="utf-8")

    assert "install_student_enrollment_identity_guard(configured)" in init_source
    assert "install_student_enrollment_identity_continuity(configured, db, audit_service)" in init_source
    assert init_source.index("install_student_enrollment_identity_guard(configured)") < init_source.index(
        "install_student_enrollment_identity_continuity(configured, db, audit_service)"
    )
    assert "enrollment_number_override_once" in continuity_source
    assert "TARGET_NUMBER" not in continuity_source  # não acopla ao manifesto Fase 0
