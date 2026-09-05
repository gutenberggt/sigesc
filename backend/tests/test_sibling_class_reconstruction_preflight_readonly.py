from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "backend" / "scripts" / "sibling_class_reconstruction_preflight_readonly.py"
CASE = ROOT / "backend" / "reconstruction_cases" / "luiz_math_r2_2026_feb_apr.json"

spec = importlib.util.spec_from_file_location("sibling_r2", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def _source(n=2):
    return {
        "items": [
            {
                "source_date": f"2026-02-{10+i:02d}",
                "source_kind": "content_entries",
                "payload_fingerprint": f"fp-{i}",
                "number_of_classes": 1,
            }
            for i in range(n)
        ],
        "blockers": [],
        "foreign_row_count": 0,
        "canonical_row_count": n,
        "legacy_row_count": 0,
    }


def _attendance(n=2):
    return {
        "dates": [f"2026-02-{20+i:02d}" for i in range(n)],
        "document_count": n,
        "foreign_document_count": 0,
        "actor_conflict_dates": [],
    }


def _assignments(attendance):
    return {
        day: {
            "status": "RESOLVED",
            "assignment_fingerprint": f"asg-{i}",
            "historical_backfill": True,
        }
        for i, day in enumerate(attendance["dates"])
    }


def test_case_is_declarative_and_engine_is_not_luiz_specific():
    case = json.loads(CASE.read_text(encoding="utf-8"))
    mod._validate_case(case)
    assert case["strategy"] == "MONTHLY_ORDINAL_EXACT_COUNT"
    assert case["pairs"] == [
        {"source_class": "8º ANO B", "target_class": "8º ANO A"},
        {"source_class": "9º ANO B", "target_class": "9º ANO A"},
    ]
    source = SCRIPT.read_text(encoding="utf-8")
    assert "Luiz Gomes dos Santos" not in source
    assert "Jose Pereira Barbosa" not in source
    assert "8º ANO A" not in source
    assert "9º ANO A" not in source


def test_exact_monthly_ordinal_pairing_is_ready():
    attendance = _attendance(2)
    plan = mod._build_month_plan(
        month="2026-02",
        source=_source(2),
        target_attendance=attendance,
        occupied_dates=set(),
        assignment_by_date=_assignments(attendance),
    )
    assert plan["status"] == "READY_TO_APPLY"
    assert plan["blockers"] == []
    assert [(x["ordinal"], x["source_date"], x["target_date"]) for x in plan["items"]] == [
        (1, "2026-02-10", "2026-02-20"),
        (2, "2026-02-11", "2026-02-21"),
    ]


def test_count_mismatch_blocks_entire_month_and_emits_no_items():
    attendance = _attendance(3)
    plan = mod._build_month_plan(
        month="2026-02",
        source=_source(2),
        target_attendance=attendance,
        occupied_dates=set(),
        assignment_by_date=_assignments(attendance),
    )
    assert plan["status"] == "BLOCKED_REVIEW_REQUIRED"
    assert "MONTHLY_COUNT_MISMATCH" in plan["blockers"]
    assert plan["items"] == []


def test_existing_target_or_ambiguous_assignment_blocks_month():
    attendance = _attendance(2)
    assignments = _assignments(attendance)
    assignments[attendance["dates"][1]] = {
        "status": "AMBIGUOUS_HISTORICAL",
        "assignment_fingerprint": None,
        "historical_backfill": True,
    }
    plan = mod._build_month_plan(
        month="2026-02",
        source=_source(2),
        target_attendance=attendance,
        occupied_dates={attendance["dates"][0]},
        assignment_by_date=assignments,
    )
    assert plan["status"] == "BLOCKED_REVIEW_REQUIRED"
    assert "TARGET_DATE_ALREADY_HAS_CONTENT" in plan["blockers"]
    assert "TARGET_ASSIGNMENT_NOT_UNIQUE" in plan["blockers"]
    assert plan["items"] == []


def test_static_boundary_has_no_mongo_mutators_or_forbidden_stores():
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_mutators = {
        "insert_one", "insert_many", "update_one", "update_many", "replace_one",
        "delete_one", "delete_many", "bulk_write", "find_one_and_update",
        "find_one_and_delete", "find_one_and_replace", "drop", "drop_database",
    }
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in forbidden_mutators:
                hits.append(node.func.attr)
    assert not hits
    for banned in ("db.students", "db.enrollments", "db.grades"):
        assert banned not in source
    assert "records" not in mod.ATTENDANCE_PROJECTION


def test_manifest_boundary_markers_and_hash_are_deterministic():
    source = SCRIPT.read_text(encoding="utf-8")
    for marker in (
        '"mongo_reads_only": True',
        '"production_writes": False',
        '"attendance_records_read": False',
        '"student_data_read": False',
        '"enrollment_data_read": False',
        '"grades_read": False',
        '"source_payload_plaintext_read_for_fingerprint": True',
        '"source_payload_plaintext_emitted": False',
        '"technical_ids_emitted": False',
        '"learning_objects_written": False',
        '"content_entries_written": False',
        '"attendance_written": False',
    ):
        assert marker in source
    payload = {"b": 2, "a": [1, 3]}
    assert mod._canonical_hash(payload) == mod._canonical_hash({"a": [1, 3], "b": 2})
