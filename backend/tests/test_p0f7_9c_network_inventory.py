from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "backend" / "scripts" / "build_p0f7_9c_inventory_snapshot_js.py"

spec = importlib.util.spec_from_file_location("p0f79c_inventory", BUILDER)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def _snapshot() -> dict:
    return {
        "phase": mod.SOURCE_PHASE,
        "mode": mod.SOURCE_MODE,
        "query_budget": 8,
        "query_calls": 8,
        "class": {
            "mantenedora_id": "tenant-1",
            "academic_year": 2026,
        },
    }


def test_source_context_is_fail_closed_and_chained() -> None:
    ctx = mod._source_context(_snapshot())
    assert ctx["mantenedora_id"] == "tenant-1"
    assert ctx["academic_year"] == 2026
    assert len(ctx["source_p0f7_9a_snapshot_sha256"]) == 64


def test_missing_tenant_is_rejected() -> None:
    payload = _snapshot()
    payload["class"]["mantenedora_id"] = ""
    try:
        mod._source_context(payload)
    except ValueError as exc:
        assert str(exc) == "P0F7_9A_SOURCE_TENANT_MISSING_FAIL_CLOSED"
    else:
        raise AssertionError("missing tenant must fail closed")


def test_collector_is_counts_only_and_exactly_six_queries() -> None:
    js = mod.build_js(_snapshot(), "sigesc")
    assert "const QUERY_BUDGET = 6" in js
    assert js.count("countDocuments(") == 6
    assert ".find(" not in js
    assert ".aggregate(" not in js
    assert ".toArray(" not in js
    assert "P0F79C_INVENTORY_JSON=" in js


def test_collector_does_not_touch_sensitive_or_mutating_operations() -> None:
    js = mod.build_js(_snapshot(), "sigesc")
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
        mod.build_js(_snapshot(), "sigesc;drop")
    except ValueError as exc:
        assert str(exc) == "DB_NAME_INVALID"
    else:
        raise AssertionError("invalid db name must be rejected")
