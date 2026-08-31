from pathlib import Path
import importlib.util
import sys
from types import SimpleNamespace

import pytest

BACKEND = Path(__file__).parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

SCRIPT = BACKEND / "scripts" / "p0_250_f2_9b_seal_safe_backfill_targets.py"
spec = importlib.util.spec_from_file_location("p0_250_f2_9b", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def make_target(index=1, *, owner=False):
    return {
        "id": f"target-{index}",
        "teacher_id": f"user-{index}",
        "class_id": f"class-{index // 4}",
        "component_id": f"course-{index}",
        "school_id": "school-1",
        "mantenedora_id": "tenant-1",
        "deleted": False,
        "valid_from": "2026-02-01",
        "valid_until": None,
        "diary_settings": {
            "enabled": True,
            "schema_version": 1,
            "profile": "regular",
            "student_scope": "all",
        },
        "is_substitute": False,
        "grades_official_owner": owner,
        "shift": "matutino",
    }


def make_manifest(count=48):
    rows = []
    for index in range(1, count + 1):
        rows.append(
            {
                "teacher_key": f"staff-{index}",
                "class_key": f"class-{index // 4}",
                "component_key": f"course-{index}",
                "decision": "PLAN_CREATE_CANONICAL_ASSIGNMENT",
                "review_reasons": [],
                "target_assignment": make_target(index),
            }
        )
    return rows


def approved_snapshot():
    return {
        "status": "PASS",
        "classification": module.SOURCE_CLASSIFICATION,
        "database_mutation": False,
        "production_writes": False,
        "http_methods": [],
        "mongo_reads_only": True,
        "academic_data_read": False,
        "record_content_emitted": False,
        "record_ids_emitted": False,
        "assignment_ids_emitted": False,
        "teacher_ids_emitted": False,
        "staff_ids_emitted": False,
        "student_data_read": False,
        "student_pii_emitted": False,
        "user_pii_emitted": False,
        "plan_payload_emitted": False,
        "analysis": {
            "plan_sha256": module.SOURCE_PLAN_SHA256,
            "decision_manifest_sha256": module.SOURCE_DECISION_SHA256,
            "input_state_sha256": module.SOURCE_INPUT_SHA256,
            "plan_namespace_sha256": module.SOURCE_NAMESPACE_SHA256,
            "academic_year": 2026,
            "reference_date": "2026-08-31",
            "plan_create_count": 48,
            "review_count": 883,
            "active_legacy_component_pairs": 2218,
            "decision_counts": dict(module.APPROVED_DECISIONS),
            "automatic_apply_authorized": False,
        },
    }


def test_source_snapshot_exact_contract_passes():
    module.assert_source_snapshot(approved_snapshot())


def test_source_snapshot_hash_drift_is_fail_closed():
    payload = approved_snapshot()
    payload["analysis"]["input_state_sha256"] = "0" * 64
    with pytest.raises(module.F29BSealError, match="F2_9A_SEAL_DRIFT_input_state_sha256"):
        module.assert_source_snapshot(payload)


def test_capture_reuses_planner_manifest_builder_and_restores_it():
    manifest = make_manifest(1)

    class FakePlanner:
        def _decision_manifest_rows(self, rows):
            return list(rows)

        def run_live_plan(self):
            self._decision_manifest_rows(manifest)
            return {"status": "PASS"}

    planner = FakePlanner()
    original = planner._decision_manifest_rows.__func__
    snapshot, captured = module.capture_planner_material(planner)
    assert snapshot == {"status": "PASS"}
    assert captured == manifest
    assert planner._decision_manifest_rows.__func__ is original


def test_extract_targets_accepts_generic_48_when_seals_match(monkeypatch):
    manifest = make_manifest(48)
    fake = SimpleNamespace(_sha256_value=module.sha256_value)
    monkeypatch.setattr(module, "SOURCE_DECISION_SHA256", module.sha256_value(manifest))
    targets = [row["target_assignment"] for row in manifest]
    monkeypatch.setattr(module, "SOURCE_PLAN_SHA256", module.sha256_value(targets))

    rows = module.extract_targets(fake, manifest)
    assert len(rows) == 48


def test_extract_targets_rejects_duplicate_natural_key(monkeypatch):
    manifest = make_manifest(48)
    manifest[1]["target_assignment"]["teacher_id"] = manifest[0]["target_assignment"]["teacher_id"]
    manifest[1]["target_assignment"]["class_id"] = manifest[0]["target_assignment"]["class_id"]
    manifest[1]["target_assignment"]["component_id"] = manifest[0]["target_assignment"]["component_id"]
    fake = SimpleNamespace(_sha256_value=module.sha256_value)
    monkeypatch.setattr(module, "SOURCE_DECISION_SHA256", module.sha256_value(manifest))
    monkeypatch.setattr(
        module,
        "SOURCE_PLAN_SHA256",
        module.sha256_value([row["target_assignment"] for row in manifest]),
    )
    with pytest.raises(module.F29BSealError, match="TARGET_DUPLICATE_KEY"):
        module.extract_targets(fake, manifest)


def test_private_bundle_is_deterministic_and_public_receipt_hides_ids(monkeypatch):
    rows = make_manifest(48)
    targets = [row["target_assignment"] for row in rows]
    monkeypatch.setattr(module, "SOURCE_PLAN_SHA256", module.sha256_value(targets))
    checks = [
        {
            "ordinal": index,
            "source_legacy_count": 1,
            "target_id_count": 0,
            "other_teacher_official_grade_owner_count": 0,
        }
        for index in range(1, 49)
    ]
    snap = approved_snapshot()
    snap["analysis"]["plan_sha256"] = module.SOURCE_PLAN_SHA256

    first = module.build_private_bundle(snap, rows, checks)
    second = module.build_private_bundle(snap, rows, checks)
    assert first == second
    assert first["expected_target_count"] == 48
    assert len(first["operations"]) == 48

    public = module.build_public_receipt(first)
    assert public["target_count"] == 48
    assert public["apply_authorized"] is False
    assert "operations" not in public
    assert "target_assignment" not in public
    assert "teacher_id" not in public


class CountingCollection:
    def __init__(self, handler):
        self.handler = handler

    def count_documents(self, query):
        return self.handler(query)


class FakeDb:
    def __init__(self, owner_conflict=0):
        self.teacher_assignments = CountingCollection(lambda query: 1)

        def dvd_count(query):
            if set(query.keys()) == {"id"}:
                return 0
            if query.get("grades_official_owner") is True:
                return owner_conflict
            return 0

        self.teacher_class_assignments = CountingCollection(dvd_count)


def test_live_preconditions_are_read_only_counts():
    rows = make_manifest(1)
    rows[0]["target_assignment"]["grades_official_owner"] = True
    checks = module.collect_preconditions(FakeDb(owner_conflict=0), rows)
    assert checks == [
        {
            "ordinal": 1,
            "source_legacy_count": 1,
            "target_id_count": 0,
            "other_teacher_official_grade_owner_count": 0,
        }
    ]


def test_official_grade_owner_conflict_blocks_seal():
    rows = make_manifest(1)
    rows[0]["target_assignment"]["grades_official_owner"] = True
    with pytest.raises(module.F29BSealError, match="OFFICIAL_GRADE_OWNER_CONFLICT_AT_1"):
        module.collect_preconditions(FakeDb(owner_conflict=1), rows)
