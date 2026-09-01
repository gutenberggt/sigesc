from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

pymongo_stub = types.ModuleType("pymongo")
pymongo_stub.MongoClient = object
sys.modules["pymongo"] = pymongo_stub

planner_stub = types.ModuleType("p0_250_f2_9a_global_dvd_reconciliation_plan")
planner_stub.ACADEMIC_YEAR = 2026
planner_stub.REFERENCE_DATE = "2026-09-01"
planner_stub.OPERATIONAL_DVD = "OPERATIONAL_DVD"
planner_stub.DiaryAssignmentAccessError = RuntimeError
sys.modules[planner_stub.__name__] = planner_stub

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ana_lucia_f2_canonical_remediation_dry_run.py"
spec = importlib.util.spec_from_file_location("ana_lucia_f2", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def test_authorized_target_has_exactly_17_unique_pairs():
    assert len(mod.TARGET_PAIRS) == 17
    assert len(set(mod.TARGET_PAIRS)) == 17
    assert ("6º ANO A", "Língua Inglesa") in mod.TARGET_PAIRS
    assert ("8º ANO C", "Estudos Amazônicos") in mod.TARGET_PAIRS


def test_content_before_or_on_cutover_stays_read_only_legacy():
    assert mod.classify_legacy_content(
        record_date="2026-06-01",
        valid_from="2026-08-18",
        binding_ready=True,
    ) == "KEEP_LEGACY_READ_ONLY_BRIDGE"
    assert mod.classify_legacy_content(
        record_date="2026-08-18",
        valid_from="2026-08-18",
        binding_ready=True,
    ) == "KEEP_LEGACY_READ_ONLY_BRIDGE"


def test_content_after_cutover_is_future_canonical_backfill_candidate():
    assert mod.classify_legacy_content(
        record_date="2026-09-01",
        valid_from="2026-08-18",
        binding_ready=True,
    ) == "PLAN_CONTENT_CANONICAL_BACKFILL"


def test_content_overlap_is_never_auto_planned():
    assert mod.classify_legacy_content(
        record_date="2026-09-01",
        valid_from="2026-08-18",
        binding_ready=True,
        canonical_same_date_exists=True,
    ) == "REVIEW_CANONICAL_CONTENT_OVERLAP"


def test_content_is_blocked_without_canonical_binding():
    assert mod.classify_legacy_content(
        record_date="2026-09-01",
        valid_from=None,
        binding_ready=False,
    ) == "BLOCKED_BY_CANONICAL_BINDING"


def test_attendance_pre_cutover_is_preserved_without_retro_assignment():
    assert mod.classify_legacy_attendance(
        record_date="2026-06-01",
        valid_from="2026-08-18",
        binding_ready=True,
    ) == "KEEP_LEGACY_HISTORICAL_ACCESS"


def test_attendance_on_or_after_cutover_requires_review_not_retag():
    assert mod.classify_legacy_attendance(
        record_date="2026-08-18",
        valid_from="2026-08-18",
        binding_ready=True,
    ) == "REVIEW_POST_CUTOVER_UNASSIGNED_ATTENDANCE"
    assert mod.classify_legacy_attendance(
        record_date="2026-09-01",
        valid_from="2026-08-18",
        binding_ready=True,
    ) == "REVIEW_POST_CUTOVER_UNASSIGNED_ATTENDANCE"


def test_classification_fails_closed_on_binding_review():
    pairs = [{
        "canonical_decision": "REQUIRES_REVIEW",
        "record_plan": {"content_action_counts": {}, "attendance_action_counts": {}},
    }]
    assert mod._classification(pairs) == "ANA_LUCIA_F2_REVIEW_REQUIRED"


def test_classification_marks_post_cutover_attendance_as_partial_review():
    pairs = [{
        "canonical_decision": "PLAN_CREATE_CANONICAL_ASSIGNMENT",
        "record_plan": {
            "content_action_counts": {},
            "attendance_action_counts": {"REVIEW_POST_CUTOVER_UNASSIGNED_ATTENDANCE": 1},
        },
    }]
    assert mod._classification(pairs) == "ANA_LUCIA_F2_PARTIAL_REVIEW_REQUIRED"


def test_name_normalization_handles_accents_and_ordinals():
    assert mod._norm("Língua Inglesa") == mod._norm("LINGUA INGLESA")
    assert mod._norm("6º ANO C") == mod._norm("6o ano c")
    assert mod._norm("3ª ETAPA") == mod._norm("3a etapa")
