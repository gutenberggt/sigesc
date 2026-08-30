import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).with_name("p0_250_f2_4_content_runtime_contract_audit.py")
spec = importlib.util.spec_from_file_location("p0_250_f2_4_content_runtime_contract_audit", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def test_zero_frontend_diaries_plus_backend_guard_is_runtime_contradiction():
    result = mod.analyze_runtime_contract(
        content_enabled_diary_count=0,
        legacy_guard_match_count=3,
        legacy_record_count=45,
        teacher_assignment_component_count=9,
        blocked_diary_count=16,
    )
    assert result["classification"] == "CONTENT_RUNTIME_LEGACY_FALLBACK_BLOCKED"
    assert result["runtime_contract_parity"] is False
    assert result["frontend_expected_route"] == "LEARNING_OBJECTS_LEGACY"
    assert result["backend_legacy_expected_status"] == 409
    assert result["stale_ui_risk_if_previous_records_exist"] is True


def test_zero_frontend_diaries_without_guard_allows_legacy_fallback():
    result = mod.analyze_runtime_contract(
        content_enabled_diary_count=0,
        legacy_guard_match_count=0,
        legacy_record_count=45,
        teacher_assignment_component_count=9,
    )
    assert result["classification"] == "CONTENT_RUNTIME_LEGACY_FALLBACK_AVAILABLE"
    assert result["runtime_contract_parity"] is True
    assert result["backend_legacy_expected_status"] == 200


def test_content_enabled_diary_routes_to_canonical_content():
    result = mod.analyze_runtime_contract(
        content_enabled_diary_count=9,
        legacy_guard_match_count=9,
        legacy_record_count=45,
        teacher_assignment_component_count=9,
    )
    assert result["classification"] == "CONTENT_RUNTIME_DVD_REWRITE_EXPECTED"
    assert result["runtime_contract_parity"] is True
    assert result["frontend_expected_route"] == "CONTENT_ENTRIES_DVD"


def test_entitlement_drift_has_priority():
    result = mod.analyze_runtime_contract(
        content_enabled_diary_count=0,
        legacy_guard_match_count=1,
        legacy_record_count=45,
        teacher_assignment_component_count=8,
    )
    assert result["classification"] == "PROFESSOR_CONTENT_ENTITLEMENT_DRIFT"
    assert result["runtime_contract_parity"] is False
