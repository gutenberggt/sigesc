from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ana_lucia_f2_3_english_identity_provenance_readonly.py"
SERVICE = Path(__file__).resolve().parents[1] / "services" / "course_reference_integrity.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("ana_lucia_f2_3", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_split_classification_current_binding_vs_legacy_data():
    mod = _load_module()
    assert mod.classify_split(
        target_binding_current=8,
        target_binding_legacy=0,
        current_content_2026=0,
        legacy_content_2026=198,
        current_attendance_2026=5,
        legacy_attendance_2026=392,
    ) == "CURRENT_BINDING_VS_LEGACY_DATA_IDENTITY_SPLIT"


def test_split_classification_mixed_binding_is_review():
    mod = _load_module()
    assert mod.classify_split(
        target_binding_current=7,
        target_binding_legacy=1,
        current_content_2026=0,
        legacy_content_2026=1,
        current_attendance_2026=0,
        legacy_attendance_2026=1,
    ) == "MIXED_ACTIVE_BINDINGS_REQUIRE_REVIEW"


def test_creation_order_is_metadata_only():
    mod = _load_module()
    assert mod.classify_creation_order("2026-05-01T00:00:00", "2025-01-01T00:00:00") == "CURRENT_ID_CREATED_AFTER_LEGACY_ID"
    assert mod.classify_creation_order("2025-01-01T00:00:00", "2026-05-01T00:00:00") == "CURRENT_ID_CREATED_BEFORE_LEGACY_ID"
    assert mod.classify_creation_order(None, "2026-05-01T00:00:00") == "COURSE_CREATION_ORDER_UNKNOWN"


def test_p0_identity_collision_requires_same_tenant_name_and_level():
    mod = _load_module()
    current = {"name": "Língua Inglesa", "mantenedora_id": "TENANT", "nivel_ensino": "Fundamental II"}
    legacy = {"name": "língua inglesa", "mantenedora_id": "TENANT", "nivel_ensino": "fundamental ii"}
    assert mod.classify_p0_identity(current, legacy) == "P0_DUPLICATE_IDENTITY_KEY_COLLISION"
    legacy["nivel_ensino"] = "EJA"
    assert mod.classify_p0_identity(current, legacy) == "SAME_TENANT_AND_NAME_DIFFERENT_LEVEL_IDENTITY"


def test_reference_specs_remain_aligned_with_ssot():
    mod = _load_module()
    source = SERVICE.read_text(encoding="utf-8")
    for collection, field, label in mod.REFERENCE_SPECS:
        marker = f'CourseReferenceSpec("{collection}", "{field}", "{label}")'
        assert marker in source


def test_read_only_and_privacy_boundary_is_structural():
    source = SCRIPT.read_text(encoding="utf-8")
    forbidden_calls = (
        ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
        ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
        ".find_one_and_update(", ".find_one_and_delete(", ".find_one_and_replace(",
    )
    assert not any(token in source for token in forbidden_calls)
    for forbidden_read in (
        "db.students", "db.enrollments", "db.student_health_profiles",
        '"records": 1', "'records': 1",
        '"b1": 1', '"b2": 1', '"b3": 1', '"b4": 1',
        '"description": 1', '"old_value": 1', '"new_value": 1',
    ):
        assert forbidden_read not in source
    for marker in (
        '"database_mutation": False',
        '"production_writes": False',
        '"mongo_reads_only": True',
        '"http_methods": []',
        '"attendance_records_read": False',
        '"student_data_read": False',
        '"grade_values_read": False',
        '"attendance_status_values_read": False',
        '"pedagogical_text_read": False',
        '"technical_ids_emitted": False',
        '"audit_old_new_values_projected": False',
        '"automatic_merge_authorized": False',
        '"automatic_remap_authorized": False',
    ):
        assert marker in source
