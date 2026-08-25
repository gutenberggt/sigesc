from pathlib import Path

import pytest

from scripts import prepare_dvd_second_wave_2d_j_migration_aware as subject


def _artifact(artifact_id: str):
    expected = subject.EXPECTED_ARTIFACTS[artifact_id]
    return {
        "id": artifact_id,
        "class_id": subject.base.CLASS_ID,
        "school_id": subject.base.SCHOOL_ID,
        "academic_year": subject.base.ACADEMIC_YEAR,
        "component_id": expected["component_id"],
        "teacher_id": subject.base.STAFF_ID,
        "valid_from": subject.EXPECTED_MIGRATION_VALID_FROM,
        "valid_until": subject.EXPECTED_MIGRATION_VALID_UNTIL,
        "deleted": False,
        "is_substitute": False,
        "source": subject.MIGRATION_SOURCE,
        "synthetic_validity": True,
        "migrated_from_legacy": True,
        "migration_run_id": subject.EXPECTED_MIGRATION_RUN_ID,
        "created_by": subject.MIGRATION_SOURCE,
    }


def _valid_artifacts():
    return [_artifact(artifact_id) for artifact_id in sorted(subject.EXPECTED_ARTIFACTS)]


def test_accepts_only_exact_legacy_migration_artifacts():
    evidence = subject.validate_legacy_migration_artifacts(_valid_artifacts())
    assert len(evidence) == 2
    assert {row["id"] for row in evidence} == set(subject.EXPECTED_ARTIFACTS)
    assert all(row["dvd_enabled"] is False for row in evidence)


def test_rejects_legacy_artifact_with_dvd_enabled():
    rows = _valid_artifacts()
    rows[0]["diary_settings"] = {"enabled": True, "profile": "regular"}
    with pytest.raises(subject.MigrationAwarePreflightError, match="dvd_not_enabled"):
        subject.validate_legacy_migration_artifacts(rows)


def test_rejects_wrong_source_or_wrong_teacher_identity():
    rows = _valid_artifacts()
    rows[0]["source"] = "import"
    with pytest.raises(subject.MigrationAwarePreflightError, match="source"):
        subject.validate_legacy_migration_artifacts(rows)

    rows = _valid_artifacts()
    rows[0]["teacher_id"] = subject.base.TEACHER_USER_ID
    with pytest.raises(subject.MigrationAwarePreflightError, match="teacher_is_staff_id"):
        subject.validate_legacy_migration_artifacts(rows)


def test_rejects_missing_or_extra_artifact():
    rows = _valid_artifacts()[:1]
    with pytest.raises(subject.MigrationAwarePreflightError, match="ARTIFACT_SET_MISMATCH"):
        subject.validate_legacy_migration_artifacts(rows)


class _FakeCollection:
    def __init__(self):
        self.queries = []

    def find(self, query=None, projection=None):
        self.queries.append((query, projection))
        return query


def test_proxy_hides_legacy_migration_only_from_current_class_conflict_query():
    fake = _FakeCollection()
    proxy = subject._TeacherClassAssignmentsProxy(fake)

    current_query = {
        "class_id": subject.base.CLASS_ID,
        "deleted": {"$ne": True},
    }
    returned = proxy.find(current_query, {"_id": 0})
    assert returned["source"] == {"$ne": subject.MIGRATION_SOURCE}

    peer_query = {
        "class_id": {"$in": [subject.base.CLASS_ID]},
        "component_id": {"$in": ["x"]},
        "deleted": {"$ne": True},
    }
    returned_peer = proxy.find(peer_query, {"_id": 0})
    assert "source" not in returned_peer


def test_script_is_read_only_and_has_no_apply_tokens():
    subject.assert_script_read_only()
    path = Path(subject.__file__)
    src = path.read_text(encoding="utf-8")
    assert "--apply" not in src
    assert "--rollback" not in src
    assert "legacy_migration" in src
    assert "collect_backup_bundle" in src
