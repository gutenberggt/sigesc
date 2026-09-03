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


def test_teacher_attribution_matches_actor_or_assignment_only():
    actor_ids = {"user-1", "staff-1"}
    assignment_ids = {"assignment-1", "assignment-old"}
    assert mod._teacher_attributed(
        {"recorded_by": "user-1"}, actor_ids=actor_ids, teacher_assignment_ids=assignment_ids
    )
    assert mod._teacher_attributed(
        {"staff_id": "staff-1"}, actor_ids=actor_ids, teacher_assignment_ids=assignment_ids
    )
    assert mod._teacher_attributed(
        {"assignment_id": "assignment-old"}, actor_ids=actor_ids, teacher_assignment_ids=assignment_ids
    )
    assert not mod._teacher_attributed(
        {"recorded_by": "other", "assignment_id": "foreign"},
        actor_ids=actor_ids,
        teacher_assignment_ids=assignment_ids,
    )
    assert not mod._teacher_attributed(
        {}, actor_ids=actor_ids, teacher_assignment_ids=assignment_ids
    )


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


def test_effective_binding_prefers_canonical_then_legacy_then_dvd():
    ids, source = mod._effective_binding(
        current_ids={"canonical"}, legacy_active_ids={"legacy"}, dvd_current_ids={"dvd"}
    )
    assert ids == {"canonical"}
    assert source == "canonical_diary"

    ids, source = mod._effective_binding(
        current_ids=set(), legacy_active_ids={"legacy"}, dvd_current_ids={"dvd"}
    )
    assert ids == {"legacy"}
    assert source == "legacy_active_teacher_assignment"

    ids, source = mod._effective_binding(
        current_ids=set(), legacy_active_ids=set(), dvd_current_ids={"dvd"}
    )
    assert ids == {"dvd"}
    assert source == "dvd_structural"


def test_classify_reproduces_ana_positive_control_identity_split_with_legacy_effective_binding():
    codes = mod._classify_pair(
        current_ids=set(),
        effective_binding_ids={"current-fundamental"},
        effective_binding_source="legacy_active_teacher_assignment",
        dvd_current_ids=set(),
        legacy_active_ids={"current-fundamental"},
        same_name_tenant_ids={"current-fundamental", "legacy-eja"},
        raw_data_ids={"legacy-eja"},
        attributed_data_ids={"legacy-eja"},
        attributed_counts={"legacy-eja": 24},
        assignment_drift_present=False,
        assignmentless_present=True,
        unresolved_attributed_refs=0,
        cross_tenant_attributed_refs=0,
        teacher_class_daily_without_course=0,
    )
    assert "NO_CURRENT_AUTHORIZED_DIARY" in codes
    assert "EFFECTIVE_BINDING_FROM_LEGACY_ASSIGNMENT" in codes
    assert "MULTIPLE_SAME_NAME_COMPONENT_IDENTITIES_IN_TENANT" in codes
    assert "CURRENT_BINDING_VS_SAME_NAME_DATA_IDENTITY_SPLIT" in codes
    assert "CURRENT_IDENTITY_EMPTY_ALT_IDENTITY_HAS_DATA" in codes
    assert "LEGACY_RECORDS_WITHOUT_ASSIGNMENT" in codes


def test_classify_does_not_attribute_other_teacher_data_to_target_teacher():
    codes = mod._classify_pair(
        current_ids={"current"},
        effective_binding_ids={"current"},
        effective_binding_source="canonical_diary",
        dvd_current_ids={"current"},
        legacy_active_ids={"current"},
        same_name_tenant_ids={"current", "other-id"},
        raw_data_ids={"other-id"},
        attributed_data_ids=set(),
        attributed_counts={},
        assignment_drift_present=False,
        assignmentless_present=False,
        unresolved_attributed_refs=0,
        cross_tenant_attributed_refs=0,
        teacher_class_daily_without_course=0,
    )
    assert "SAME_NAME_DATA_PRESENT_BUT_NOT_ATTRIBUTABLE_TO_TEACHER" in codes
    assert "CURRENT_BINDING_VS_SAME_NAME_DATA_IDENTITY_SPLIT" not in codes
    assert "CURRENT_IDENTITY_EMPTY_ALT_IDENTITY_HAS_DATA" not in codes


def test_classify_detects_aligned_current_identity():
    codes = mod._classify_pair(
        current_ids={"current"},
        effective_binding_ids={"current"},
        effective_binding_source="canonical_diary",
        dvd_current_ids={"current"},
        legacy_active_ids={"current"},
        same_name_tenant_ids={"current"},
        raw_data_ids={"current"},
        attributed_data_ids={"current"},
        attributed_counts={"current": 15},
        assignment_drift_present=False,
        assignmentless_present=False,
        unresolved_attributed_refs=0,
        cross_tenant_attributed_refs=0,
        teacher_class_daily_without_course=0,
    )
    assert "DATA_IDENTITY_ALIGNED_TO_CURRENT_BINDING" in codes
    assert "CURRENT_BINDING_VS_SAME_NAME_DATA_IDENTITY_SPLIT" not in codes


def test_classify_detects_binding_assignment_and_legacy_attendance_shape_risks():
    codes = mod._classify_pair(
        current_ids={"current"},
        effective_binding_ids={"current"},
        effective_binding_source="canonical_diary",
        dvd_current_ids={"current"},
        legacy_active_ids={"old"},
        same_name_tenant_ids={"current", "old"},
        raw_data_ids={"current", "old"},
        attributed_data_ids={"current", "old"},
        attributed_counts={"current": 2, "old": 20},
        assignment_drift_present=True,
        assignmentless_present=False,
        unresolved_attributed_refs=1,
        cross_tenant_attributed_refs=1,
        teacher_class_daily_without_course=3,
    )
    assert "LEGACY_BINDING_DIFFERS_FROM_CURRENT_BINDING" in codes
    assert "RECORDS_ON_HISTORICAL_SAME_TEACHER_ASSIGNMENT" in codes
    assert "CURRENT_BINDING_VS_SAME_NAME_DATA_IDENTITY_SPLIT" in codes
    assert "TEACHER_HAS_DATA_WITH_UNRESOLVED_COURSE_ID_IN_CLASS" in codes
    assert "CROSS_TENANT_SAME_NAME_COMPONENT_REFERENCE" in codes
    assert "TEACHER_ATTRIBUTED_CLASS_DAILY_ATTENDANCE_UNATTRIBUTED_TO_COMPONENT" in codes


def test_attendance_shape_preserves_legacy_aggregate_signal_without_inventing_aula_numero():
    result = mod._attendance_shape(
        [
            {"aula_numero": 1, "number_of_classes": None},
            {"aula_numero": None, "number_of_classes": 2},
            {"aula_numero": "", "number_of_classes": 1},
        ]
    )
    assert result == {
        "with_aula_numero": 1,
        "with_number_of_classes": 2,
        "without_aula_numero": 2,
    }
