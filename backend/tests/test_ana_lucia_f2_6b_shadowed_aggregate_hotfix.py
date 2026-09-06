from types import SimpleNamespace

import pytest

from scripts import ana_lucia_f2_6b_shadowed_aggregate_hotfix as hotfix


class _Schedules:
    def __init__(self, schedule):
        self.schedule = schedule

    def find_one(self, query, projection):
        return self.schedule


class _Db:
    def __init__(self, schedule):
        self.class_schedules = _Schedules(schedule)


def _base():
    def attendance_key(row):
        class_id = str(row.get("class_id") or "")
        date = str(row.get("date") or "")[:10]
        aula = str(row.get("aula_numero") or "")
        if not class_id or not date or not aula:
            return None
        return class_id, date, str(row.get("period") or "regular"), aula

    def aggregate_key(row):
        class_id = str(row.get("class_id") or "")
        date = str(row.get("date") or "")[:10]
        if not class_id or not date:
            return None
        return class_id, date, str(row.get("period") or "regular")

    return SimpleNamespace(
        _attendance_key=attendance_key,
        _aggregate_key=aggregate_key,
        _day=lambda value: str(value or "")[:10],
    )


def _row(id_, *, date="2026-02-12", aula=None, classes=2, course="legacy"):
    return {
        "id": id_,
        "class_id": "class-1",
        "date": date,
        "period": "regular",
        "aula_numero": aula,
        "number_of_classes": classes,
        "course_id": course,
    }


def _schedule(*aulas):
    return {
        "schedule_slots": [
            {"course_id": "current", "day": "quinta-feira", "slot_number": aula}
            for aula in aulas
        ]
    }


def test_schedule_extracts_exact_thursday_slots_across_equivalent_identity():
    expected = hotfix.expected_schedule_aulas(
        _schedule(1, 2),
        date="2026-02-12",
        course_ids={"legacy", "current"},
    )
    assert expected == {"1", "2"}


def test_two_mixed_sessions_are_safe_only_when_schedule_and_declared_count_match():
    source = [_row("agg"), _row("a1", aula=1), _row("a2", aula=2)]
    result = hotfix.validate_attendance_keys_with_schedule(
        _base(),
        _Db(_schedule(1, 2)),
        source,
        [],
        legacy_id="legacy",
        current_id="current",
    )
    assert result == {
        "incomplete_candidates": 1,
        "isolated_aggregate_cases": 0,
        "shadowed_aggregate_cases": 1,
    }


def test_shadowed_case_fails_closed_when_schedule_does_not_equal_sessions():
    source = [_row("agg"), _row("a1", aula=1), _row("a2", aula=2)]
    with pytest.raises(RuntimeError, match="SHADOWED_SESSION_SET_MISMATCH"):
        hotfix.validate_attendance_keys_with_schedule(
            _base(),
            _Db(_schedule(1, 3)),
            source,
            [],
            legacy_id="legacy",
            current_id="current",
        )


def test_shadowed_case_fails_closed_when_number_of_classes_disagrees():
    source = [_row("agg", classes=3), _row("a1", aula=1), _row("a2", aula=2)]
    with pytest.raises(RuntimeError, match="DECLARED_CLASS_COUNT_MISMATCH"):
        hotfix.validate_attendance_keys_with_schedule(
            _base(),
            _Db(_schedule(1, 2)),
            source,
            [],
            legacy_id="legacy",
            current_id="current",
        )


def test_shadowed_case_fails_closed_if_target_already_has_session():
    source = [_row("agg"), _row("a1", aula=1), _row("a2", aula=2)]
    target = [_row("target", aula=3, course="current")]
    with pytest.raises(RuntimeError, match="AGGREGATE_NOT_PRESERVABLE"):
        hotfix.validate_attendance_keys_with_schedule(
            _base(),
            _Db(_schedule(1, 2)),
            source,
            target,
            legacy_id="legacy",
            current_id="current",
        )


def test_isolated_aggregate_remains_preservable_without_inventing_sessions():
    result = hotfix.validate_attendance_keys_with_schedule(
        _base(),
        _Db(_schedule(1, 2)),
        [_row("agg")],
        [],
        legacy_id="legacy",
        current_id="current",
    )
    assert result == {
        "incomplete_candidates": 1,
        "isolated_aggregate_cases": 1,
        "shadowed_aggregate_cases": 0,
    }


def test_hotfix_has_no_database_mutator_calls():
    from pathlib import Path
    import ast

    source = Path(hotfix.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = {
        "insert_one", "insert_many", "update_one", "update_many", "replace_one",
        "delete_one", "delete_many", "bulk_write", "find_one_and_update",
        "find_one_and_delete", "find_one_and_replace", "drop", "drop_database",
    }
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in forbidden:
                hits.append(node.func.attr)
    assert hits == []
