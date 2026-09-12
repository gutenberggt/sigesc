from types import SimpleNamespace

import pytest

from services.class_details_roster import build_class_students


class FakeCursor:
    def __init__(self, items):
        self.items = list(items)

    async def to_list(self, _limit):
        return list(self.items)

    def sort(self, *_args, **_kwargs):
        return self

    def collation(self, *_args, **_kwargs):
        return self


class EnrollmentCollection:
    def __init__(self, active, inactive):
        self.active = active
        self.inactive = inactive

    def find(self, query, _projection):
        if query.get("status") == "active":
            return FakeCursor(self.active)
        return FakeCursor(self.inactive)


class StudentCollection:
    def __init__(self, students):
        self.students = students

    def find(self, query, _projection):
        if "class_id" in query or "atendimento_programa_class_id" in query:
            return FakeCursor([])
        requested = set((query.get("id") or {}).get("$in") or [])
        return FakeCursor([student for student in self.students if student["id"] in requested])

    async def find_one(self, *_args, **_kwargs):
        return None


class HistoryCollection:
    def __init__(self, entries):
        self.entries = entries

    def find(self, _query, _projection):
        return FakeCursor(self.entries)


class EmptyCollection:
    def find(self, *_args, **_kwargs):
        return FakeCursor([])


@pytest.mark.asyncio
async def test_roster_keeps_moved_students_and_series():
    active = [
        {
            "student_id": "active",
            "enrollment_number": "1",
            "student_series": "6º ANO",
            "academic_year": 2026,
        }
    ]
    inactive = [
        {"student_id": "transferred", "enrollment_number": "2", "student_series": "6º ANO", "academic_year": 2026},
        {"student_id": "relocated", "enrollment_number": "3", "student_series": "7º ANO", "academic_year": 2026},
        {"student_id": "progressed", "enrollment_number": "4", "student_series": "6º ANO", "academic_year": 2026},
        {"student_id": "dropout", "enrollment_number": "5", "student_series": "7º ANO", "academic_year": 2026},
        {"student_id": "reclassified", "enrollment_number": "6", "student_series": "6º ANO", "academic_year": 2026},
    ]
    students = [
        {
            "id": sid,
            "full_name": sid.title(),
            "birth_date": "2013-01-01",
            "guardian_name": "Responsável",
            "guardian_phone": "",
            "enrollment_number": None,
        }
        for sid in ["active", "transferred", "relocated", "progressed", "dropout", "reclassified"]
    ]
    history = [
        {"student_id": "transferred", "action_type": "transferencia_saida", "action_date": "2026-03-01"},
        {"student_id": "relocated", "action_type": "remanejamento", "action_date": "2026-03-02"},
        {"student_id": "progressed", "action_type": "progressao", "action_date": "2026-03-03"},
        {"student_id": "dropout", "action_type": "desistencia", "action_date": "2026-03-04"},
        {"student_id": "reclassified", "action_type": "reclassificacao", "action_date": "2026-03-05"},
    ]

    db = SimpleNamespace(
        enrollments=EnrollmentCollection(active, inactive),
        students=StudentCollection(students),
        student_history=HistoryCollection(history),
        planos_aee=EmptyCollection(),
        atendimentos_aee=EmptyCollection(),
    )
    class_doc = {
        "id": "class-1",
        "school_id": "school-1",
        "academic_year": 2026,
        "grade_level": "6º ANO",
        "is_multi_grade": True,
        "series": ["6º ANO", "7º ANO"],
    }

    roster = await build_class_students(db, class_doc)
    by_id = {student["id"]: student for student in roster}

    assert set(by_id) == {
        "active",
        "transferred",
        "relocated",
        "progressed",
        "dropout",
        "reclassified",
    }
    assert by_id["transferred"]["action_label"] == "Transferido"
    assert by_id["relocated"]["action_label"] == "Remanejado"
    assert by_id["progressed"]["action_label"] == "Progredido"
    assert by_id["dropout"]["action_label"] == "Desistente"
    assert by_id["reclassified"]["action_label"] == "Reclassificado"
    assert by_id["relocated"]["student_series"] == "7º ANO"
