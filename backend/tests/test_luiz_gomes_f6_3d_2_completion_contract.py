from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "backend/scripts/luiz_gomes_f6_3d_1_bson_dump_runner.sh"
PROBE = ROOT / "backend/scripts/luiz_gomes_f6_3d_2_historical_actor_probe.js"
WORKFLOW = ROOT / ".github/workflows/luiz-gomes-f6-3d-2-completion.yml"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_probe_has_adaptive_historical_schema_contract():
    src = read(PROBE)
    for marker in (
        "LUIZ_GOMES_F6_3D_2_HISTORICAL_ACTOR_V3_ADAPTIVE",
        "HISTORICAL_SCHEMA_INSUFFICIENT",
        "CLASS_NAME_KEYS",
        "CLASS_ID_KEYS",
        "CLASS_GROUP_KEYS",
        "CLASS_YEAR_KEYS",
        "COURSE_NAME_KEYS",
        "COURSE_ID_KEYS",
        "LO_CLASS_KEYS",
        "LO_COURSE_KEYS",
        "LO_DATE_KEYS",
        "schema_aliases_fail_closed: true",
        "structural_solution_count",
        "selected_by_six_classes_and_four_math_controls",
    ):
        assert marker in src
    for name in ("6º ANO A", "6º ANO B", "7º ANO A", "7º ANO B", "8º ANO A", "9º ANO A"):
        assert name in src


def test_probe_b_terminal_is_explicit_and_fail_closed():
    src = read(PROBE)
    assert 'emit("INCONCLUSIVE", "HISTORICAL_SCHEMA_INSUFFICIENT"' in src
    assert 'terminal_state: "INSUFFICIENT"' in src
    for reason in (
        "REQUIRED_COLLECTION_MISSING",
        "CLASS_NAME_SCHEMA_NOT_RESOLVED",
        "MATH_COURSE_SCHEMA_NOT_RESOLVED",
        "LEARNING_OBJECT_DATE_SCHEMA_NOT_RESOLVED",
        "CLASS_REFERENCE_SCHEMA_NOT_RESOLVED",
        "NO_UNIQUE_SIX_CLASS_FOUR_CONTROL_SCHEMA_SOLUTION",
        "MULTIPLE_STRUCTURAL_SCHEMA_SOLUTIONS",
        "ACTOR_IDENTITY_NOT_UNIQUELY_DERIVABLE_FROM_AVAILABLE_HISTORICAL_FIELDS",
    ):
        assert reason in src


def test_probe_completed_path_requires_unique_schema_and_exact_actor():
    src = read(PROBE)
    assert "solutions.length !== 1" in src
    assert 'terminal_state: "RESOLVED"' in src
    assert "TEACHER_ASSIGNMENTS_ADAPTIVE_EXACT_CONTROL_UNANIMOUS" in src
    assert "LEARNING_OBJECT_METADATA_ADAPTIVE_FOUR_CLASS_DOMINANT" in src
    assert 'status: "EXACT_CONTROL_DERIVED"' in src
    assert "school_identity_structurally_derived: true" in src
    assert "historical_schema_adaptively_resolved: true" in src


def test_probe_infers_actor_without_users_lookup():
    src = read(PROBE)
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
    for marker in (
        "pedagogical_plaintext_emitted: false",
        "pedagogical_payload_boolean_only: true",
        "attendance_records_read: false",
        "student_data_read: false",
        "production_writes: false",
        "technical_ids_emitted: false",
    ):
        assert marker in src
    completed_tail = src[src.find('emit("COMPLETED"') :]
    assert "actorStaffId" not in completed_tail
    assert "actorPrincipal" not in completed_tail
    assert "classMap" not in completed_tail


def test_runner_remains_isolated_and_read_only():
    src = read(RUNNER)
    for marker in (
        "--network none",
        "dst=/dump,readonly",
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


def test_completion_gate_accepts_only_a_or_b_terminal_states():
    src = read(WORKFLOW)
    assert "LUIZ_GOMES_F6_3D_2_HISTORICAL_ACTOR_V3_ADAPTIVE" in src
    assert "HISTORICAL_SCHEMA_INSUFFICIENT" in src
    assert "EXACT_CONTROL_DERIVED" in src
    assert "historical_schema_adaptively_resolved" in src
    assert "F63D2_COMPLETION_TERMINAL_STATE_NOT_A_OR_B" in src


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
