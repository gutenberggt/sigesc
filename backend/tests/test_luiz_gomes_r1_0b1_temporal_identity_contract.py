from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "backend/scripts/luiz_gomes_r1_0b1_live_seed.js"
PROBE = ROOT / "backend/scripts/luiz_gomes_r1_0b1_temporal_probe.js"
RUNNER = ROOT / "backend/scripts/luiz_gomes_r1_0b1_temporal_runner.sh"
WORKFLOW = ROOT / ".github/workflows/luiz-gomes-r1-0b1-temporal-identity.yml"
DOC = ROOT / "memory/audit/LUIZ_GOMES_R1_0B1_TEMPORAL_IDENTITY_2026-09-05.md"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_live_seed_is_bounded_to_non_student_metadata():
    s = text(SEED)
    assert 'd.schools.find' in s
    assert 'd.classes.find' in s
    assert 'd.courses.find' in s
    for forbidden in ('d.students', 'd.enrollments', 'd.attendance', 'd.grades', 'd.learning_objects'):
        assert forbidden not in s
    for mutator in ('insertOne(', 'insertMany(', 'updateOne(', 'updateMany(', 'replaceOne(', 'deleteOne(', 'deleteMany(', 'bulkWrite('):
        assert mutator not in s
    assert 'limit(2)' in s
    assert 'limit(20)' in s
    assert 'technical_ids_for_internal_bridge_only: true' in s


def test_historical_probe_requires_all_six_current_identities_and_fails_closed():
    s = text(PROBE)
    assert 'preservedNames.length !== 6' in s
    assert 'TEMPORAL_IDENTITY_NOT_PRESERVED' in s
    assert 'MULTIPLE_TEMPORAL_RELATIONAL_SOLUTIONS' in s
    assert 'NO_TEMPORAL_RELATIONAL_SOLUTION' in s
    assert 'FOUR_CONTROLS_WITH_MATH_IN_PERIOD' in s
    assert 'next_gate_r1_0c_open:targetRows>0' in s
    assert 'actor_attribution_attempted:false' in s
    assert 'technical_ids_emitted:false' in s
    for forbidden in ('d.students', 'd.enrollments', 'd.attendance', 'd.grades'):
        assert forbidden not in s
    for mutator in ('insertOne(', 'updateOne(', 'deleteOne(', 'bulkWrite('):
        assert mutator not in s


def test_runner_keeps_live_seed_private_and_restores_only_safe_collections():
    s = text(RUNNER)
    assert '> "$seed_raw" 2>&1' in s
    assert "printf '%s\\n' \"$point\"" in s
    assert 'printf \'const LIVE_SEED = %s;\\n\'' in s
    assert 'restore=(schools classes courses learning_objects)' in s
    assert '--network none' in s
    assert 'dst=/dump,readonly' in s
    assert 'PRODUCTION_WRITES=NO' in s
    assert 'PRODUCTION_BACKEND_PYTHON_EXECUTIONS=0' in s
    assert 'LIVE_TECHNICAL_IDS_EXPOSED=NO' in s
    assert 'PEDAGOGICAL_PLAINTEXT_EMITTED=NO' in s
    assert 'EPHEMERAL_TECHNICAL_ID_FILES_CLEANED=YES' in s
    assert 'cat "$seed_raw"' not in s
    assert 'echo "$seed_json"' not in s


def test_workflow_has_exact_owner_sha_gate_and_no_deploy():
    s = text(WORKFLOW)
    assert "[LUIZ-GOMES-R1.0B.1-TEMPORAL-IDENTITY] " in s
    assert "github.event.issue.user.login == github.repository_owner" in s
    assert "RUN_TEMPORAL_IDENTITY_BRIDGE_2026_08_18_READ_ONLY" in s
    assert "TRACKING_ISSUE':'425'" in s
    assert "PARENT_TRACKING_ISSUE':'418'" in s
    assert "ROOT_TRACKING_ISSUE':'357'" in s
    assert "branches/main" in s and "branches/production" in s
    assert "R1B1_MAIN_MOVED" in s and "R1B1_PRODUCTION_MOVED" in s
    assert "sigesc-production-deploy" not in s
    assert "git push" not in s


def test_document_records_non_inference_and_internal_id_boundary():
    s = text(DOC)
    assert "não infere autoria" in s.lower()
    assert "identidades técnicas" in s.lower()
    assert "efêmer" in s.lower()
    assert "R1.0C" in s
    assert "RECOVERABLE_EXACT" in s
