from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "backend/scripts/luiz_gomes_f6_3d_1_bson_dump_runner.sh"
PROBE = ROOT / "backend/scripts/luiz_gomes_f6_3c_backup_probe.js"
WORKFLOW = ROOT / ".github/workflows/luiz-gomes-f6-3d-1-1-probe-localization.yml"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_runner_keeps_single_coherent_20260818_dump_and_readonly_mount():
    src = read(RUNNER)
    assert "2026-08-18" in src
    assert '"${#eligible[@]}" -eq 1' in src
    assert "spread <= 600" in src
    assert "structural_only_ad_hoc_bson_dump" in src
    assert "dst=/dump,readonly" in src
    assert "F63D1_SOURCE_FILES_MUTATED=NO" in src


def test_runner_restore_is_network_isolated_and_no_production_write():
    src = read(RUNNER)
    assert "--network none" in src
    assert "TEMP_RESTORE_NETWORK=none" in src
    assert "TEMP_RESTORE_PORTS=none" in src
    assert "PRODUCTION_DATABASE_TOUCHED=NO" in src
    assert "SOURCE_MOUNT=read_only" in src
    assert "TEMP_CONTAINERS_CLEANED=YES" in src
    assert "RAW_PROBE_OUTPUT_EMITTED=NO" in src
    for forbidden in ("students", "enrollments", "attendance", "grades", "attendance_documentary"):
        assert forbidden not in src


def test_probe_uses_four_control_classes_and_two_targets():
    probe = read(PROBE)
    for name in ("6º ANO A", "6º ANO B", "7º ANO A", "7º ANO B", "8º ANO A", "9º ANO A"):
        assert name in probe
    assert "CONTROL_CLASSES" in probe
    assert "TARGET_CLASSES" in probe
    assert "2026-02-01" in probe
    assert "2026-05-01" in probe


def test_probe_infers_actor_without_users_lookup():
    probe = read(PROBE)
    assert "TEACHER_ASSIGNMENTS_EXACT_CONTROL_UNANIMOUS" in probe
    assert "LEARNING_OBJECT_METADATA_FOUR_CLASS_DOMINANT" in probe
    assert "actor_identity_derived_without_user_lookup: true" in probe
    assert "technical_ids_emitted: false" in probe
    for banned in ('d.users', 'getCollection("users")', 'findOne({email'):
        assert banned not in probe


def test_probe_does_not_emit_pedagogical_plaintext_or_student_data():
    probe = read(PROBE)
    for banned in ("content: 1", "methodology: 1", "observations: 1", "records: 1", "student_id: 1"):
        assert banned not in probe
    assert "payload_present" in probe
    assert "pedagogical_plaintext_emitted: false" in probe
    assert "attendance_records_read: false" in probe
    assert "student_data_read: false" in probe


def test_probe_has_conclusive_and_fail_closed_taxonomy():
    probe = read(PROBE)
    for marker in (
        "HISTORICAL_ACTOR_NOT_UNIQUELY_INFERRED",
        "BSON_20260818_RECOVERY_SOURCE_CONFIRMED",
        "BSON_20260818_LUIZ_ROWS_UNDER_NONMATH_COMPONENT",
        "BSON_20260818_BINDING_PRESENT_CONTENT_ABSENT",
        "HISTORICAL_ACTOR_ABSENT_FROM_BOTH_TARGETS_20260818",
    ):
        assert marker in probe
    assert 'status: "EXACT_CONTROL_DERIVED"' in probe


def test_workflow_is_owner_gated_exact_sha_for_f63d2():
    wf = read(WORKFLOW)
    assert "github.event.issue.user.login == github.repository_owner" in wf
    assert "LUIZ_GOMES_F6_3D_2_HISTORICAL_ACTOR':'AUTHORIZED'" in wf
    assert "INFER_20260818_LUIZ_ACTOR_FROM_CONTROL_CLASSES" in wf
    assert "[LUIZ-GOMES-F6.3D.2-ACTOR] " in wf
    assert "TARGET_SHA" in wf
    assert "EXPECTED_PRODUCTION_SHA" in wf
    assert "TRACKING_ISSUE':'357'" in wf
    assert "LUIZ_GOMES_F6_3D_2_MAIN_MOVED" in wf
    assert "LUIZ_GOMES_F6_3D_2_PRODUCTION_MOVED" in wf


def test_no_deploy_or_production_data_mutation_path():
    combined = (read(PROBE) + "\n" + read(RUNNER) + "\n" + read(WORKFLOW)).lower()
    for forbidden in (
        "git pull",
        "docker compose up",
        "docker stack deploy",
        "kubectl apply",
        "insertone(",
        "updateone(",
        "deleteone(",
        "delete_many",
        "rm -rf /root/sigesc-backups",
    ):
        assert forbidden not in combined
