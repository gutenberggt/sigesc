from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_dvd_missing_bindings_p0.py"


def _source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_p0_missing_bindings_preflight_is_strictly_read_only():
    source = _source()

    forbidden_writes = (
        ".insert_one(",
        ".insert_many(",
        ".update_one(",
        ".update_many(",
        ".delete_one(",
        ".delete_many(",
        ".replace_one(",
        ".find_one_and_update(",
    )
    for token in forbidden_writes:
        assert token not in source, f"preflight P0 não pode escrever no Mongo: {token}"

    assert '"mutates_database": False' in source
    assert '"mode": "READ_ONLY_P0_MISSING_BINDINGS_PREFLIGHT"' in source


def test_p0_missing_bindings_reuses_sealed_cutover_evidence_rules():
    source = _source()

    assert "first_wave_blocker" in source
    assert "build_manifest_weekly_slots" in source
    assert 'blocker == "regular_or_integrator_review"' in source
    assert "regular_sibling_evidence_ids" in source
    assert 'state = "missing_regular_sibling_evidence"' in source


def test_p0_missing_bindings_requires_teacher_scope():
    source = _source()

    assert 'parser.add_argument("--teacher-user-id", required=True)' in source
    assert '"teacher_id": teacher_user_id' in source
