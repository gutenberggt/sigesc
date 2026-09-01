from __future__ import annotations

import ast
import importlib.util
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "ana_lucia_f2_4_surgical_remap_preflight_readonly.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("ana_lucia_f2_4", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_learning_key_matches_p0f3_collapsed_course_semantics():
    m = _load_module()
    assert m._learning_key({"class_id": "c1", "date": "2026-04-10T00:00:00"}) == (
        "c1",
        "2026-04-10",
    )
    assert m._learning_key({"class_id": "c1", "date": ""}) is None


def test_attendance_key_matches_p0f3_and_requires_aula_numero():
    m = _load_module()
    assert m._attendance_key(
        {"class_id": "c1", "date": "2026-04-10", "period": "", "aula_numero": 2}
    ) == ("c1", "2026-04-10", "regular", "2")
    assert m._attendance_key(
        {"class_id": "c1", "date": "2026-04-10", "period": "regular"}
    ) is None


def test_classify_preflight_safe_only_without_structural_blockers():
    m = _load_module()
    base = dict(
        candidates=10,
        missing_natural_key=0,
        duplicate_source_keys=0,
        duplicate_target_keys=0,
        collision_keys=0,
        assignment_bound=0,
        tenant_missing=0,
        tenant_mismatch=0,
    )
    assert m.classify_preflight(**base) == "STRUCTURALLY_SAFE_FOR_FUTURE_COURSE_ID_REMAP"
    assert m.classify_preflight(**{**base, "collision_keys": 1}) == (
        "BLOCKED_TARGET_COLLISIONS_REQUIRE_ADJUDICATION"
    )
    assert m.classify_preflight(**{**base, "duplicate_source_keys": 1}) == (
        "BLOCKED_INTERNAL_MULTIPLICITY"
    )
    assert m.classify_preflight(**{**base, "missing_natural_key": 1}) == (
        "BLOCKED_INCOMPLETE_NATURAL_KEY"
    )
    assert m.classify_preflight(**{**base, "assignment_bound": 1}) == (
        "BLOCKED_ASSIGNMENT_BOUND_RECORDS"
    )
    assert m.classify_preflight(**{**base, "tenant_mismatch": 1}) == (
        "BLOCKED_TENANT_INTEGRITY"
    )


def test_collection_preflight_counts_collisions_without_payload_values():
    m = _load_module()
    source = [
        {"id": "s1", "class_id": "c1", "date": "2026-03-01", "mantenedora_id": "t"},
        {"id": "s2", "class_id": "c1", "date": "2026-03-02", "mantenedora_id": "t"},
    ]
    target = [
        {"id": "t1", "class_id": "c1", "date": "2026-03-02", "mantenedora_id": "t"},
    ]
    report = m._collection_preflight(
        collection="learning_objects",
        source_rows=source,
        target_rows=target,
        tenant_id="t",
        key_fn=m._learning_key,
    )
    assert report["candidate_documents"] == 2
    assert report["collision_natural_keys"] == 1
    assert report["collision_source_documents"] == 1
    assert report["structurally_noncolliding_source_documents"] == 1
    assert report["classification"] == "BLOCKED_TARGET_COLLISIONS_REQUIRE_ADJUDICATION"
    assert report["direct_remap_authorized"] is False


def test_candidate_partition_excludes_non_teacher_and_deleted():
    m = _load_module()
    rows = [
        {"id": "1", "created_by": "u", "status": "ativo"},
        {"id": "2", "created_by": "other", "status": "ativo"},
        {"id": "3", "created_by": "u", "deleted": True},
        {"id": "4", "assignment_id": "a1", "status": "ativo"},
    ]
    candidates, excluded = m._candidate_partition(
        rows,
        actor_ids={"u", "s"},
        teacher_assignment_ids={"a1"},
        assignment_owner={"a1": "u"},
        teacher_user_id="u",
    )
    assert [row["id"] for row in candidates] == ["1", "4"]
    assert excluded["NOT_ATTRIBUTABLE_TO_TEACHER"] == 1
    assert excluded["INACTIVE_OR_DELETED"] == 1


def test_projection_and_source_preserve_read_only_privacy_boundary():
    m = _load_module()
    forbidden_projection_fields = {
        "records",
        "content",
        "observations",
        "methodology",
        "resources",
        "student_id",
        "b1",
        "b2",
        "b3",
        "b4",
    }
    assert forbidden_projection_fields.isdisjoint(m.COMMON_PROJECTION)

    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_calls = {
        "insert_one",
        "insert_many",
        "update_one",
        "update_many",
        "replace_one",
        "delete_one",
        "delete_many",
        "bulk_write",
        "find_one_and_update",
        "find_one_and_delete",
        "find_one_and_replace",
        "drop",
        "drop_database",
    }
    hits = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in forbidden_calls
    }
    assert hits == set()
    assert '"attendance_records_read": False' in source
    assert '"pedagogical_text_read": False' in source
    assert '"automatic_remap_authorized": False' in source


def test_f2_baseline_is_evidence_only():
    m = _load_module()
    assert m.F2_BASELINE == {
        "learning_objects_teacher_attributed": 198,
        "attendance_teacher_attributed": 392,
    }
