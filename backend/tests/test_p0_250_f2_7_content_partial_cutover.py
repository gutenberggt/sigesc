from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import services.professor_content_projection as projection


TENANT = "tenant-1"
CLASS_ID = "class-5a"
DVD_COMPONENTS = [f"dvd-{idx}" for idx in range(1, 8)]
PORTUGUES = "portugues"
MATEMATICA = "matematica"
ENTITLED = [*DVD_COMPONENTS, PORTUGUES, MATEMATICA]


class FakeCursor:
    def __init__(self, rows, query=None):
        self.rows = list(rows)
        self.query = query or {}

    async def to_list(self, _limit):
        return list(self.rows)


class FakeCollection:
    def __init__(self, rows):
        self.rows = list(rows)
        self.queries = []

    @staticmethod
    def _matches(row, query):
        for key, expected in query.items():
            actual = row.get(key)
            if isinstance(expected, dict):
                if "$in" in expected and actual not in expected["$in"]:
                    return False
                if "$gte" in expected and str(actual) < str(expected["$gte"]):
                    return False
                if "$lt" in expected and str(actual) >= str(expected["$lt"]):
                    return False
                continue
            if actual != expected:
                return False
        return True

    async def find_one(self, query, _projection=None):
        self.queries.append(dict(query))
        return next((dict(row) for row in self.rows if self._matches(row, query)), None)

    def find(self, query, _projection=None):
        self.queries.append(dict(query))
        return FakeCursor(
            [dict(row) for row in self.rows if self._matches(row, query)],
            query=query,
        )


def build_db(*, assignments=None, legacy_rows=None):
    assignments = assignments if assignments is not None else [
        {
            "staff_id": "staff-1",
            "class_id": CLASS_ID,
            "academic_year": 2026,
            "status": "ativo",
            "mantenedora_id": TENANT,
            "course_id": component_id,
        }
        for component_id in ENTITLED
    ]
    course_names = {
        **{component_id: f"DVD {idx}" for idx, component_id in enumerate(DVD_COMPONENTS, 1)},
        PORTUGUES: "Língua Portuguesa",
        MATEMATICA: "Matemática",
        "unauthorized": "Componente não alocado",
    }
    return SimpleNamespace(
        staff=FakeCollection([
            {
                "id": "staff-1",
                "user_id": "user-1",
                "email": "prof@example.test",
                "mantenedora_id": TENANT,
            }
        ]),
        classes=FakeCollection([
            {"id": CLASS_ID, "name": "5º ANO A", "mantenedora_id": TENANT}
        ]),
        teacher_assignments=FakeCollection(assignments),
        learning_objects=FakeCollection(legacy_rows or []),
        courses=FakeCollection([
            {"id": course_id, "name": name, "mantenedora_id": TENANT}
            for course_id, name in course_names.items()
        ]),
    )


def professor_user():
    return {
        "id": "user-1",
        "email": "prof@example.test",
        "role": "professor",
        "mantenedora_id": TENANT,
    }


@pytest.mark.asyncio
async def test_mixed_projection_keeps_7_dvd_plus_portuguese_and_math_legacy(monkeypatch):
    legacy_rows = [
        *[
            {
                "id": f"pt-{idx}",
                "class_id": CLASS_ID,
                "course_id": PORTUGUES,
                "date": f"2026-06-{idx:02d}",
                "academic_year": 2026,
                "mantenedora_id": TENANT,
            }
            for idx in range(1, 14)
        ],
        *[
            {
                "id": f"mat-{idx}",
                "class_id": CLASS_ID,
                "course_id": MATEMATICA,
                "date": f"2026-06-{idx + 13:02d}",
                "academic_year": 2026,
                "mantenedora_id": TENANT,
            }
            for idx in range(1, 6)
        ],
        {
            "id": "must-not-leak",
            "class_id": CLASS_ID,
            "course_id": "unauthorized",
            "date": "2026-06-30",
            "academic_year": 2026,
            "mantenedora_id": TENANT,
        },
    ]
    db = build_db(legacy_rows=legacy_rows)

    async def fake_diaries(*_args, **_kwargs):
        return {
            "items": [
                {
                    "assignment_id": f"assignment-{idx}",
                    "class_id": CLASS_ID,
                    "component_id": component_id,
                    "capabilities": {"content_enabled": True},
                }
                for idx, component_id in enumerate(DVD_COMPONENTS, 1)
            ]
        }

    async def fake_history(_db, _user, *, assignment_id, class_id, component_id, **_kwargs):
        assert class_id == CLASS_ID
        assert component_id in DVD_COMPONENTS
        return {
            "items": [
                {
                    "id": f"canonical-{assignment_id}",
                    "class_id": CLASS_ID,
                    "course_id": component_id,
                    "component_id": component_id,
                    "date": "2026-06-20",
                    "academic_year": 2026,
                    "source": "content_entries",
                    "assignment_id": assignment_id,
                }
            ]
        }

    monkeypatch.setattr(projection, "list_teacher_diaries", fake_diaries)
    monkeypatch.setattr(projection, "list_assignment_content_history", fake_history)

    result = await projection.list_professor_content_projection(
        db,
        professor_user(),
        class_id=CLASS_ID,
        academic_year=2026,
        month=6,
        active_mantenedora_id=TENANT,
    )

    by_course = {}
    for row in result:
        by_course.setdefault(row["course_id"], []).append(row)

    assert set(by_course) == set(ENTITLED)
    assert all(len(by_course[component_id]) == 1 for component_id in DVD_COMPONENTS)
    assert len(by_course[PORTUGUES]) == 13
    assert len(by_course[MATEMATICA]) == 5
    assert all(row.get("source") == "content_entries" for c in DVD_COMPONENTS for row in by_course[c])
    assert all(row.get("source") == "learning_objects" for row in by_course[PORTUGUES])
    assert all(row.get("source") == "learning_objects" for row in by_course[MATEMATICA])
    assert all(row.get("legacy") is True and row.get("read_only") is True for row in by_course[PORTUGUES] + by_course[MATEMATICA])
    assert "unauthorized" not in by_course

    legacy_query = db.learning_objects.queries[-1]
    assert set(legacy_query["course_id"]["$in"]) == {PORTUGUES, MATEMATICA}
    assert legacy_query["mantenedora_id"] == TENANT


