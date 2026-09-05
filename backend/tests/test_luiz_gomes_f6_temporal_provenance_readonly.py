import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "luiz_gomes_f6_temporal_provenance_readonly.py"
spec = importlib.util.spec_from_file_location("luiz_gomes_f6", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def _base_kwargs(rows):
    return {
        "target_name": "8º ANO A",
        "current_class_id": "class-current",
        "current_course_id": "course-current",
        "same_name_class_ids": {"class-current", "class-old"},
        "same_name_course_ids": {"course-current", "course-alt"},
        "all_class_ids": {"class-current", "class-old", "class-other"},
        "all_course_ids": {"course-current", "course-alt", "course-other"},
        "actor_ids": {"teacher-user", "staff"},
        "assignment_ids": {"assignment-current"},
        "store_rows": {
            "learning_objects": rows,
            "content_entries": [],
        },
    }


def test_projection_contains_only_metadata_fields():
    assert not mod.FORBIDDEN_CONTENT_FIELDS.intersection(mod.SAFE_CONTENT_PROJECTION)
    assert "date" in mod.SAFE_CONTENT_PROJECTION
    assert "class_id" in mod.SAFE_CONTENT_PROJECTION
    assert "course_id" in mod.SAFE_CONTENT_PROJECTION


def test_current_path_historical_content_is_detected():
    result = mod.classify_target(**_base_kwargs([
        {
            "class_id": "class-current",
            "course_id": "course-current",
            "date": "2026-02-10",
            "recorded_by": "teacher-user",
        }
    ]))
    assert "CURRENT_PATH_HAS_HISTORICAL_CONTENT" in result["classification"]
    assert result["stores"]["learning_objects"]["summary"]["months"]["02"] == 1


def test_course_binding_anomaly_is_detected():
    result = mod.classify_target(**_base_kwargs([
        {
            "class_id": "class-current",
            "course_id": "course-alt",
            "date": "2026-03-11",
            "recorded_by": "teacher-user",
        }
    ]))
    assert "HISTORICAL_CONTENT_COURSE_BINDING_ANOMALY_CONFIRMED" in result["classification"]


def test_class_identity_split_is_detected():
    result = mod.classify_target(**_base_kwargs([
        {
            "class_id": "class-old",
            "course_id": "course-current",
            "date": "2026-04-12",
            "recorded_by": "teacher-user",
        }
    ]))
    assert "HISTORICAL_CONTENT_CLASS_IDENTITY_SPLIT_CONFIRMED" in result["classification"]


def test_content_entries_store_is_detected():
    kwargs = _base_kwargs([])
    kwargs["store_rows"]["content_entries"] = [
        {
            "class_id": "class-current",
            "component_id": "course-current",
            "date": "2026-02-18",
            "assignment_id": "assignment-current",
        }
    ]
    result = mod.classify_target(**kwargs)
    assert "HISTORICAL_CONTENT_IN_CANONICAL_STORE_CONFIRMED" in result["classification"]


def test_unresolved_teacher_class_binding_is_detected():
    result = mod.classify_target(**_base_kwargs([
        {
            "class_id": "deleted-class-id",
            "course_id": "course-current",
            "date": "2026-03-20",
            "recorded_by": "teacher-user",
        }
    ]))
    assert "HISTORICAL_CONTENT_POSSIBLE_UNRESOLVED_CLASS_BINDING" in result["classification"]


def test_not_found_live_stores_is_explicit():
    result = mod.classify_target(**_base_kwargs([]))
    assert result["classification"] == ["HISTORICAL_CONTENT_NOT_FOUND_LIVE_STORES"]


def test_fingerprints_do_not_emit_raw_ids():
    assert mod._fp("secret-internal-id") != "secret-internal-id"
    assert len(mod._fp("secret-internal-id")) == 12
