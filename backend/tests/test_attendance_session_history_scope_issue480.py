import importlib.util
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "routers"
    / "attendance_session_history_scope.py"
)
spec = importlib.util.spec_from_file_location("issue480_attendance_scope", SCRIPT)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
SessionHistoryCollision = mod.SessionHistoryCollision
normalize_session_history_docs = mod.normalize_session_history_docs


SLOTS = [
    {"weekday": 4, "aula_numero": 1},
    {"weekday": 4, "aula_numero": 2},
]


def _doc(
    id_, *, date="2026-03-12", aula=1, assignment="current",
    tenant="tenant-1", mode=None, purpose=None, period="regular",
    number_of_classes=1,
):
    return {
        "id": id_,
        "class_id": "class-1",
        "course_id": "english-final",
        "date": date,
        "period": period,
        "aula_numero": aula,
        "assignment_id": assignment,
        "mantenedora_id": tenant,
        "attendance_mode": mode,
        "attendance_purpose": purpose,
        "number_of_classes": number_of_classes,
    }


def _normalize(docs, slots=SLOTS):
    return normalize_session_history_docs(
        docs,
        class_id="class-1",
        component_id="english-final",
        current_assignment_id="current",
        tenant_id="tenant-1",
        weekly_slots=slots,
    )


def test_two_sessions_from_historical_assignment_remain_two_sessions():
    items = _normalize([
        _doc("a1", aula=1, assignment="old"),
        _doc("a2", aula=2, assignment="old"),
    ])
    assert [(item["aula_numero"], item["id"]) for item in items] == [(1, "a1"), (2, "a2")]
    assert all(item["read_only"] is True for item in items)


def test_author_or_assignment_does_not_hide_valid_session():
    items = _normalize([_doc("old", aula=1, assignment="historical-assignment")])
    assert [item["id"] for item in items] == ["old"]
    assert items[0]["historical_scope_read"] is True


def test_aggregate_never_fans_out_on_two_slot_day():
    items = _normalize([
        _doc("agg", aula=None, assignment="old", number_of_classes=2),
    ])
    assert items == []


def test_shadowed_aggregate_is_ignored_when_exact_sessions_exist():
    items = _normalize([
        _doc("agg", aula=None, assignment="old", number_of_classes=2),
        _doc("a1", aula=1, assignment="old"),
        _doc("a2", aula=2, assignment="old"),
    ])
    assert {item["id"] for item in items} == {"a1", "a2"}


def test_single_slot_day_can_preserve_one_legacy_aggregate():
    friday_slots = [{"weekday": 5, "aula_numero": 3}]
    items = _normalize([
        _doc("agg", date="2026-03-13", aula=None, assignment="old"),
    ], slots=friday_slots)
    assert [item["id"] for item in items] == ["agg"]
    assert items[0]["read_only"] is True


def test_explicit_foreign_tenant_is_not_visible():
    assert _normalize([_doc("foreign", tenant="tenant-2")]) == []


def test_explicit_class_daily_or_pdf_only_never_enters_session_history():
    assert _normalize([
        _doc("daily", mode="class_daily"),
        _doc("pdf", purpose="pdf_only"),
    ]) == []


def test_collision_without_unique_current_owner_fails_closed():
    with pytest.raises(SessionHistoryCollision):
        _normalize([
            _doc("old-a", assignment="old-a"),
            _doc("old-b", assignment="old-b"),
        ])


def test_one_current_document_wins_over_historical_duplicate_key():
    items = _normalize([
        _doc("old", assignment="old"),
        _doc("current", assignment="current"),
    ])
    assert [item["id"] for item in items] == ["current"]
    assert items[0]["read_only"] is False
