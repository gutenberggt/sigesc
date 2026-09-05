from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "backend" / "scripts" / "sibling_class_reconstruction_preflight_readonly.py"
MIRROR = ROOT / "backend" / "scripts" / "sibling_class_reconstruction_mirror_policy.py"
GLOBAL = ROOT / "backend" / "scripts" / "sibling_class_reconstruction_global_ordinal_policy.py"
ORPHAN = ROOT / "backend" / "scripts" / "sibling_class_reconstruction_orphan_adjudication.py"
STRUCTURAL = ROOT / "backend" / "scripts" / "sibling_class_reconstruction_orphan_structural_discrimination.py"
WORKFLOW = ROOT / ".github" / "workflows" / "r2-sibling-class-orphan-structural-discrimination.yml"
AUDIT = ROOT / "memory" / "audit" / "R2_0C1_ORPHAN_STRUCTURAL_DISCRIMINATION_2026-09-05.md"

ns = {"__name__": "r2c1_test_module"}
for path in (BASE, MIRROR, GLOBAL, ORPHAN, STRUCTURAL):
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), ns)


def _row(**overrides):
    row = {
        "id": "private-doc-id",
        "class_id": "private-class",
        "course_id": "private-math",
        "date": "2026-04-30",
        "academic_year": 2026,
        "teacher_id": "private-teacher",
        "assignment_id": "private-assignment",
        "number_of_classes": 1,
        "period": "MATUTINO",
        "aula_numero": 1,
        "version": 1,
        "observations": "texto privado",
        "created_at": "2026-04-30T12:00:00+00:00",
        "updated_at": "2026-04-30T12:00:00+00:00",
    }
    row.update(overrides)
    return row


def test_projection_never_reads_attendance_records():
    projection = ns["STRUCTURAL_ATTENDANCE_PROJECTION"]
    assert "records" not in projection
    source = STRUCTURAL.read_text(encoding="utf-8")
    assert 'db.attendance.find(' in source
    assert 'db.students' not in source
    assert 'db.enrollments' not in source
    assert 'db.grades' not in source
    assert 'db.audit_logs' not in source


def test_two_distinct_sessions_require_semantic_discriminator():
    compare = ns["_structural_comparison"](
        _row(aula_numero=1),
        _row(id="private-doc-id-2", aula_numero=2),
    )
    assert compare["strong_distinct_session_evidence"] is True
    assert compare["duplicate_supported_evidence"] is False


def test_timestamp_or_technical_identity_difference_is_not_session_evidence():
    compare = ns["_structural_comparison"](
        _row(),
        _row(
            id="other-private-id",
            created_at="2026-04-30T12:05:00+00:00",
            updated_at="2026-04-30T12:05:00+00:00",
        ),
    )
    assert compare["strong_distinct_session_evidence"] is False
    assert compare["duplicate_supported_evidence"] is True
    assert compare["created_at_gap_seconds_abs"] == 300


def test_legacy_canonical_overlap_requires_business_equivalence_and_marker():
    legacy = _row(
        assignment_id=None,
        historical_backfill_last_authorized_assignment_id="private-canonical-assignment",
        historical_backfill_last_authorized_at="2026-08-20T10:00:00+00:00",
    )
    canonical = _row(id="canonical-private-doc")
    compare = ns["_structural_comparison"](legacy, canonical)
    assert compare["business_signature_equal"] is True
    assert compare["assignment_presence_asymmetry"] is True
    assert compare["legacy_marker_asymmetry"] is True
    assert compare["strong_legacy_canonical_overlap_evidence"] is True
    assert compare["duplicate_supported_evidence"] is False


def test_assignment_presence_alone_does_not_prove_legacy_overlap():
    left = _row(assignment_id=None)
    right = _row(id="private-doc-2")
    compare = ns["_structural_comparison"](left, right)
    assert compare["assignment_presence_asymmetry"] is True
    assert compare["strong_legacy_canonical_overlap_evidence"] is False


def test_asymmetric_session_metadata_fails_closed_as_conflict():
    compare = ns["_structural_comparison"](
        _row(aula_numero=None),
        _row(id="private-doc-2", aula_numero=2),
    )
    assert compare["session_presence_asymmetry"] is True
    assert compare["strong_distinct_session_evidence"] is False
    assert compare["structural_conflict_evidence"] is True


def test_safe_meta_contains_hashes_not_plaintext_or_ids():
    meta = ns["_safe_document_meta"](_row())
    rendered = repr(meta)
    assert "texto privado" not in rendered
    assert "private-doc-id" not in rendered
    assert "private-class" not in rendered
    assert len(meta["business_signature"]) == 64
    assert len(meta["session_signature"]) == 64
    assert len(meta["provenance_signature"]) == 64


def test_workflow_is_owner_gated_exact_sha_read_only():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "[R2-SIBLING-CLASS-ORPHAN-STRUCTURAL]" in source
    assert "github.event.issue.user.login == github.repository_owner" in source
    assert "RUN_LUIZ_MATH_9A_2026_04_30_STRUCTURAL_READ_ONLY" in source
    assert "TARGET_SHA" in source
    assert "EXPECTED_PRODUCTION_SHA" in source
    assert "TRACKING_ISSUE':'450'" in source
    assert "production_writes" in source
    assert "attendance_records_read" in source
    assert "git push" not in source
    assert "docker compose up" not in source


def test_audit_contract_preserves_no_automatic_sanitization_rule():
    text = AUDIT.read_text(encoding="utf-8")
    assert "nenhum saneamento automático" in text.casefold()
    assert "ORPHAN_TWO_DISTINCT_SESSIONS_SUPPORTED" in text
    assert "ORPHAN_DUPLICATE_ATTENDANCE_SUPPORTED" in text
    assert "ORPHAN_LEGACY_CANONICAL_OVERLAP_SUPPORTED" in text
