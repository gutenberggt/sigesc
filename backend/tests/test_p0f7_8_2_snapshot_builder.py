from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "backend" / "scripts" / "build_p0f7_8_2_snapshot_js.py"

spec = importlib.util.spec_from_file_location("p0f782_builder", BUILDER)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def _report() -> dict:
    cases = []
    for number in (1, 2, 3):
        cases.append({
            "case_number": number,
            "class": {"class_id": f"class-{number}", "academic_year": 2026},
            "teacher": {"staff_id": f"staff-{number}"},
            "school": {"school_id": f"school-{number}"},
            "source_course": {"course_id": f"source-{number}"},
            "target_course": {"course_id": f"target-{number}"},
            "exact_level_same_name_candidates": [],
        })
    return {
        "phase": mod.P0F75_PHASE,
        "status": "PASS",
        "group_name": "Geografia",
        "cases": cases,
    }


def test_builder_generates_exact_bounded_read_surface() -> None:
    js = mod.build_js(_report(), "sigesc")
    assert "const QUERY_BUDGET = 9" in js
    assert "targetDb.classes.findOne(" in js
    assert "targetDb.courses.find(" in js
    assert "targetDb.teacher_assignments.find(" in js
    assert "P0F782_SNAPSHOT_JSON=" in js
    assert "students" not in js
    assert "enrollments" not in js
    assert "grades" not in js
    assert "attendance" not in js


def test_generated_collector_has_no_write_surface() -> None:
    js = mod.build_js(_report(), "sigesc")
    forbidden = [
        ".insertOne(", ".insertMany(", ".updateOne(", ".updateMany(",
        ".replaceOne(", ".deleteOne(", ".deleteMany(", ".bulkWrite(",
        ".findOneAndUpdate(", ".findOneAndDelete(", ".findOneAndReplace(",
    ]
    assert not any(token in js for token in forbidden)


def test_builder_itself_has_no_database_client() -> None:
    source = BUILDER.read_text(encoding="utf-8")
    forbidden = ["from motor", "import motor", "AsyncIOMotorClient", "MongoClient(", "pymongo"]
    assert not any(token in source for token in forbidden)
