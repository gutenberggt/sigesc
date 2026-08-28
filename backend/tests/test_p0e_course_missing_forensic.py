from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_course_missing_p0e.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


P0E = _load(SCRIPT, "p0e_course_missing")


def test_read_only_guard_and_no_apply_mode():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "--apply" not in source
    assert "--rollback" not in source
    P0E.assert_read_only()


def test_phase_and_manifest_version_are_explicit():
    assert P0E.PHASE_ID == "P0E-COURSE-MISSING-FORENSIC-READ-ONLY-2026"
    assert P0E.MANIFEST_VERSION == 1


def test_same_year_accepts_missing_and_string_year():
    assert P0E._same_year(None, 2026)
    assert P0E._same_year("", 2026)
    assert P0E._same_year("2026", 2026)
    assert P0E._same_year(2026, 2026)
    assert not P0E._same_year(2025, 2026)


def test_exact_identity_candidate_requires_tenant_name_and_level():
    current = [
        {
            "id": "course-ok",
            "name": "Matemática",
            "nivel_ensino": "Fundamental",
            "mantenedora_id": "tenant-1",
            "status": "active",
        },
        {
            "id": "wrong-tenant",
            "name": "Matemática",
            "nivel_ensino": "Fundamental",
            "mantenedora_id": "tenant-2",
        },
        {
            "id": "wrong-level",
            "name": "Matemática",
            "nivel_ensino": "Médio",
            "mantenedora_id": "tenant-1",
        },
    ]
    historical = {
        "name": " matemática ",
        "nivel_ensino": "fundamental",
        "mantenedora_id": "tenant-1",
    }
    candidates = P0E.exact_identity_candidates(historical, current)
    assert [x["id"] for x in candidates] == ["course-ok"]


def test_exact_identity_candidate_fails_closed_when_identity_incomplete():
    current = [{
        "id": "course-1",
        "name": "Matemática",
        "nivel_ensino": "Fundamental",
        "mantenedora_id": "tenant-1",
    }]
    assert P0E.exact_identity_candidates(
        {"name": "Matemática", "nivel_ensino": "Fundamental"},
        current,
    ) == []


def test_merge_candidate_requires_missing_id_in_removed_ids():
    logs = [{
        "extra_data": {
            "consolidated": [
                {
                    "kept_id": "kept-1",
                    "removed_ids": ["missing-1", "removed-2"],
                },
                {
                    "kept_id": "kept-2",
                    "removed_ids": ["other"],
                },
            ]
        }
    }]
    assert P0E._merge_candidates("missing-1", logs) == ["kept-1"]
    assert P0E._merge_candidates("not-there", logs) == []


def test_historical_snapshot_comes_only_from_audit_value():
    logs = [
        {
            "old_value": {
                "id": "missing-1",
                "name": "Ciências",
                "nivel_ensino": "Fundamental",
                "mantenedora_id": "tenant-1",
            }
        }
    ]
    snapshot = P0E._historical_course_from_logs("missing-1", logs)
    assert snapshot == {
        "id": "missing-1",
        "name": "Ciências",
        "nivel_ensino": "Fundamental",
        "mantenedora_id": "tenant-1",
        "source": "audit_logs.old_value",
    }


def test_historical_snapshot_rejects_other_explicit_id():
    logs = [{
        "old_value": {
            "id": "another-course",
            "name": "Ciências",
            "nivel_ensino": "Fundamental",
            "mantenedora_id": "tenant-1",
        }
    }]
    assert P0E._historical_course_from_logs("missing-1", logs) is None


def test_safe_reference_context_does_not_dump_pedagogical_payload():
    row = {
        "id": "doc-1",
        "class_id": "class-1",
        "student_id": "student-1",
        "records": [{"student_id": "s", "present": False}],
        "grades": {"b1": 10},
        "notes": "private payload",
    }
    safe = P0E._safe_reference_context(row)
    assert safe == {
        "id": "doc-1",
        "class_id": "class-1",
        "student_id": "student-1",
    }
    assert "records" not in safe
    assert "grades" not in safe
    assert "notes" not in safe


def test_canonical_sha_is_deterministic():
    a = {"b": 2, "a": 1}
    b = {"a": 1, "b": 2}
    assert P0E.canonical_sha256(a) == P0E.canonical_sha256(b)
