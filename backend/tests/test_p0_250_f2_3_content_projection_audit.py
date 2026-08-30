import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "p0_250_f2_3_content_projection_audit.py"
spec = importlib.util.spec_from_file_location("p0_250_f2_3_content_projection_audit", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def scope(component_id, valid_from="2026-08-18"):
    return {"component_id": component_id, "valid_from": valid_from, "valid_until": None}


def legacy(record_id, date, course_id, recorded_by="teacher-1", content="secret text"):
    return {
        "id": record_id,
        "source": "learning_objects",
        "date": date,
        "course_id": course_id,
        "recorded_by": recorded_by,
        "content": content,
    }


def canonical(record_id, date, course_id, teacher_id="teacher-1", content="canonical secret"):
    return {
        "id": record_id,
        "source": "content_entries",
        "date": date,
        "component_id": course_id,
        "teacher_id": teacher_id,
        "content": content,
    }


def test_explains_management_only_dates_outside_professor_component_scope():
    management = [
        legacy("lo-30", "2026-06-30", "course-other"),
        legacy("lo-29", "2026-06-29", "course-other"),
        legacy("lo-27", "2026-06-27", "course-other"),
        legacy("lo-26", "2026-06-26", "course-1"),
    ]
    professor = [legacy("lo-26", "2026-06-26", "course-1")]
    scopes = [scope(f"course-{i}") for i in range(1, 10)]

    result = mod.analyze_content_projection(
        management_rows=management,
        professor_rows=professor,
        assignment_scopes=scopes,
        target_teacher_id="teacher-1",
        course_names={"course-other": "Componente de outro escopo"},
    )

    assert result["classification"] == "CONTENT_VIEW_DIFFERENCE_EXPLAINED_BY_SCOPE_OR_CUTOVER"
    assert result["management_only_slot_count"] == 3
    assert result["scope_explained_management_only_slot_count"] == 3
    assert result["unexpected_management_only_slot_count"] == 0
    assert [row["date"] for row in result["management_only_slots"]] == [
        "2026-06-27", "2026-06-29", "2026-06-30"
    ]


def test_flags_missing_legacy_slot_inside_authorized_component_scope():
    management = [legacy("lo-30", "2026-06-30", "course-1", recorded_by="other-user")]
    scopes = [scope(f"course-{i}") for i in range(1, 10)]

    result = mod.analyze_content_projection(
        management_rows=management,
        professor_rows=[],
        assignment_scopes=scopes,
        target_teacher_id="teacher-1",
        course_names={"course-1": "Língua Portuguesa"},
    )

    assert result["classification"] == "CONTENT_PROJECTION_GAP_WITHIN_AUTHORIZED_SCOPE"
    assert result["unexpected_management_only_slot_count"] == 1
    detail = result["management_only_slots"][0]
    assert detail["reason"] == "EXPECTED_IN_PROFESSOR_HISTORY"
    # recorded_by is provenance only; another historical recorder must not hide the row.
    assert detail["recorded_by_other_or_unknown_count"] == 1


def test_legacy_after_cutover_is_explained_not_projection_gap():
    management = [legacy("lo-1", "2026-09-01", "course-1")]
    scopes = [scope(f"course-{i}") for i in range(1, 10)]

    result = mod.analyze_content_projection(
        management_rows=management,
        professor_rows=[],
        assignment_scopes=scopes,
        target_teacher_id="teacher-1",
    )

    assert result["classification"] == "CONTENT_VIEW_DIFFERENCE_EXPLAINED_BY_SCOPE_OR_CUTOVER"
    assert result["cutover_explained_management_only_slot_count"] == 1
    assert result["management_only_slots"][0]["reason"] == "LEGACY_AFTER_COMPONENT_CUTOVER"


def test_canonical_only_professor_slot_is_structural_and_does_not_emit_content_or_ids():
    professor = [canonical("ce-secret-id", "2026-06-18", "course-1", content="do not emit me")]
    scopes = [scope(f"course-{i}") for i in range(1, 10)]

    result = mod.analyze_content_projection(
        management_rows=[],
        professor_rows=professor,
        assignment_scopes=scopes,
        target_teacher_id="teacher-1",
        course_names={"course-1": "Matemática"},
    )

    assert result["classification"] == "CONTENT_CANONICAL_ONLY_ROWS_PRESENT"
    assert result["professor_only_slot_count"] == 1
    payload = json.dumps(result, ensure_ascii=False)
    assert "do not emit me" not in payload
    assert "ce-secret-id" not in payload
    assert "teacher-1" not in payload


def test_entitlement_drift_has_priority_when_component_count_is_not_nine():
    result = mod.analyze_content_projection(
        management_rows=[],
        professor_rows=[],
        assignment_scopes=[scope("course-1"), scope("course-2")],
        target_teacher_id="teacher-1",
    )
    assert result["classification"] == "PROFESSOR_CONTENT_ENTITLEMENT_DRIFT"
    assert result["assignment_component_count"] == 2


def test_legacy_fallback_models_same_class_month_dataset_and_emits_only_provenance_counts():
    management = [
        legacy("lo-30", "2026-06-30", "course-1", recorded_by="other-user", content="secret 30"),
        legacy("lo-29", "2026-06-29", "course-2", recorded_by="teacher-1", content="secret 29"),
        legacy("lo-27", "2026-06-27", "course-3", recorded_by="other-user", content="secret 27"),
        legacy("lo-26", "2026-06-26", "course-1", recorded_by="teacher-1", content="secret 26"),
    ]

    result = mod.analyze_legacy_fallback_projection(
        management_rows=management,
        legacy_assignment_course_ids=[f"course-{i}" for i in range(1, 10)],
        target_teacher_id="teacher-1",
    )

    assert result["classification"] == "CONTENT_LEGACY_FALLBACK_PARITY_EXPECTED"
    assert result["projection_mode"] == "LEGACY_FALLBACK"
    assert result["legacy_teacher_assignment_component_count"] == 9
    assert result["management_legacy_record_count"] == 4
    assert result["professor_projection_record_count"] == 4
    assert result["management_only_slot_count"] == 0
    assert result["professor_only_slot_count"] == 0
    assert result["professor_legacy_record_count"] == 4
    assert result["legacy_date_provenance"][0] == {
        "date": "2026-06-30",
        "record_count": 1,
        "component_count": 1,
        "recorded_by_target_professor_count": 0,
        "recorded_by_other_or_unknown_count": 1,
    }
    payload = json.dumps(result, ensure_ascii=False)
    for forbidden in ("secret 30", "secret 29", "secret 27", "secret 26", "lo-30", "teacher-1"):
        assert forbidden not in payload
