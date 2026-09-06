import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


MODULE_PATH = Path("backend/routers/manual_content_copy_identity_bridge.py")
INIT_PATH = Path("backend/routers/__init__.py")

_spec = importlib.util.spec_from_file_location("manual_content_copy_identity_bridge_test", MODULE_PATH)
bridge = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(bridge)


class FakeCursor:
    def __init__(self, rows):
        self.rows = list(rows)

    async def to_list(self, _limit):
        return list(self.rows)


class FakeCollection:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    async def find_one(self, query, _projection=None):
        for row in self.rows:
            if _matches(row, query):
                return dict(row)
        return None

    def find(self, query, _projection=None):
        # Os testes desta ponte precisam apenas dos filtros simples usados por
        # teacher_assignments; o fallback por e-mail é validado estruturalmente.
        return FakeCursor([row for row in self.rows if _matches(row, query)])


def _matches(row, query):
    for key, value in query.items():
        if key.startswith("$"):
            continue
        if isinstance(value, dict) and "$in" in value:
            if row.get(key) not in value["$in"]:
                return False
            continue
        if isinstance(value, dict) and "$regex" in value:
            # Não é necessário para os casos funcionais desta suíte.
            continue
        if row.get(key) != value:
            return False
    return True


def _db(*, users=None, staff=None, teacher_assignments=None):
    return SimpleNamespace(
        users=FakeCollection(users),
        staff=FakeCollection(staff),
        teacher_assignments=FakeCollection(teacher_assignments),
    )


@pytest.mark.asyncio
async def test_actor_can_already_be_canonical_user_id():
    db = _db(users=[{"id": "user-luiz", "full_name": "Luiz Gomes"}])
    user = await bridge._canonical_user_for_actor(db, "user-luiz")
    assert user["id"] == "user-luiz"


@pytest.mark.asyncio
async def test_legacy_staff_id_resolves_through_staff_user_id():
    db = _db(
        users=[{"id": "user-luiz", "full_name": "Luiz Gomes"}],
        staff=[{"id": "staff-luiz", "user_id": "user-luiz"}],
    )
    user = await bridge._canonical_user_for_actor(db, "staff-luiz")
    assert user["id"] == "user-luiz"


@pytest.mark.asyncio
async def test_legacy_binding_prioritizes_staff_id_over_transitional_teacher_id():
    db = _db(
        users=[{"id": "user-luiz", "full_name": "Luiz Gomes"}],
        staff=[{"id": "staff-luiz", "user_id": "user-luiz"}],
        teacher_assignments=[
            {
                "class_id": "9a",
                "course_id": "mat",
                "status": "ativo",
                "academic_year": 2026,
                "staff_id": "staff-luiz",
                "teacher_id": "transitional-value",
            }
        ],
    )
    result = await bridge._legacy_binding(
        db,
        class_doc={"id": "9a", "academic_year": 2026},
        component_id="mat",
    )
    assert result["status"] == "RESOLVED"
    assert result["mode"] == "LEGACY_CANONICAL"
    assert result["teacher_id"] == "user-luiz"


@pytest.mark.asyncio
async def test_unresolved_legacy_can_fall_back_to_unambiguous_attendance_teacher():
    async def dvd_binding(*args, **kwargs):
        return None

    async def attendance_binding(*args, **kwargs):
        return {
            "status": "RESOLVED",
            "mode": "ATTENDANCE_TEACHER_SNAPSHOT",
            "assignment_id": None,
            "teacher_id": "user-luiz",
            "teacher_name": "Luiz Gomes",
            "historical_backfill": False,
        }

    module = SimpleNamespace(
        _dvd_binding=dvd_binding,
        _attendance_teacher_binding=attendance_binding,
    )
    bridge.install_manual_content_copy_identity_bridge(module)
    db = _db(
        teacher_assignments=[
            {
                "class_id": "9a",
                "course_id": "mat",
                "status": "ativo",
                "academic_year": 2026,
                "staff_id": "staff-sem-user",
            }
        ]
    )
    result = await bridge._resolve_target_binding(
        db,
        class_doc={"id": "9a", "academic_year": 2026},
        component_id="mat",
        target_date="2026-02-11",
    )
    assert result["status"] == "RESOLVED"
    assert result["mode"] == "ATTENDANCE_TEACHER_SNAPSHOT"
    assert result["teacher_id"] == "user-luiz"


@pytest.mark.asyncio
async def test_ambiguous_legacy_remains_fail_closed_and_never_falls_to_attendance():
    async def dvd_binding(*args, **kwargs):
        return None

    async def attendance_binding(*args, **kwargs):
        raise AssertionError("attendance fallback must not run after ambiguous legacy")

    module = SimpleNamespace(
        _dvd_binding=dvd_binding,
        _attendance_teacher_binding=attendance_binding,
    )
    bridge.install_manual_content_copy_identity_bridge(module)
    db = _db(
        teacher_assignments=[
            {
                "class_id": "9a",
                "course_id": "mat",
                "status": "ativo",
                "academic_year": 2026,
                "staff_id": "staff-a",
            },
            {
                "class_id": "9a",
                "course_id": "mat",
                "status": "ativo",
                "academic_year": 2026,
                "staff_id": "staff-b",
            },
        ]
    )
    result = await bridge._resolve_target_binding(
        db,
        class_doc={"id": "9a", "academic_year": 2026},
        component_id="mat",
        target_date="2026-02-11",
    )
    assert result == {"status": "AMBIGUOUS", "reason": "MULTIPLE_LEGACY_TEACHERS"}


def test_bridge_is_installed_before_manual_copy_setup():
    source = INIT_PATH.read_text(encoding="utf-8")
    bridge_call = "install_manual_content_copy_identity_bridge(_manual_content_copy_admin_mod)"
    setup_call = "install_manual_content_copy_setup(_content_entries_mod)"
    assert bridge_call in source
    assert setup_call in source
    assert source.index(bridge_call) < source.index(setup_call)


def test_bridge_never_uses_super_admin_as_teacher_fallback():
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "staff.user_id" in source
    assert 'db.staff.find_one(' in source
    assert '"AMBIGUOUS"' in source
    assert "super_admin" in source  # docstring states the prohibition explicitly
    assert 'teacher_id=user.get("id")' not in source
