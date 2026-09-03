from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "teacher_visibility_f1_readonly.py"
spec = importlib.util.spec_from_file_location("teacher_visibility_f1", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def test_cases_are_school_pinned_and_total_23_pairs():
    assert len(mod.CASES) == 2
    assert sum(len(case["pairs"]) for case in mod.CASES) == 23
    assert mod.CASES[0]["school"] == "E M E I E F Monsenhor Augusto Dias de Brito"
    assert mod.CASES[1]["school"] == "E M E I E F Jose Pereira Barbosa"
    assert len(mod.CASES[1]["pairs"]) == 6
    assert all(component == "Matemática" for _class, component in mod.CASES[1]["pairs"])


def test_name_normalization_handles_accents_ordinals_and_alias():
    assert mod._norm("Matemática") == mod._norm("MATEMATICA")
    assert mod._norm("6º ANO A") == mod._norm("6o ano a")
    assert mod._norm("3ª ETAPA") == mod._norm("3a etapa")
    assert mod._norm("Ana Lucia Faria Pinto Tristão") != mod._norm("Ana Lucia Faria Pinto")
    assert mod._norm("Ana Lucia Faria Pinto") in {
        mod._norm(value) for value in mod.CASES[0]["teacher_aliases"]
    }


def test_fingerprint_never_exposes_raw_identifier():
    raw = "sensitive-course-id"
    value = mod._fp(raw)
    assert value
    assert value != raw
    assert len(value) == 12


def test_assignment_partition_distinguishes_current_historical_and_legacy():
    rows = [
        {"assignment_id": "current"},
        {"assignment_id": "historical"},
        {"assignment_id": None},
        {"assignment_id": "foreign"},
    ]
    result = mod._partition_assignment_rows(
        rows,
        current_assignment_ids={"current"},
        same_teacher_assignment_ids={"current", "historical"},
    )
    assert result == {
        "current_assignment": 1,
        "historical_same_teacher_assignment": 1,
        "without_assignment": 1,
        "foreign_or_unknown_assignment": 1,
    }


def test_classify_detects_same_name_identity_split():
    codes = mod._classify_pair(
        current_ids={"current"},
        dvd_current_ids={"current"},
        legacy_active_ids={"current"},
        same_name_tenant_ids={"current", "legacy-data"},
        data_ids={"legacy-data"},
        data_counts={"legacy-data": 24},
        assignment_drift_present=False,
        assignmentless_present=True,
        unknown_course_refs=0,
        cross_tenant_same_name_refs=0,
    )
    assert "MULTIPLE_SAME_NAME_COMPONENT_IDENTITIES_IN_TENANT" in codes
    assert "CURRENT_BINDING_VS_SAME_NAME_DATA_IDENTITY_SPLIT" in codes
    assert "CURRENT_IDENTITY_EMPTY_ALT_IDENTITY_HAS_DATA" in codes
    assert "LEGACY_RECORDS_WITHOUT_ASSIGNMENT" in codes


def test_classify_detects_aligned_current_identity():
    codes = mod._classify_pair(
        current_ids={"current"},
        dvd_current_ids={"current"},
        legacy_active_ids={"current"},
        same_name_tenant_ids={"current"},
        data_ids={"current"},
        data_counts={"current": 15},
        assignment_drift_present=False,
        assignmentless_present=False,
        unknown_course_refs=0,
        cross_tenant_same_name_refs=0,
    )
    assert "DATA_IDENTITY_ALIGNED_TO_CURRENT_BINDING" in codes
    assert "CURRENT_BINDING_VS_SAME_NAME_DATA_IDENTITY_SPLIT" not in codes


def test_classify_detects_binding_and_assignment_drift():
    codes = mod._classify_pair(
        current_ids={"current"},
        dvd_current_ids={"current"},
        legacy_active_ids={"old"},
        same_name_tenant_ids={"current", "old"},
        data_ids={"current", "old"},
        data_counts={"current": 2, "old": 20},
        assignment_drift_present=True,
        assignmentless_present=False,
        unknown_course_refs=0,
        cross_tenant_same_name_refs=0,
    )
    assert "LEGACY_BINDING_DIFFERS_FROM_CURRENT_BINDING" in codes
    assert "RECORDS_ON_HISTORICAL_SAME_TEACHER_ASSIGNMENT" in codes
    assert "CURRENT_BINDING_VS_SAME_NAME_DATA_IDENTITY_SPLIT" in codes


def test_classify_flags_unknown_and_cross_tenant_references():
    codes = mod._classify_pair(
        current_ids=set(),
        dvd_current_ids=set(),
        legacy_active_ids=set(),
        same_name_tenant_ids=set(),
        data_ids=set(),
        data_counts={},
        assignment_drift_present=False,
        assignmentless_present=False,
        unknown_course_refs=2,
        cross_tenant_same_name_refs=1,
    )
    assert "NO_CURRENT_AUTHORIZED_DIARY" in codes
    assert "TARGET_COMPONENT_DATA_NOT_FOUND" in codes
    assert "CLASS_HAS_DATA_WITH_UNRESOLVED_COURSE_ID" in codes
    assert "CROSS_TENANT_SAME_NAME_COMPONENT_REFERENCE" in codes
