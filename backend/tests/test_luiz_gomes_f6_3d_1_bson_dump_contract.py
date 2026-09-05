from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "backend/scripts/luiz_gomes_f6_3d_1_bson_dump_runner.sh"
PROBE = ROOT / "backend/scripts/luiz_gomes_f6_3c_backup_probe.js"
WORKFLOW = ROOT / ".github/workflows/luiz-gomes-f6-3d-1-1-probe-localization.yml"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_selection_is_single_group_pre_0819_and_coherent():
    src = read(RUNNER)
    assert "2026-08-18" in src
    assert "required=(users schools classes courses learning_objects)" in src
    assert '"${#eligible[@]}" -eq 1' in src
    assert "spread <= 600" in src
    assert "structural_only_ad_hoc_bson_dump" in src
    assert "F63D1_GROUP_SELECTION=PASS" in src


def test_canonical_tree_is_excluded_and_source_is_read_only():
    src = read(RUNNER)
    assert "canonical_root='/root/sigesc-backups'" in src
    assert '-path "$canonical_root/*"' in src
    assert "F63D1_CANONICAL_BACKUP_TREE_EXCLUDED=YES" in src
    assert "dst=/dump,readonly" in src
    assert "F63D1_SOURCE_FILES_MUTATED=NO" in src


def test_restore_is_network_isolated_and_collection_allowlisted():
    src = read(RUNNER)
    assert "--network none" in src
    assert "TEMP_RESTORE_NETWORK=none" in src
    assert "TEMP_RESTORE_PORTS=none" in src
    assert "PRODUCTION_DATABASE_TOUCHED=NO" in src
    assert "mongorestore --quiet --stopOnError --db sigesc --collection" in src
    for forbidden in (
        "students",
        "enrollments",
        "attendance",
        "grades",
        "attendance_documentary",
    ):
        assert forbidden not in src


def test_probe_does_not_emit_sensitive_academic_plaintext():
    probe = read(PROBE)
    for banned in (
        "content: 1",
        "methodology: 1",
        "observations: 1",
        "records: 1",
        "student_id: 1",
    ):
        assert banned not in probe
    assert "payload_present" in probe
    assert "pedagogical_plaintext_emitted: false" in probe


def test_probe_error_localization_is_allowlisted_and_raw_output_stays_on_host():
    src = read(RUNNER)
    assert 'probe_raw="/tmp/sigesc-f63d11-probe-${run_id}.log"' in src
    assert 'mongosh --quiet --file /forensic/probe.js >"$probe_raw" 2>&1' in src
    assert "F63D11_PROBE_ERROR_MARKER=" in src
    assert "F63D11_PROBE_EXIT_CODE=" in src
    for marker in (
        "TEACHER_USER_MATCHES:",
        "TEACHER_USER_ID_MISSING",
        "SCHOOL_MATCHES:",
        "SCHOOL_ID_MISSING",
        "CLASS_MATCHES_8A:",
        "CLASS_MATCHES_9A:",
        "CLASS_MATCHES_TARGET:",
        "UNCLASSIFIED_RUNTIME_ERROR",
    ):
        assert marker in src
    assert 'rm -f "$probe_raw"' in src
    assert "RAW_PROBE_OUTPUT_EMITTED=NO" in src
    assert "emit_terminal_boundary" in src


def test_error_path_proves_cleanup_before_exit():
    src = read(RUNNER)
    error_block = src.split('if [[ -z "$point_line" ]]; then', 1)[1].split("fi\nprintf '%s\\n' \"$point_line\"", 1)[0]
    assert 'docker rm -f "$drill"' in error_block
    assert "drill=''" in error_block
    assert "emit_terminal_boundary" in error_block
    assert "exit 1" in error_block


def test_workflow_is_owner_gated_exact_sha_and_fail_closed():
    wf = read(WORKFLOW)
    assert "github.event.issue.user.login == github.repository_owner" in wf
    assert "LUIZ_GOMES_F6_3D_1_1_PROBE_LOCALIZATION':'AUTHORIZED'" in wf
    assert "LOCALIZE_20260818_HISTORICAL_PROBE_ERROR_SANITIZED" in wf
    assert "TARGET_SHA" in wf
    assert "EXPECTED_PRODUCTION_SHA" in wf
    assert "TRACKING_ISSUE':'357'" in wf
    assert "LUIZ_GOMES_F6_3D_1_1_MAIN_MOVED" in wf
    assert "LUIZ_GOMES_F6_3D_1_1_PRODUCTION_MOVED" in wf
    assert "BSON_DUMP_PROBE_ERROR" in wf
    assert "probe_error_marker" in wf
    assert "raw_probe_output_emitted" in wf


def test_no_deploy_or_data_mutation_path():
    combined = (read(RUNNER) + "\n" + read(WORKFLOW)).lower()
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
