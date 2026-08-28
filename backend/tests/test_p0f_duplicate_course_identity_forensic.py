from __future__ import annotations

import importlib.util
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "scripts" / "audit_duplicate_course_identity_p0f.py"


def load_module():
    spec = importlib.util.spec_from_file_location("audit_duplicate_course_identity_p0f", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_phase_is_explicit_and_read_only():
    module = load_module()
    assert module.PHASE_ID == "P0F-DUPLICATE-COURSE-IDENTITY-FORENSIC-READ-ONLY-2026"
    assert module.MANIFEST_VERSION == 1
    module.assert_read_only()


def test_no_apply_or_rollback_mode_exists():
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"--apply"' not in source
    assert '"--rollback"' not in source


def test_identity_matches_p0_global_semantics():
    module = load_module()
    a = {
        "mantenedora_id": "TENANT-1",
        "name": "Matemática",
        "nivel_ensino": "Fundamental",
    }
    b = {
        "mantenedora_id": "TENANT-1",
        "name": "MATEMÁTICA",
        "nivel_ensino": "FUNDAMENTAL",
    }
    assert module.course_identity_key(a) == module.course_identity_key(b)


def test_identity_does_not_cross_tenants():
    module = load_module()
    a = {"mantenedora_id": "A", "name": "Arte", "nivel_ensino": "EF"}
    b = {"mantenedora_id": "B", "name": "Arte", "nivel_ensino": "EF"}
    assert module.course_identity_key(a) != module.course_identity_key(b)


def test_duplicate_counter_unit_is_group_not_record():
    module = load_module()
    courses = [
        {"id": "1", "mantenedora_id": "T", "name": "Arte", "nivel_ensino": "EF"},
        {"id": "2", "mantenedora_id": "T", "name": "ARTE", "nivel_ensino": "ef"},
        {"id": "3", "mantenedora_id": "T", "name": "Arte", "nivel_ensino": "EF"},
        {"id": "4", "mantenedora_id": "T", "name": "Ciências", "nivel_ensino": "EF"},
    ]
    groups = module.build_duplicate_groups(courses)
    assert len(groups) == 1
    assert len(groups[0][1]) == 3


def test_empty_name_is_not_reported_as_duplicate_identity():
    module = load_module()
    courses = [
        {"id": "1", "mantenedora_id": "T", "name": "", "nivel_ensino": "EF"},
        {"id": "2", "mantenedora_id": "T", "name": None, "nivel_ensino": "EF"},
    ]
    assert module.build_duplicate_groups(courses) == []


def test_reference_distribution_never_declares_automatic_safe_consolidation():
    module = load_module()
    assert module.classify_reference_distribution({"a": 0, "b": 0}, history_found=False) == (
        "NO_REGISTERED_REFERENCES_REQUIRES_REVIEW"
    )
    assert module.classify_reference_distribution({"a": 10, "b": 0}, history_found=False) == (
        "ONE_REFERENCED_ID_OTHERS_UNUSED_REQUIRES_REVIEW"
    )
    assert module.classify_reference_distribution({"a": 10, "b": 3}, history_found=False) == (
        "MULTIPLE_REFERENCED_IDS_REQUIRES_REVIEW"
    )
    assert module.classify_reference_distribution({"a": 0, "b": 0}, history_found=True) == (
        "AUDIT_HISTORY_FOUND_REQUIRES_REVIEW"
    )


def test_safe_context_excludes_pedagogical_payload():
    module = load_module()
    row = {
        "id": "doc-1",
        "class_id": "class-1",
        "course_id": "course-1",
        "content": "conteúdo pedagógico",
        "notes": "não deve entrar",
        "student_id": "student-1",
    }
    safe = module.safe_context(row)
    assert safe["id"] == "doc-1"
    assert safe["class_id"] == "class-1"
    assert safe["student_id"] == "student-1"
    assert "content" not in safe
    assert "notes" not in safe


def test_manifest_sha_is_deterministic():
    module = load_module()
    a = {"b": 2, "a": [3, 1]}
    b = {"a": [3, 1], "b": 2}
    assert module._canonical_json_sha256(a) == module._canonical_json_sha256(b)
