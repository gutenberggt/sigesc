"""Regressão P0 do escopo Professor -> Turma AEE -> Estudante.

Sem MongoDB/HTTP real. Protege especificamente o incidente de 31/08/2026 em
que duas professoras da mesma escola podiam receber estudantes AEE de turmas
uma da outra e uma delas não recebia sua Turma AEE no seletor.
"""

import asyncio
import importlib.util
from pathlib import Path
import sys
import types


class FakeHTTPException(Exception):
    def __init__(self, status_code, detail=None):
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail


def _load_module():
    fastapi_stub = types.ModuleType("fastapi")
    fastapi_stub.HTTPException = FakeHTTPException
    fastapi_stub.Request = object

    auth_stub = types.ModuleType("auth_middleware")

    class FakeAuthMiddleware:
        pass

    auth_stub.AuthMiddleware = FakeAuthMiddleware

    old_modules = {
        name: sys.modules.get(name)
        for name in ("fastapi", "auth_middleware")
    }
    sys.modules["fastapi"] = fastapi_stub
    sys.modules["auth_middleware"] = auth_stub
    try:
        module_path = Path(__file__).resolve().parents[1] / "routers" / "aee_professor_scope_p0.py"
        spec = importlib.util.spec_from_file_location("aee_professor_scope_p0_under_test", module_path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        return module
    finally:
        for name, previous in old_modules.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


P0 = _load_module()
SOURCE = Path(__file__).resolve().parents[1] / "routers" / "aee_professor_scope_p0.py"


def _project(document, projection):
    if not projection:
        return dict(document)
    return {
        key: value
        for key, value in document.items()
        if key != "_id" and projection.get(key, 0)
    }


def _matches(document, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(_matches(document, branch) for branch in expected):
                return False
            continue
        if isinstance(expected, dict) and "$in" in expected:
            if document.get(key) not in expected["$in"]:
                return False
            continue
        if document.get(key) != expected:
            return False
    return True


class FakeCursor:
    def __init__(self, documents):
        self.documents = list(documents)

    async def to_list(self, length):
        return [dict(item) for item in self.documents[:length]]


class FakeCollection:
    def __init__(self, documents=None):
        self.documents = list(documents or [])

    async def find_one(self, query, projection=None):
        for document in self.documents:
            if _matches(document, query):
                return _project(document, projection)
        return None

    def find(self, query, projection=None):
        return FakeCursor(
            _project(document, projection)
            for document in self.documents
            if _matches(document, query)
        )


class FakeDB:
    def __init__(
        self,
        *,
        staff=None,
        assignments=None,
        plans=None,
        students=None,
        classes=None,
        schools=None,
        courses=None,
    ):
        self.staff = FakeCollection(staff)
        self.teacher_assignments = FakeCollection(assignments)
        self.planos_aee = FakeCollection(plans)
        self.students = FakeCollection(students)
        self.classes = FakeCollection(classes)
        self.schools = FakeCollection(schools)
        self.courses = FakeCollection(courses)


def _base_classes():
    return [
        {
            "id": "aee-matutino",
            "name": "AEE Matutino",
            "school_id": "school-1",
            "atendimento_programa": "aee",
        },
        {
            "id": "aee-vespertino",
            "name": "AEE Vespertino",
            "school_id": "school-1",
            "atendimento_programa": "aee",
        },
        {
            "id": "regular-1",
            "name": "3º Ano",
            "school_id": "school-1",
            "atendimento_programa": None,
        },
    ]


def test_each_professor_resolves_only_own_aee_class_from_assignment():
    db = FakeDB(
        staff=[
            {"id": "staff-a", "user_id": "user-a", "email": "a@test"},
            {"id": "staff-b", "user_id": "user-b", "email": "b@test"},
        ],
        assignments=[
            {
                "id": "ta-a",
                "staff_id": "staff-a",
                "class_id": "aee-matutino",
                "academic_year": 2026,
                "status": "ativo",
            },
            {
                "id": "ta-b",
                "staff_id": "staff-b",
                "class_id": "aee-vespertino",
                "academic_year": 2026,
                "status": "active",
            },
        ],
        classes=_base_classes(),
    )

    allowed_a = asyncio.run(
        P0.resolve_professor_aee_class_ids(
            db,
            {"id": "user-a", "email": "a@test", "role": "professor"},
            academic_year=2026,
            school_id="school-1",
        )
    )
    allowed_b = asyncio.run(
        P0.resolve_professor_aee_class_ids(
            db,
            {"id": "user-b", "email": "b@test", "role": "professor"},
            academic_year=2026,
            school_id="school-1",
        )
    )

    assert allowed_a == {"aee-matutino"}
    assert allowed_b == {"aee-vespertino"}


def test_historical_staff_id_in_plan_restores_aee_class_without_crossing_teacher():
    db = FakeDB(
        staff=[
            {"id": "staff-a", "user_id": "user-a", "email": "a@test"},
            {"id": "staff-b", "user_id": "user-b", "email": "b@test"},
        ],
        plans=[
            {
                "id": "plan-a",
                "student_id": "student-a",
                "school_id": "school-1",
                "academic_year": 2026,
                # legado: staff.id persistido onde hoje se espera user.id
                "professor_aee_id": "staff-a",
                "created_by": "admin-user",
            },
            {
                "id": "plan-b",
                "student_id": "student-b",
                "school_id": "school-1",
                "academic_year": 2026,
                "professor_aee_id": "staff-b",
                "created_by": "admin-user",
            },
        ],
        students=[
            {"id": "student-a", "atendimento_programa_class_id": "aee-matutino"},
            {"id": "student-b", "atendimento_programa_class_id": "aee-vespertino"},
        ],
        classes=_base_classes(),
    )

    allowed = asyncio.run(
        P0.resolve_professor_aee_class_ids(
            db,
            {"id": "user-a", "email": "a@test", "role": "professor"},
            academic_year=2026,
            school_id="school-1",
        )
    )

    assert allowed == {"aee-matutino"}


def test_resolver_rejects_regular_class_and_other_school():
    classes = _base_classes() + [
        {
            "id": "aee-other-school",
            "name": "AEE Outra Escola",
            "school_id": "school-2",
            "atendimento_programa": "aee",
        }
    ]
    db = FakeDB(
        staff=[{"id": "staff-a", "user_id": "user-a", "email": "a@test"}],
        assignments=[
            {
                "staff_id": "staff-a",
                "class_id": "regular-1",
                "academic_year": 2026,
                "status": "ativo",
            },
            {
                "staff_id": "staff-a",
                "class_id": "aee-other-school",
                "academic_year": 2026,
                "status": "ativo",
            },
        ],
        classes=classes,
    )

    allowed = asyncio.run(
        P0.resolve_professor_aee_class_ids(
            db,
            {"id": "user-a", "email": "a@test", "role": "professor"},
            academic_year=2026,
            school_id="school-1",
        )
    )

    assert allowed == set()


def test_student_projection_is_fail_closed_and_prefers_explicit_aee_class():
    items = [
        {
            "student_id": "student-a",
            "class_id": "regular-1",
            "atendimento_programa_class_id": "aee-matutino",
        },
        {
            "student_id": "student-b",
            "class_id": "regular-1",
            "atendimento_programa_class_id": "aee-vespertino",
        },
        {
            "student_id": "legacy-a",
            "class_id": "aee-matutino",
            "atendimento_programa_class_id": None,
        },
        {
            # Campo AEE explícito vence o fallback de class_id.
            "student_id": "must-not-leak",
            "class_id": "aee-matutino",
            "atendimento_programa_class_id": "aee-vespertino",
        },
    ]

    assert P0.filter_professor_aee_students(items, set()) == []
    filtered = P0.filter_professor_aee_students(items, {"aee-matutino"})
    assert [item["student_id"] for item in filtered] == ["student-a", "legacy-a"]


def test_professor_turma_projection_tolerates_aee_assignment_without_course_id():
    db = FakeDB(
        staff=[{"id": "staff-a", "user_id": "user-a", "email": "a@test"}],
        assignments=[
            {
                "id": "ta-aee",
                "staff_id": "staff-a",
                "class_id": "aee-matutino",
                "academic_year": 2026,
                "status": "ativo",
                # AEE não é obrigado a possuir course_id curricular.
            }
        ],
        classes=_base_classes(),
        schools=[{"id": "school-1", "name": "Escola Teste"}],
    )

    items = asyncio.run(
        P0._build_professor_turmas_projection(
            db,
            {"id": "user-a", "email": "a@test", "role": "professor"},
            academic_year=2026,
        )
    )

    assert len(items) == 1
    assert items[0]["id"] == "aee-matutino"
    assert items[0]["componentes"] == []


def test_source_replaces_both_reads_and_does_not_adopt_dvd():
    source = SOURCE.read_text(encoding="utf-8")
    assert '_remove_route(base_router, "/aee/estudantes", "GET")' in source
    assert '_remove_route(base_router, "/professor/turmas", "GET")' in source
    assert "if not allowed_class_ids:\n            return []" in source
    assert '"professor_aee_id": {"$in": list(professor_identity_ids)}' in source
    assert "/professor/diarios" not in source
