from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "backend/scripts/luiz_gomes_r1_0b_schema_bridge_probe.js"
RUNNER = ROOT / "backend/scripts/luiz_gomes_f6_3d_1_bson_dump_runner.sh"
WORKFLOW = ROOT / ".github/workflows/luiz-gomes-r1-0b-schema-bridge.yml"
DOC = ROOT / "memory/audit/LUIZ_GOMES_R1_0B_SCHEMA_BRIDGE_2026-09-05.md"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_probe_uses_value_and_composite_schema_discovery():
    src = read(PROBE)
    for marker in (
        "LUIZ_GOMES_R1_0B_SCHEMA_BRIDGE_V1",
        "FULL_VALUE",
        "GRADE_SECTION_COMPOSITE",
        "SCHOOL_CLASS_RELATION_NOT_RESOLVED",
        "CLASS_REFERENCE_RELATION_NOT_RESOLVED",
        "MATH_REFERENCE_RELATION_NOT_RESOLVED",
        "FOUR_CONTROLS_WITH_MATH_IN_PERIOD",
        "MULTIPLE_STRUCTURAL_BRIDGE_SOLUTIONS",
        "SCHEMA_BRIDGE_RESOLVED_TARGET_PAYLOAD_PRESENT",
        "SCHEMA_BRIDGE_RESOLVED_NO_TARGET_MATH_ROWS",
        "SCHEMA_BRIDGE_RESOLVED_TARGET_ROWS_WITHOUT_PAYLOAD",
        "next_gate_r1_0c_open",
    ):
        assert marker in src


def test_probe_is_fail_closed_and_does_not_attribute_actor():
    src = read(PROBE)
    for marker in (
        "actor_attribution_attempted: false",
        "fail_closed_on_ambiguity: true",
        "technical_ids_emitted: false",
        "pedagogical_plaintext_emitted: false",
        "student_data_read: false",
        "attendance_records_read: false",
        "grades_read: false",
    ):
        assert marker in src
    for banned in (
        "d.users",
        "d.students",
        "d.enrollments",
        "d.attendance",
        "d.grades",
        "insertOne(",
        "insertMany(",
        "updateOne(",
        "updateMany(",
        "deleteOne(",
        "deleteMany(",
        "replaceOne(",
        "bulkWrite(",
    ):
        assert banned not in src


def test_payload_plaintext_is_not_emitted():
    src = read(PROBE)
    assert 'SKIP_KEYS = new Set' in src
    for field in ('"content"', '"methodology"', '"observations"', '"resources"'):
        assert field in src
    assert "rows_with_payload" in src
    assert "payloadPresent" in src


def test_existing_runner_keeps_isolated_restore_boundary():
    src = read(RUNNER)
    for marker in (
        "--network none",
        "dst=/dump,readonly",
        "PRODUCTION_DATABASE_TOUCHED=NO",
        "TEMP_RESTORE_PORTS=none",
        "PEDAGOGICAL_PLAINTEXT_EMITTED=NO",
        "RAW_PROBE_OUTPUT_EMITTED=NO",
    ):
        assert marker in src
    for excluded in ("students", "enrollments", "attendance", "grades"):
        assert f'optional=({excluded}' not in src
        assert f'required=({excluded}' not in src


def test_workflow_requires_owner_exact_sha_and_read_only_confirmation():
    src = read(WORKFLOW)
    for marker in (
        "[LUIZ-GOMES-R1.0B-SCHEMA-BRIDGE] ",
        "RUN_SCHEMA_BRIDGE_2026_08_18_READ_ONLY",
        "TRACKING_ISSUE':'422'",
        "PARENT_TRACKING_ISSUE':'418'",
        "ROOT_TRACKING_ISSUE':'357'",
        "TARGET_SHA",
        "EXPECTED_PRODUCTION_SHA",
        "github.event.issue.user.login == github.repository_owner",
        "SCHEMA_BRIDGE_RUNTIME_OR_BOUNDARY_ERROR",
    ):
        assert marker in src


def test_document_preserves_r1_0b_scope():
    src = read(DOC)
    for marker in (
        "R1.0B",
        "dump de 18/08/2026",
        "CLASS_NAME_SCHEMA_NOT_RESOLVED",
        "Descoberta estrutural por valor",
        "Mongo temporário",
        "R1.0C",
        "não prova autoria",
    ):
        assert marker in src
