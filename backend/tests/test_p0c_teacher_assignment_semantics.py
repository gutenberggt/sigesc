from __future__ import annotations

import importlib.util
from pathlib import Path

from services.teacher_class_assignment_semantics import (
    LEGACY_MIGRATION_DRIFT,
    LEGACY_MIGRATION_SYNTHETIC,
    LEGACY_MIGRATION_SYNTHETIC_UNASSIGNED,
    OPERATIONAL_DVD,
    classify_teacher_class_assignment,
    partition_teacher_class_assignments,
)


ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCRIPT = ROOT / "scripts" / "audit_teacher_binding_integrity_p0_semantic.py"
PREFLIGHT_SCRIPT = ROOT / "scripts" / "preflight_teacher_identity_remediation_p0c_semantic.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


AUDIT = _load(AUDIT_SCRIPT, "p0c_semantic_audit")
PREFLIGHT = _load(PREFLIGHT_SCRIPT, "p0c_semantic_preflight")


def valid_legacy_row(**overrides):
    row = {
        "id": "legacy::class-1::course-1::staff-1",
        "teacher_id": "staff-1",
        "class_id": "class-1",
        "component_id": "course-1",
        "source": "legacy_migration",
        "migrated_from_legacy": True,
        "synthetic_validity": True,
        "created_by": "legacy_migration",
        "migration_run_id": "run-1",
        "diary_settings": {},
        "deleted": False,
    }
    row.update(overrides)
    return row


def valid_unassigned_legacy_row(**overrides):
    row = valid_legacy_row(
        id="legacy::class-1::course-1::none",
        teacher_id=None,
    )
    row.update(overrides)
    return row


def test_valid_legacy_migration_is_synthetic_not_operational():
    semantic = classify_teacher_class_assignment(valid_legacy_row())
    assert semantic.kind == LEGACY_MIGRATION_SYNTHETIC
    assert semantic.drift_reasons == ()


def test_valid_unassigned_legacy_migration_is_explicit_synthetic_bucket():
    semantic = classify_teacher_class_assignment(valid_unassigned_legacy_row())
    assert semantic.kind == LEGACY_MIGRATION_SYNTHETIC_UNASSIGNED
    assert semantic.drift_reasons == ()


def test_unassigned_without_none_suffix_fails_closed_as_drift():
    semantic = classify_teacher_class_assignment(
        valid_unassigned_legacy_row(id="legacy::class-1::course-1::staff-missing")
    )
    assert semantic.kind == LEGACY_MIGRATION_DRIFT
    assert "UNASSIGNED_ID_NOT_NONE" in semantic.drift_reasons


def test_teacher_present_with_none_suffix_fails_closed_as_drift():
    semantic = classify_teacher_class_assignment(
        valid_legacy_row(id="legacy::class-1::course-1::none")
    )
    assert semantic.kind == LEGACY_MIGRATION_DRIFT
    assert "TEACHER_PRESENT_WITH_NONE_ID" in semantic.drift_reasons


def test_enabled_unassigned_legacy_migration_still_fails_closed():
    semantic = classify_teacher_class_assignment(
        valid_unassigned_legacy_row(diary_settings={"enabled": True})
    )
    assert semantic.kind == LEGACY_MIGRATION_DRIFT
    assert "DVD_ENABLED_TRUE" in semantic.drift_reasons


def test_enabled_legacy_migration_fails_closed_as_drift():
    semantic = classify_teacher_class_assignment(
        valid_legacy_row(diary_settings={"enabled": True})
    )
    assert semantic.kind == LEGACY_MIGRATION_DRIFT
    assert "DVD_ENABLED_TRUE" in semantic.drift_reasons


def test_missing_official_marker_is_drift():
    semantic = classify_teacher_class_assignment(
        valid_legacy_row(synthetic_validity=False)
    )
    assert semantic.kind == LEGACY_MIGRATION_DRIFT
    assert "SYNTHETIC_VALIDITY_NOT_TRUE" in semantic.drift_reasons


def test_non_migration_source_remains_operational():
    semantic = classify_teacher_class_assignment({
        "id": "dvd-1",
        "teacher_id": "user-1",
        "class_id": "class-1",
        "component_id": "course-1",
        "source": "import",
        "diary_settings": {"enabled": True},
    })
    assert semantic.kind == OPERATIONAL_DVD


def test_partition_keeps_four_populations_explicit():
    rows = [
        valid_legacy_row(),
        valid_unassigned_legacy_row(),
        valid_legacy_row(id="bad", synthetic_validity=False),
        {"id": "dvd", "source": "import"},
    ]
    result = partition_teacher_class_assignments(rows)
    assert len(result[LEGACY_MIGRATION_SYNTHETIC]) == 1
    assert len(result[LEGACY_MIGRATION_SYNTHETIC_UNASSIGNED]) == 1
    assert len(result[LEGACY_MIGRATION_DRIFT]) == 1
    assert len(result[OPERATIONAL_DVD]) == 1


def test_binding_scan_detection_does_not_filter_course_reference_scan():
    binding_projection = {
        "teacher_id": 1,
        "component_id": 1,
        "valid_from": 1,
        "valid_until": 1,
    }
    course_reference_projection = {
        "id": 1,
        "class_id": 1,
        "component_id": 1,
        "academic_year": 1,
    }
    assert AUDIT._binding_identity_scan({}, binding_projection) is True
    assert AUDIT._binding_identity_scan({}, course_reference_projection) is False


class FakeCollection:
    def __init__(self):
        self.last_query = None
        self.last_projection = None

    def find(self, query=None, projection=None, *args, **kwargs):
        self.last_query = query
        self.last_projection = projection
        return self


def test_semantic_proxy_filters_only_identity_scan():
    raw = FakeCollection()
    proxy = AUDIT._SemanticCollectionProxy(raw)

    projection = {
        "teacher_id": 1,
        "component_id": 1,
        "valid_from": 1,
        "valid_until": 1,
    }
    proxy.find({"deleted": {"$ne": True}}, projection)
    assert raw.last_query == {
        "$and": [
            {"deleted": {"$ne": True}},
            {"source": {"$ne": "legacy_migration"}},
        ]
    }

    reference_projection = {"component_id": 1, "class_id": 1}
    proxy.find({"component_id": {"$exists": True}}, reference_projection)
    assert raw.last_query == {"component_id": {"$exists": True}}


def test_new_auditors_have_no_apply_mode_and_read_only_guards():
    assert "--apply" not in AUDIT_SCRIPT.read_text(encoding="utf-8")
    assert "--apply" not in PREFLIGHT_SCRIPT.read_text(encoding="utf-8")
    AUDIT.assert_read_only()
    PREFLIGHT.assert_read_only()


def test_semantic_preflight_version_is_explicit():
    assert PREFLIGHT.MANIFEST_VERSION == 3
    assert "SEMANTIC-V3" in PREFLIGHT.PHASE_ID
