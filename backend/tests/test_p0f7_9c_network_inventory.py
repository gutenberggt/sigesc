from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "backend" / "scripts" / "build_p0f7_9c_inventory_snapshot_js.py"
ANALYZER = ROOT / "backend" / "scripts" / "audit_p0f7_9c_inventory_offline.py"

builder_spec = importlib.util.spec_from_file_location("p0f79c_inventory_builder", BUILDER)
builder = importlib.util.module_from_spec(builder_spec)
assert builder_spec.loader is not None
builder_spec.loader.exec_module(builder)

analyzer_spec = importlib.util.spec_from_file_location("p0f79c_inventory_analyzer", ANALYZER)
analyzer = importlib.util.module_from_spec(analyzer_spec)
assert analyzer_spec.loader is not None
analyzer_spec.loader.exec_module(analyzer)


def _snapshot() -> dict:
    return {
        "phase": builder.SOURCE_PHASE,
        "mode": builder.SOURCE_MODE,
        "query_budget": 8,
        "query_calls": 8,
        "class": {
            "mantenedora_id": "tenant-1",
            "academic_year": 2026,
        },
    }


def _inventory(source: dict, *, classes: int = 50, assignments: int = 600, courses: int = 120) -> dict:
    return {
        "phase": analyzer.INVENTORY_PHASE,
        "mode": analyzer.INVENTORY_MODE,
        "mantenedora_id": "tenant-1",
        "academic_year": 2026,
        "source_p0f7_9a_snapshot_sha256": analyzer._canonical_sha256(source),
        "query_budget": 6,
        "query_calls": 6,
        "counts": {
            "schools": 23,
            "classes": classes,
            "classes_without_explicit_level": 0,
            "teacher_assignments": assignments,
            "active_teacher_assignments": assignments,
            "courses": courses,
        },
    }


def test_source_context_is_fail_closed_and_chained() -> None:
    ctx = builder._source_context(_snapshot())
    assert ctx["mantenedora_id"] == "tenant-1"
    assert ctx["academic_year"] == 2026
    assert len(ctx["source_p0f7_9a_snapshot_sha256"]) == 64


def test_missing_tenant_is_rejected() -> None:
    payload = _snapshot()
    payload["class"]["mantenedora_id"] = ""
    try:
        builder._source_context(payload)
    except ValueError as exc:
        assert str(exc) == "P0F7_9A_SOURCE_TENANT_MISSING_FAIL_CLOSED"
    else:
        raise AssertionError("missing tenant must fail closed")


def test_collector_is_counts_only_and_exactly_six_queries() -> None:
    js = builder.build_js(_snapshot(), "sigesc")
    assert "const QUERY_BUDGET = 6" in js
    assert js.count("countDocuments(") == 6
    assert ".find(" not in js
    assert ".aggregate(" not in js
    assert ".toArray(" not in js
    assert "P0F79C_INVENTORY_JSON=" in js


def test_collector_does_not_touch_sensitive_or_mutating_operations() -> None:
    js = builder.build_js(_snapshot(), "sigesc")
    forbidden = (
        "students",
        "enrollments",
        "grades",
        "attendance",
        "insertOne",
        "insertMany",
        "updateOne",
        "updateMany",
        "deleteOne",
        "deleteMany",
        "replaceOne",
        "bulkWrite",
        "findOneAndUpdate",
    )
    for token in forbidden:
        assert token not in js


def test_db_name_is_validated() -> None:
    try:
        builder.build_js(_snapshot(), "sigesc;drop")
    except ValueError as exc:
        assert str(exc) == "DB_NAME_INVALID"
    else:
        raise AssertionError("invalid db name must be rejected")


def test_offline_inventory_selects_single_snapshot_under_conservative_limits() -> None:
    source = _snapshot()
    report = analyzer.validate(source, _inventory(source))
    assert report["status"] == "PASS"
    assert report["collection_strategy"] == "SINGLE_BOUNDED_TENANT_SNAPSHOT"
    assert report["safety"]["production_writes"] is False


def test_offline_inventory_selects_paging_when_assignment_limit_is_exceeded() -> None:
    source = _snapshot()
    report = analyzer.validate(source, _inventory(source, assignments=1001))
    assert report["collection_strategy"] == "PAGED_BY_SCHOOL_SNAPSHOT"


def test_offline_inventory_rejects_source_chain_drift() -> None:
    source = _snapshot()
    inventory = _inventory(source)
    inventory["source_p0f7_9a_snapshot_sha256"] = "0" * 64
    try:
        analyzer.validate(source, inventory)
    except ValueError as exc:
        assert str(exc) == "P0F7_9C_INVENTORY_SOURCE_CHAIN_MISMATCH"
    else:
        raise AssertionError("source chain drift must be rejected")
