from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "backend/scripts/luiz_gomes_r1_0b2_historical_topology_probe.js"
RUNNER = ROOT / "backend/scripts/luiz_gomes_f6_3d_1_bson_dump_runner.sh"
WORKFLOW = ROOT / ".github/workflows/luiz-gomes-r1-0b2-historical-topology.yml"
DOC = ROOT / "memory/audit/LUIZ_GOMES_R1_0B2_HISTORICAL_TOPOLOGY_2026-09-05.md"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_probe_is_relational_and_does_not_use_current_class_identity_bridge():
    src = read(PROBE)
    for marker in (
        "LUIZ_GOMES_R1_0B2_HISTORICAL_TOPOLOGY_V1",
        "teacher_assignments",
        "teacher_class_assignments",
        "teacherAssignmentIndexes",
        "teacherMathAssignmentIndexes",
        "teacherMathClassIndexes",
        "classUniqueValues",
        "courseUniqueValues",
        "six_node_neighborhood_resolved",
        "topology_fingerprint",
        "SIX_NODE_NEIGHBORHOOD_RESOLVED_ROLE_MAPPING_UNANCHORED",
    ):
        assert marker in src
    for banned in (
        "LUIZ_GOMES_R1_0B1_LIVE_SEED_JSON",
        "math_course_ids",
        "school_id: schoolId",
        "current_class_ids",
    ):
        assert banned not in src


def test_probe_refuses_arbitrary_role_mapping_and_graph_symmetry():
    src = read(PROBE)
    for marker in (
        "HISTORICAL_TOPOLOGY_BRIDGE_SYMMETRIC",
        "GRAPH_AUTOMORPHISM_OR_EQUAL_LOCAL_SIGNATURE",
        "NO_INDEPENDENT_SEMANTIC_ROLE_ANCHOR",
        "role_mapping_resolved: false",
        "fail_closed_on_graph_symmetry: true",
        "class_labels_used_for_mapping: false",
        "current_ids_used_for_mapping: false",
        "next_gate_r1_0c_open: false",
    ):
        assert marker in src
    assert "ROLES[" not in src
    assert ".sort((a, b) => a.classIndex" not in src


def test_probe_does_not_emit_sensitive_or_pedagogical_data():
    src = read(PROBE)
    for marker in (
        "SKIP_KEYS = new Set",
        "pedagogical_plaintext_emitted: false",
        "technical_ids_emitted: false",
        "student_data_read: false",
        "attendance_read: false",
        "attendance_records_read: false",
        "grades_read: false",
        "actor_payload_attribution_attempted: false",
        "payloadPresent",
    ):
        assert marker in src
    for banned in (
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


def test_existing_runner_preserves_isolated_aug18_restore_boundary():
    src = read(RUNNER)
    for marker in (
        "--network none",
        "dst=/dump,readonly",
        "PRODUCTION_DATABASE_TOUCHED=NO",
        "TEMP_RESTORE_PORTS=none",
        "PEDAGOGICAL_PLAINTEXT_EMITTED=NO",
        "RAW_PROBE_OUTPUT_EMITTED=NO",
        "2026-08-18",
    ):
        assert marker in src
    for excluded in ("students", "enrollments", "attendance", "grades"):
        assert f"required=({excluded}" not in src
        assert f"optional=({excluded}" not in src


def test_workflow_requires_owner_exact_sha_and_explicit_read_only_gate():
    src = read(WORKFLOW)
    for marker in (
        "[LUIZ-GOMES-R1.0B.2-HISTORICAL-TOPOLOGY] ",
        "RUN_HISTORICAL_TOPOLOGY_BRIDGE_2026_08_18_READ_ONLY",
        "TRACKING_ISSUE':'435'",
        "PARENT_TRACKING_ISSUE':'418'",
        "ROOT_TRACKING_ISSUE':'357'",
        "TARGET_SHA",
        "EXPECTED_PRODUCTION_SHA",
        "github.event.issue.user.login == github.repository_owner",
        "HISTORICAL_TOPOLOGY_RUNTIME_OR_BOUNDARY_ERROR",
    ):
        assert marker in src


def test_document_seals_semantic_non_inference_rule():
    src = read(DOC)
    for marker in (
        "R1.0B.2",
        "Topologia Histórica",
        "0/6",
        "None não significa zero",
        "seis nós não são seis papéis",
        "simetria",
        "R1.0C",
        "R1.1",
        "sem deploy",
    ):
        assert marker in src
