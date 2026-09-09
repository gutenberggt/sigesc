from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.enrollment_rectification_f2_3_case_preflight import (
    SCHEMA,
    _normalize_birth_date,
    _safe_summary,
    identity_fingerprint,
)


def test_identity_fingerprint_normalizes_accents_spacing_and_date():
    salt = "0123456789abcdef0123456789abcdef"
    a = identity_fingerprint(salt, "  Aluna   Vitória  ", "01/03/2013")
    b = identity_fingerprint(salt, "aluna vitoria", "2013-03-01")
    assert a == b
    assert len(a) == 64


def test_normalize_birth_date_supports_legacy_and_iso():
    assert _normalize_birth_date("01/03/2013") == "2013-03-01"
    assert _normalize_birth_date("2013-03-01") == "2013-03-01"


def test_safe_summary_does_not_emit_raw_ids_tokens_or_pii(monkeypatch):
    monkeypatch.setenv("ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED", "false")
    dry_run = {
        "contract_version": "F1.0",
        "operation": "retificacao_enturmacao",
        "execution_enabled": False,
        "can_execute_later": False,
        "dry_run_token": "SECRET_TOKEN_MUST_NOT_LEAK",
        "precondition_hash": "SECRET_PRECONDITION_MUST_NOT_LEAK",
        "student": {"id": "student-secret-id", "full_name": "Nome Privado"},
        "enrollment": {"id": "enrollment-secret-id"},
        "origin_class": {"id": "source-secret-id", "name": "6º ANO B"},
        "destination_class": {"id": "destination-secret-id", "name": "7º ANO B"},
        "counts": {"source_grades": 1},
        "course_map": [{
            "source_course_id": "source-course-secret-id",
            "source_name": "Matemática",
            "target_course_id": "target-course-secret-id",
            "target_name": "Matemática",
            "method": "unique_normalized_name",
            "ok": True,
        }],
        "grades_manifest": [{
            "source_grade_id": "grade-secret-id",
            "migratable_fields": ["b1", "b2"],
            "overlapping_fields": [],
            "destination_metadata_conflicts": [],
        }],
        "attendance_manifest": [{
            "source_attendance_id": "attendance-secret-id",
            "validated": True,
            "destination_overlap_count": 0,
        }],
        "documents": {
            "coverage_complete": False,
            "tracked_total": 1,
            "tracked_counts": {"verifiable_documents": 1},
            "coverage_gap": {"code": "SYNC_PDF_LEDGER_GAP"},
        },
        "preservations": {
            "content_entries": "preserve",
            "aee": "preserve",
            "bolsa_familia_tracking": "preserve",
            "medical_certificates": "preserve",
            "current_counts": {},
        },
        "blockers": [{"code": "DOCUMENT_RESOLUTION_REQUIRED_F1_3", "detail": {"student_id": "student-secret-id"}}],
        "warnings": [{"code": "SYNC_PDF_LEDGER_GAP"}],
        "expected_postconditions": ["zero origem"],
    }

    result = _safe_summary(
        dry_run,
        identity_hash="a" * 64,
        projection_matches_source=True,
    )
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True)

    assert result["schema"] == SCHEMA
    assert result["database_mutation"] is False
    assert result["production_writes"] is False
    assert result["dry_run_token_emitted"] is False
    assert result["precondition_hash_emitted"] is False
    assert result["student_pii_emitted"] is False
    assert result["technical_ids_emitted"] is False
    for forbidden in (
        "SECRET_TOKEN_MUST_NOT_LEAK",
        "SECRET_PRECONDITION_MUST_NOT_LEAK",
        "student-secret-id",
        "enrollment-secret-id",
        "source-course-secret-id",
        "target-course-secret-id",
        "grade-secret-id",
        "attendance-secret-id",
        "Nome Privado",
    ):
        assert forbidden not in encoded
