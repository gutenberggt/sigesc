from __future__ import annotations

import ast
import importlib.util
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "ana_lucia_f2_5_adjudication_readonly.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("ana_lucia_f2_5", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_missing_key_fields_are_strict_and_structural():
    m = _load_module()
    assert m._missing_attendance_key_fields(
        {"class_id": "c1", "date": "2026-08-31", "aula_numero": None}
    ) == ["aula_numero"]
    assert m._missing_attendance_key_fields(
        {"class_id": "c1", "date": "", "aula_numero": None}
    ) == ["date", "aula_numero"]


def test_unique_unoccupied_dvd_slot_is_the_only_deterministic_slot_case():
    m = _load_module()
    dvd = {
        "weekly_slots": [
            {"weekday": 1, "aula_numero": 1},
            {"weekday": 1, "aula_numero": 2},
        ]
    }
    row = {
        "id": "x",
        "class_id": "c1",
        "date": "2026-08-31",
        "period": "regular",
        "aula_numero": None,
    }
    case = m._adjudicate_missing_key_case(
        row,
        dvd=dvd,
        source_complete=[
            {
                "class_id": "c1",
                "date": "2026-08-31",
                "period": "regular",
                "aula_numero": 1,
            }
        ],
        target_complete=[],
    )
    assert case["classification"] == "DETERMINISTIC_UNIQUE_UNOCCUPIED_DVD_SLOT"
    assert case["inferred_aula_numero"] == "2"


def test_multiple_dvd_slots_remain_unresolved():
    m = _load_module()
    dvd = {
        "weekly_slots": [
            {"weekday": 1, "aula_numero": 1},
            {"weekday": 1, "aula_numero": 2},
        ]
    }
    row = {
        "id": "x",
        "class_id": "c1",
        "date": "2026-08-31",
        "period": "regular",
        "aula_numero": None,
    }
    case = m._adjudicate_missing_key_case(
        row,
        dvd=dvd,
        source_complete=[],
        target_complete=[],
    )
    assert case["classification"] == "UNRESOLVED_MULTIPLE_DVD_SLOTS"
    assert case["inferred_aula_numero"] is None


def test_missing_date_is_never_inferred_from_created_or_updated_timestamp():
    m = _load_module()
    row = {
        "id": "x",
        "class_id": "c1",
        "date": "",
        "aula_numero": None,
        "created_at": "2026-08-31T09:00:00",
        "updated_at": "2026-08-31T10:00:00",
    }
    case = m._adjudicate_missing_key_case(
        row,
        dvd={"weekly_slots": [{"weekday": 1, "aula_numero": 1}]},
        source_complete=[],
        target_complete=[],
    )
    assert case["classification"] == "UNRESOLVED_MISSING_DATE_NO_TIMESTAMP_INFERENCE"
    assert case["inferred_aula_numero"] is None


def test_tenant_adjudication_requires_class_and_dvd_anchors_to_agree():
    m = _load_module()
    rows = [
        {"id": "a", "class_id": "c1", "school_id": "s1", "mantenedora_id": ""},
        {"id": "b", "class_id": "c2", "school_id": "s2", "mantenedora_id": None},
    ]
    report = m._tenant_adjudication(
        attendance_candidates=rows,
        class_by_id={
            "c1": {"class": "6º ANO A", "school_id": "s1", "tenant_id": "t"},
            "c2": {"class": "6º ANO B", "school_id": "s2", "tenant_id": "t"},
        },
        dvd_by_class={
            "c1": {"mantenedora_id": "t"},
            "c2": {"mantenedora_id": "other"},
        },
        tenant_id="t",
    )
    assert report["missing_tenant_candidates"] == 2
    assert report["deterministic_expected_tenant"] == 1
    assert report["unresolved_or_contradictory"] == 1
    assert report["classification"] == "TENANT_ADJUDICATION_PARTIAL_OR_BLOCKED"
    assert report["write_authorized"] is False


def test_lineage_cycle_detector_counts_distinct_cycles():
    m = _load_module()
    assert m._detect_candidate_cycles({"a": "b", "b": "a", "c": "d"}) == 1
    assert m._detect_candidate_cycles({"a": "b", "b": "c"}) == 0


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
        "old_value",
        "new_value",
        "description",
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
    assert '"audit_old_new_description_read": False' in source
    assert '"automatic_remap_authorized": False' in source


def test_f2_4_baseline_is_evidence_only():
    m = _load_module()
    assert m.F2_4_BASELINE == {
        "learning_candidates": 198,
        "attendance_candidates": 392,
        "attendance_tenant_missing": 74,
        "attendance_missing_natural_key": 4,
        "copied_candidates": 74,
        "parent_in_candidate_set": 73,
        "parent_missing": 1,
    }
