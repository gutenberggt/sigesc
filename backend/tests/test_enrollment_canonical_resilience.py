"""Resiliência adicional do contrato canônico de matrículas."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from services.enrollment_service import (
    EnrollmentConflictError,
    EnrollmentValidationError,
    create_active_enrollment,
)


class _Result:
    def __init__(self, matched=1, deleted=0):
        self.matched_count = matched
        self.deleted_count = deleted


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, length=None):
        return deepcopy(self.docs if length is None else self.docs[:length])


class _Collection:
    def __init__(self, docs=None, *, fail_update=False):
        self.docs = [deepcopy(d) for d in (docs or [])]
        self.fail_update = fail_update

    async def find_one(self, query, projection=None, **kwargs):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items() if not k.startswith("$")):
                return deepcopy(doc)
        return None

    def find(self, query, projection=None):
        docs = []
        for doc in self.docs:
            ok = True
            for key, value in query.items():
                if key.startswith("$"):
                    continue
                if doc.get(key) != value:
                    ok = False
                    break
            if ok:
                docs.append(doc)
        return _Cursor(docs)

    async def insert_one(self, doc):
        self.docs.append(deepcopy(doc))
        return _Result()

    async def update_one(self, query, update):
        if self.fail_update:
            raise RuntimeError("projection write failed")
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items() if not k.startswith("$")):
                for key, value in update.get("$set", {}).items():
                    doc[key] = deepcopy(value)
                for key in update.get("$unset", {}):
                    doc.pop(key, None)
                return _Result(matched=1)
        return _Result(matched=0)

    async def delete_one(self, query):
        for idx, doc in enumerate(self.docs):
            if all(doc.get(k) == v for k, v in query.items() if not k.startswith("$")):
                self.docs.pop(idx)
                return _Result(deleted=1)
        return _Result(deleted=0)


class _DB:
    def __init__(self, *, student, school, classes, enrollments=None, fail_student_update=False):
        self.students = _Collection([student], fail_update=fail_student_update)
        self.schools = _Collection([school])
        self.classes = _Collection(classes)
        self.enrollments = _Collection(enrollments or [])


def _student(tenant="tenant"):
    doc = {"id": "student", "school_id": "school", "status": "inactive"}
    if tenant is not None:
        doc["mantenedora_id"] = tenant
    return doc


def _school(tenant="tenant"):
    doc = {"id": "school"}
    if tenant is not None:
        doc["mantenedora_id"] = tenant
    return doc


def _regular(class_id="regular", tenant="tenant"):
    doc = {
        "id": class_id,
        "school_id": "school",
        "academic_year": 2026,
        "grade_level": "5º Ano",
        "atendimento_programa": "",
    }
    if tenant is not None:
        doc["mantenedora_id"] = tenant
    return doc


@pytest.mark.asyncio
async def test_regular_insert_is_compensated_if_student_projection_fails():
    db = _DB(
        student=_student(),
        school=_school(),
        classes=[_regular()],
        fail_student_update=True,
    )

    with pytest.raises(RuntimeError, match="projection write failed"):
        await create_active_enrollment(
            db,
            student_id="student",
            school_id="school",
            class_id="regular",
            academic_year=2026,
            enrollment_number="2026-000100",
        )

    # A falha da segunda escrita não pode deixar um enrollment órfão do commit lógico.
    assert db.enrollments.docs == []


@pytest.mark.asyncio
async def test_new_enrollment_requires_resolvable_tenant():
    db = _DB(
        student=_student(tenant=None),
        school=_school(tenant=None),
        classes=[_regular(tenant=None)],
    )

    with pytest.raises(EnrollmentValidationError, match="mantenedora"):
        await create_active_enrollment(
            db,
            student_id="student",
            school_id="school",
            class_id="regular",
            academic_year=2026,
            enrollment_number="2026-000101",
        )


@pytest.mark.asyncio
async def test_broken_active_class_blocks_new_special_enrollment():
    aee = {
        "id": "aee",
        "school_id": "school",
        "academic_year": 2026,
        "grade_level": "AEE",
        "atendimento_programa": "aee",
        "mantenedora_id": "tenant",
    }
    db = _DB(
        student={**_student(), "status": "active"},
        school=_school(),
        classes=[aee],
        enrollments=[{
            "id": "broken",
            "student_id": "student",
            "school_id": "school",
            "class_id": "missing-class",
            "academic_year": 2026,
            "status": "active",
            "mantenedora_id": "tenant",
        }],
    )

    with pytest.raises(EnrollmentConflictError, match="turma inexistente"):
        await create_active_enrollment(
            db,
            student_id="student",
            school_id="school",
            class_id="aee",
            academic_year=2026,
            enrollment_number="2026-000102",
        )


def test_pre_matricula_ui_requires_regular_class():
    root = Path(__file__).resolve().parents[2]
    frontend = (
        root / "frontend" / "src" / "pages" / "PreMatriculaManagement.jsx"
    ).read_text(encoding="utf-8")

    assert "SPECIAL_ENROLLMENT_PROGRAMS" in frontend
    assert "Turma regular" in frontend
    assert "disabled={converting || !selectedClassId}" in frontend
    assert "Selecione uma turma regular" in frontend
    assert "Selecionar turma depois" not in frontend
