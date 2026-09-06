import ast
from pathlib import Path

import pytest

from scripts import ana_lucia_f2_6_surgical_course_id_remap as remap


def _attendance(id_, *, class_id="c1", date="2026-03-12", aula=1, period="regular", classes=1):
    return {
        "id": id_,
        "class_id": class_id,
        "date": date,
        "aula_numero": aula,
        "period": period,
        "number_of_classes": classes,
    }


def _learning(id_, *, class_id="c1", date="2026-03-12"):
    return {"id": id_, "class_id": class_id, "date": date}


def test_explicit_authorization_is_required_before_mongo_resolution():
    with pytest.raises(RuntimeError, match="EXPLICIT_PRODUCTION_WRITE_AUTHORIZATION_REQUIRED"):
        remap.run_authorized_remap(authorize_production_writes=False)


def test_learning_collision_is_fail_closed():
    source = [_learning("legacy")]
    target = [_learning("current")]
    with pytest.raises(RuntimeError, match="LEARNING_TARGET_COLLISION"):
        remap._validate_learning_keys(source, target)


def test_two_attendance_sessions_are_preserved_as_two_natural_keys():
    source = [_attendance("a1", aula=1), _attendance("a2", aula=2)]
    assert remap._validate_attendance_keys(source, []) == 0


def test_legacy_aggregate_without_aula_is_preservable_only_when_isolated():
    aggregate = _attendance("agg", aula=None, classes=2)
    assert remap._validate_attendance_keys([aggregate], []) == 1

    with pytest.raises(RuntimeError, match="AGGREGATE_NOT_PRESERVABLE"):
        remap._validate_attendance_keys(
            [aggregate, _attendance("a1", aula=1)],
            [],
        )


def test_legacy_aggregate_blocks_when_target_has_same_day_session():
    aggregate = _attendance("agg", aula=None, classes=2)
    with pytest.raises(RuntimeError, match="AGGREGATE_NOT_PRESERVABLE"):
        remap._validate_attendance_keys(
            [aggregate],
            [_attendance("target", aula=1)],
        )


def test_already_applied_signature_is_exact():
    state = {
        "learning_candidates": [],
        "attendance_candidates": [],
        "raw_learning": [],
        "raw_attendance": [{} for _ in range(remap.BASELINE["attendance_excluded_not_teacher"])],
        "target_learning": [{} for _ in range(
            remap.BASELINE["learning_target_existing"] + remap.BASELINE["learning_candidates"]
        )],
        "target_attendance": [{} for _ in range(
            remap.BASELINE["attendance_target_existing"] + remap.BASELINE["attendance_candidates"]
        )],
    }
    assert remap._already_applied(state) is True
    state["raw_attendance"].append({})
    assert remap._already_applied(state) is False


def test_writer_surface_is_course_id_only_update_one():
    source_path = Path(remap.__file__)
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    mutators = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {
                "insert_one", "insert_many", "update_one", "update_many", "replace_one",
                "delete_one", "delete_many", "bulk_write", "find_one_and_update",
                "find_one_and_delete", "find_one_and_replace", "drop", "drop_database",
            }:
                mutators.append(node.func.attr)
    assert set(mutators) == {"update_one"}
    assert '"$set": {"course_id": current_id}' in source
    assert '"$set": {"course_id": legacy_id}' in source
    assert '"$set": {"mantenedora_id"' not in source
    assert '"$set": {"aula_numero"' not in source
    assert '"$set": {"copied_from_id"' not in source