@pytest.mark.asyncio
async def test_zero_teacher_assignment_entitlement_fails_closed(monkeypatch):
    db = build_db(assignments=[])

    async def must_not_read_diaries(*_args, **_kwargs):
        raise AssertionError("sem entitlement não deve consultar projeção DVD")

    monkeypatch.setattr(projection, "list_teacher_diaries", must_not_read_diaries)

    result = await projection.list_professor_content_projection(
        db,
        professor_user(),
        class_id=CLASS_ID,
        academic_year=2026,
        month=6,
        active_mantenedora_id=TENANT,
    )

    assert result == []
    assert db.learning_objects.queries == []


@pytest.mark.asyncio
async def test_canonical_component_never_silently_falls_back_to_legacy(monkeypatch):
    db = build_db(
        assignments=[
            {
                "staff_id": "staff-1",
                "class_id": CLASS_ID,
                "academic_year": 2026,
                "status": "ativo",
                "mantenedora_id": TENANT,
                "course_id": DVD_COMPONENTS[0],
            }
        ],
        legacy_rows=[
            {
                "id": "legacy-post-cutover",
                "class_id": CLASS_ID,
                "course_id": DVD_COMPONENTS[0],
                "date": "2026-06-20",
                "academic_year": 2026,
                "mantenedora_id": TENANT,
            }
        ],
    )

    async def fake_diaries(*_args, **_kwargs):
        return {
            "items": [{
                "assignment_id": "assignment-1",
                "class_id": CLASS_ID,
                "component_id": DVD_COMPONENTS[0],
                "capabilities": {"content_enabled": True},
            }]
        }

    async def broken_history(*_args, **_kwargs):
        raise projection.ContentHistoryBridgeError("TEST_HISTORY_ERROR", "boom")

    monkeypatch.setattr(projection, "list_teacher_diaries", fake_diaries)
    monkeypatch.setattr(projection, "list_assignment_content_history", broken_history)

    with pytest.raises(projection.ProfessorContentProjectionError) as exc:
        await projection.list_professor_content_projection(
            db,
            professor_user(),
            class_id=CLASS_ID,
            academic_year=2026,
            month=6,
            active_mantenedora_id=TENANT,
        )

    assert exc.value.code == "CANONICAL_CONTENT_HISTORY_UNAVAILABLE"
    assert db.learning_objects.queries == []


@pytest.mark.asyncio
async def test_tenant_scope_is_required_before_any_classwide_read(monkeypatch):
    db = build_db()
    user = professor_user()
    user["mantenedora_id"] = None

    async def must_not_run(*_args, **_kwargs):
        raise AssertionError("tenant ausente deve falhar antes de qualquer projeção")

    monkeypatch.setattr(projection, "list_teacher_diaries", must_not_run)

    with pytest.raises(projection.ProfessorContentProjectionError) as exc:
        await projection.list_professor_content_projection(
            db,
            user,
            class_id=CLASS_ID,
            academic_year=2026,
            month=6,
            active_mantenedora_id=None,
        )

    assert exc.value.code == "TENANT_SCOPE_REQUIRED"


def test_frontend_and_router_contract_keep_component_scoped_flow_unchanged():
    root = Path(__file__).resolve().parents[2]
    frontend = (root / "frontend/src/services/contentPartialCutoverResolver.js").read_text(encoding="utf-8")
    hook = (root / "frontend/src/hooks/useDiaryPrefill.js").read_text(encoding="utf-8")
    adapter = (root / "backend/routers/content_partial_cutover.py").read_text(encoding="utf-8")
    routers_init = (root / "backend/routers/__init__.py").read_text(encoding="utf-8")

    assert "if (!classId || componentId) return config;" in frontend
    assert "config.__skipContentDvdBridge = true;" in frontend
    assert "@/services/contentPartialCutoverResolver" in hook
    assert 'current_user.get("role") != "professor" or not class_id or course_id' in adapter
    assert "install_professor_content_partial_cutover_setup(_learning_objects_mod)" in routers_init
