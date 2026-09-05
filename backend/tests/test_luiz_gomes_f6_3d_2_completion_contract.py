from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "backend/scripts/luiz_gomes_f6_3d_1_bson_dump_runner.sh"
PROBE = ROOT / "backend/scripts/luiz_gomes_f6_3d_2_historical_actor_probe.js"
WORKFLOW = ROOT / ".github/workflows/luiz-gomes-f6-3d-2-completion.yml"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_probe_resolves_historical_school_structurally_fail_closed():
    src = read(PROBE)
    for marker in (
        "SCHOOL_CONTEXT_NOT_STRUCTURALLY_RESOLVED",
        "SCHOOL_CONTEXT_STRUCTURAL_AMBIGUITY",
        "selected_by_six_classes_and_four_math_controls",
        "required_unique_classes",
        "controls_requiring_math_evidence",
    ):
        assert marker in src
    for name in ("6º ANO A", "6º ANO B", "7º ANO A", "7º ANO B", "8º ANO A", "9º ANO A"):
        assert name in src


def test_probe_infers_actor_without_users_lookup():
    src = read(PROBE)
    assert "TEACHER_ASSIGNMENTS_EXACT_CONTROL_UNANIMOUS" in src
    assert "LEARNING_OBJECT_METADATA_FOUR_CLASS_DOMINANT" in src
    assert "EXACT_CONTROL_DERIVED" in src
    assert "actor_identity_derived_without_user_lookup: true" in src
    assert "technical_ids_emitted: false" in src
    for banned in ('d.users', 'getCollection("users")', 'student_id: 1', 'records: 1'):
        assert banned not in src


def test_probe_target_taxonomy_is_complete():
    src = read(PROBE)
    for marker in (
        "BSON_20260818_RECOVERY_SOURCE_CONFIRMED",
        "BSON_20260818_LUIZ_ROWS_UNDER_NONMATH_COMPONENT",
        "BSON_20260818_LUIZ_ROWS_WITHOUT_PAYLOAD",
        "BSON_20260818_BINDING_PRESENT_CONTENT_ABSENT",
        "BSON_20260818_UNATTRIBUTED_MATH_PAYLOAD_CANDIDATE",
        "HISTORICAL_ACTOR_ABSENT_FROM_TARGET_20260818",
        "HISTORICAL_ACTOR_ABSENT_FROM_BOTH_TARGETS_20260818",
    ):
        assert marker in src


def test_probe_emits_no_ids_or_pedagogical_plaintext():
    src = read(PROBE)
    assert "pedagogical_plaintext_emitted: false" in src
    assert "pedagogical_payload_boolean_only: true" in src
    assert "attendance_records_read: false" in src
    assert "student_data_read: false" in src
    assert "production_writes: false" in src
    assert "actorStaffId" in src
    assert "actorStaffId" not in src[src.find("emit(\"COMPLETED\"") :]


def test_runner_remains_isolated_and_read_only():
    src = read(RUNNER)
    for marker in (
        "--network none",
        'dst=/dump,readonly',
        "PRODUCTION_DATABASE_TOUCHED=NO",
        "SOURCE_MOUNT=read_only",
        "RAW_PROBE_OUTPUT_EMITTED=NO",
    ):
        assert marker in src
    for forbidden in ("students", "enrollments", "attendance", "grades", "attendance_documentary"):
        assert forbidden not in src


def test_completion_workflow_is_owner_gated_exact_sha():
    src = read(WORKFLOW)
    for marker in (
        "github.event.issue.user.login == github.repository_owner",
        "LUIZ_GOMES_F6_3D_2_COMPLETION':'AUTHORIZED'",
        "RESOLVE_SCHOOL_CONTEXT_AND_INFER_HISTORICAL_ACTOR",
        "[LUIZ-GOMES-F6.3D.2-COMPLETE] ",
        "TARGET_SHA",
        "EXPECTED_PRODUCTION_SHA",
        "TRACKING_ISSUE':'357'",
        "LUIZ_GOMES_F6_3D_2_COMPLETION_MAIN_MOVED",
        "LUIZ_GOMES_F6_3D_2_COMPLETION_PRODUCTION_MOVED",
    ):
        assert marker in src


def test_completion_gate_requires_exact_school_and_actor_for_completed():
    src = read(WORKFLOW)
    assert "structural_matches')!=1" in src
    assert "selected_by_six_classes_and_four_math_controls') is not True" in src
    assert "EXACT_CONTROL_DERIVED" in src
    assert "school_identity_structurally_derived') is not True" in src


def test_no_production_mutation_in_executable_probe_or_runner():
    executable = (read(PROBE) + "\n" + read(RUNNER)).lower()
    for forbidden in (
        "insertone(",
        "updateone(",
        "deletemany(",
        "deleteone(",
        "delete_many",
    ):
        assert forbidden not in executable


def test_no_deploy_path_in_workflow_or_runner():
    operational = (read(RUNNER) + "\n" + read(WORKFLOW)).lower()
    for forbidden in (
        "git pull",
        "docker compose up",
        "docker stack deploy",
        "kubectl apply",
    ):
        assert forbidden not in operational
