from pathlib import Path
import importlib.util


SCRIPT = Path(__file__).parents[1] / "scripts" / "ana_lucia_f2_2_orphan_trace_readonly.py"
SPEC = importlib.util.spec_from_file_location("ana_lucia_f2_2", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_year_bucket_target_by_academic_year_or_date():
    assert MODULE._year_bucket({"academic_year": 2026}) == "target"
    assert MODULE._year_bucket({"academic_year": "2026"}) == "target"
    assert MODULE._year_bucket({"date": "2026-03-11"}) == "target"


def test_year_bucket_detects_conflict_and_other():
    assert MODULE._year_bucket({"academic_year": 2026, "date": "2025-05-01"}) == "conflict"
    assert MODULE._year_bucket({"academic_year": 2025, "date": "2025-05-01"}) == "other"
    assert MODULE._year_bucket({}) == "missing"


def test_content_classifier_prioritizes_structural_candidates_without_mutation():
    codes = MODULE.classify_content_origin(
        exact_2026=0,
        alt_english_same_class_teacher=3,
        canonical_same_class_teacher=2,
        exact_other_year=1,
        other_component_same_class_teacher=0,
        copied_lineage_same_class=0,
        school_delete_audit_count=0,
    )
    assert codes == [
        "CONTENT_ALT_ENGLISH_COURSE_ID_SAME_CLASS",
        "CONTENT_CANONICAL_SAME_CLASS_ENGLISH",
        "CONTENT_EXACT_PAIR_OUTSIDE_2026",
    ]


def test_content_classifier_returns_not_found_when_no_metadata_candidate():
    assert MODULE.classify_content_origin(
        exact_2026=0,
        alt_english_same_class_teacher=0,
        canonical_same_class_teacher=0,
        exact_other_year=0,
        other_component_same_class_teacher=0,
        copied_lineage_same_class=0,
        school_delete_audit_count=0,
    ) == ["CONTENT_ORIGIN_NOT_FOUND_IN_SCANNED_METADATA"]


def test_attendance_classifier_detects_class_daily_and_documentary_candidates():
    codes = MODULE.classify_attendance_origin(
        exact_2026=0,
        alt_english_same_class_teacher=0,
        class_daily_teacher=4,
        documentary_english_teacher=2,
        exact_other_year=0,
        other_component_same_class_teacher=0,
        school_delete_audit_count=0,
    )
    assert codes == [
        "ATTENDANCE_CLASS_DAILY_UNATTRIBUTED_TO_COMPONENT",
        "ATTENDANCE_DOCUMENTARY_ENGLISH_SAME_CLASS",
    ]


def test_static_read_only_boundary_markers_present():
    source = SCRIPT.read_text(encoding="utf-8")
    for marker in (
        '"database_mutation": False',
        '"production_writes": False',
        '"mongo_reads_only": True',
        '"http_methods": []',
        '"login_endpoint_used": False',
        '"attendance_records_read": False',
        '"student_data_read": False',
        '"pedagogical_text_read": False',
        '"technical_ids_emitted": False',
        '"audit_old_new_values_read": False',
    ):
        assert marker in source


def test_no_mongo_mutator_call_names_in_source():
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in (
        ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
        ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
        ".find_one_and_update(", ".find_one_and_delete(", ".find_one_and_replace(",
        ".drop(", ".drop_database(",
    ):
        assert forbidden not in source


def test_forbidden_student_collections_and_attendance_records_not_read():
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in (
        "db.students", "db.enrollments", "db.student_health_profiles",
        '"records": 1', "'records': 1", '"old_value": 1', '"new_value": 1',
        '"description": 1',
    ):
        assert forbidden not in source
