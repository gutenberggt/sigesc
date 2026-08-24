"""Guards unitários da fonte canônica de matrículas.

Testes puros: não usam Mongo real, servidor HTTP nem conftest de integração.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from services.enrollment_service import (
    EnrollmentConflictError,
    EnrollmentValidationError,
    canonicalize_enrollment_status,
    create_active_enrollment,
    find_primary_active_enrollment,
)


class _Result:
    def __init__(self, *, matched=0, modified=0, deleted=0):
        self.matched_count = matched
        self.modified_count = modified
        self.deleted_count = deleted


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, length=None):
        docs = self.docs if length is None else self.docs[:length]
        return deepcopy(docs)


def _match_value(actual, expected, exists=True):
    if not isinstance(expected, dict):
        return actual == expected
    for op, value in expected.items():
        if op == "$ne" and actual == value:
            return False
        if op == "$in" and actual not in value:
            return False
        if op == "$exists" and bool(value) != exists:
            return False
    return True


def _matches(doc, query):
    if "$and" in query and not all(_matches(doc, part) for part in query["$and"]):
        return False
    if "$or" in query and not any(_matches(doc, part) for part in query["$or"]):
        return False
    for key, expected in query.items():
        if key.startswith("$"):
            continue
        exists = key in doc
        if not _match_value(doc.get(key), expected, exists=exists):
            return False
    return True


class _Collection:
    def __init__(self, docs=None):
        self.docs = [deepcopy(d) for d in (docs or [])]

    async def find_one(self, query, projection=None, **kwargs):
        for doc in self.docs:
            if _matches(doc, query):
                return deepcopy(doc)
        return None

    def find(self, query, projection=None):
        return _Cursor([d for d in self.docs if _matches(d, query)])

    async def insert_one(self, doc):
        self.docs.append(deepcopy(doc))
        return _Result()

    async def update_one(self, query, update):
        for doc in self.docs:
            if not _matches(doc, query):
                continue
            for key, value in update.get("$set", {}).items():
                doc[key] = deepcopy(value)
            for key in update.get("$unset", {}):
                doc.pop(key, None)
            return _Result(matched=1, modified=1)
        return _Result()

    async def delete_one(self, query):
        for idx, doc in enumerate(self.docs):
            if _matches(doc, query):
                self.docs.pop(idx)
                return _Result(deleted=1)
        return _Result()

    async def count_documents(self, query):
        return sum(1 for d in self.docs if _matches(d, query))


class _DB:
    def __init__(self, *, students=None, schools=None, classes=None, enrollments=None):
        self.students = _Collection(students)
        self.schools = _Collection(schools)
        self.classes = _Collection(classes)
        self.enrollments = _Collection(enrollments)


def _regular_class(class_id="regular", school_id="school", tenant="tenant"):
    return {
        "id": class_id,
        "school_id": school_id,
        "academic_year": 2026,
        "grade_level": "5º Ano",
        "atendimento_programa": "",
        "mantenedora_id": tenant,
    }


def _student(class_id=None, status="inactive"):
    return {
        "id": "student",
        "school_id": "school",
        "class_id": class_id,
        "status": status,
        "mantenedora_id": "tenant",
    }


@pytest.mark.asyncio
async def test_regular_enrollment_is_canonical_and_projects_home_class():
    db = _DB(
        students=[_student()],
        schools=[{"id": "school", "mantenedora_id": "tenant"}],
        classes=[_regular_class()],
    )

    result = await create_active_enrollment(
        db,
        student_id="student",
        school_id="school",
        class_id="regular",
        academic_year=2026,
        enrollment_number="2026-000001",
        source="unit_test",
    )

    assert result["is_special"] is False
    assert result["enrollment"]["mantenedora_id"] == "tenant"
    assert db.enrollments.docs[0]["class_id"] == "regular"
    assert db.students.docs[0]["class_id"] == "regular"
    assert db.students.docs[0]["status"] == "active"
    assert db.students.docs[0]["enrollment_number"] == "2026-000001"


@pytest.mark.asyncio
async def test_special_enrollment_never_overwrites_regular_home_class():
    regular = _regular_class()
    special = {
        "id": "aee",
        "school_id": "school",
        "academic_year": 2026,
        "grade_level": "AEE",
        "atendimento_programa": "aee",
        "mantenedora_id": "tenant",
    }
    db = _DB(
        students=[_student(class_id="regular", status="active")],
        schools=[{"id": "school", "mantenedora_id": "tenant"}],
        classes=[regular, special],
        enrollments=[{
            "id": "regular-enr",
            "student_id": "student",
            "school_id": "school",
            "class_id": "regular",
            "academic_year": 2026,
            "status": "active",
            "enrollment_number": "2026-000001",
            "mantenedora_id": "tenant",
        }],
    )

    result = await create_active_enrollment(
        db,
        student_id="student",
        school_id="school",
        class_id="aee",
        academic_year=2026,
        enrollment_number="2026-000002",
    )

    assert result["is_special"] is True
    assert result["program"] == "aee"
    assert len(db.enrollments.docs) == 2
    # Invariante crítica: AEE não vira a home class do estudante.
    assert db.students.docs[0]["class_id"] == "regular"
    assert db.students.docs[0].get("enrollment_number") != "2026-000002"


@pytest.mark.asyncio
async def test_special_requires_primary_regular_enrollment():
    special = {
        "id": "reforco",
        "school_id": "school",
        "academic_year": 2026,
        "atendimento_programa": "reforco_escolar",
        "mantenedora_id": "tenant",
    }
    db = _DB(
        students=[_student()],
        schools=[{"id": "school", "mantenedora_id": "tenant"}],
        classes=[special],
    )

    with pytest.raises(EnrollmentValidationError):
        await create_active_enrollment(
            db,
            student_id="student",
            school_id="school",
            class_id="reforco",
            academic_year=2026,
            enrollment_number="2026-000003",
        )


@pytest.mark.asyncio
async def test_second_regular_enrollment_same_year_is_blocked():
    first = _regular_class("regular-1")
    second = _regular_class("regular-2")
    db = _DB(
        students=[_student(class_id="regular-1", status="active")],
        schools=[{"id": "school", "mantenedora_id": "tenant"}],
        classes=[first, second],
        enrollments=[{
            "id": "enr-1",
            "student_id": "student",
            "school_id": "school",
            "class_id": "regular-1",
            "academic_year": 2026,
            "status": "active",
            "mantenedora_id": "tenant",
        }],
    )

    with pytest.raises(EnrollmentConflictError):
        await create_active_enrollment(
            db,
            student_id="student",
            school_id="school",
            class_id="regular-2",
            academic_year=2026,
            enrollment_number="2026-000004",
        )


@pytest.mark.asyncio
async def test_primary_reader_ignores_special_enrollment():
    db = _DB(
        students=[_student(class_id="regular", status="active")],
        schools=[{"id": "school", "mantenedora_id": "tenant"}],
        classes=[
            _regular_class(),
            {
                "id": "aee",
                "school_id": "school",
                "academic_year": 2026,
                "atendimento_programa": "aee",
                "mantenedora_id": "tenant",
            },
        ],
        enrollments=[
            {
                "id": "special-newer",
                "student_id": "student",
                "class_id": "aee",
                "school_id": "school",
                "academic_year": 2026,
                "status": "active",
                "enrollment_date": "2026-08-20",
            },
            {
                "id": "regular-enr",
                "student_id": "student",
                "class_id": "regular",
                "school_id": "school",
                "academic_year": 2026,
                "status": "active",
                "enrollment_date": "2026-02-01",
            },
        ],
    )

    primary = await find_primary_active_enrollment(db, "student")
    assert primary["id"] == "regular-enr"


def test_legacy_status_is_normalized_on_write_contract():
    assert canonicalize_enrollment_status("reclassified") == "progressed"
    assert canonicalize_enrollment_status("inactive") == "cancelled"
    with pytest.raises(EnrollmentValidationError):
        canonicalize_enrollment_status("status_inventado")


def test_routers_follow_canonical_contract_statically():
    backend = Path(__file__).resolve().parents[1]
    pre = (backend / "routers" / "pre_matricula.py").read_text(encoding="utf-8")
    enr = (backend / "routers" / "enrollments.py").read_text(encoding="utf-8")
    docs = (backend / "services" / "school_docs_service.py").read_text(encoding="utf-8")

    assert "create_active_enrollment(" in pre
    assert '"converted_enrollment_id"' in pre
    assert "generate_enrollment_number" not in pre

    assert "create_active_enrollment(" in enr
    assert "await db.enrollments.insert_one" not in enr

    # class_students deixa de ser fonte operacional para declaração escolar.
    assert "db.class_students" not in docs
    assert "find_primary_active_enrollment" in docs
